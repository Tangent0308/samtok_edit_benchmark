#!/usr/bin/env python3
"""Audit a failed native RePlan request and test one explicit, separate repair."""
from __future__ import annotations

import argparse
import ast
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    content = json.dumps(value, indent=2, ensure_ascii=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != content:
            raise ValueError(f'Preserve earlier diagnostic evidence: {path}')
        return
    with path.open('x') as stream:
        stream.write(content)


def native_functions(path):
    """Execute the unchanged upstream parser and bbox checks without neural imports."""
    wanted = {'extract_bbox_from_response', 'extract_gen_image_prompt', 'expand_bbox'}
    tree = ast.parse(path.read_text())
    nodes = [node for cls in tree.body if isinstance(cls, ast.ClassDef)
             and cls.name == 'RePlanPipeline' for node in cls.body
             if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if {node.name for node in nodes} != wanted:
        raise ValueError('Pinned native functions not found')
    namespace = {'json': json, 're': re}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(path), 'exec'), namespace)
    return namespace


def invalid_boxes(regions, size):
    width, height = size
    errors = []
    for index, region in enumerate(regions):
        box = region.get('bbox_2d')
        reason = None
        if (not isinstance(box, list) or len(box) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in box)):
            reason = 'expected four finite coordinates'
        else:
            x1, y1, x2, y2 = box
            if x1 >= x2 or y1 >= y2:
                reason = 'non-positive area'
            elif not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                reason = 'outside public canvas'
        if reason:
            errors.append({'region_index': index, 'bbox_2d': box, 'reason': reason})
    return errors


def correction_prompt(instruction, response, errors, size):
    width, height = size
    return (instruction + '\n\n'
            'The following previous native plan contains invalid region coordinates. '
            'Correct this structural error using the supplied image. This is one correction request.\n'
            f'Public image canvas: width={width}, height={height} pixels. '
            'Every box must satisfy 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height.\n'
            'Return a COMPLETE plan in the same <think>, <gen_image>, <region> format. '
            'Change ONLY bbox_2d in the listed invalid region entries. Preserve the number '
            'and order of regions, every hint and all other region fields, every already-valid '
            'box, and the exact <gen_image> text. Do not omit any requested operation. '
            'Do not replace an invalid box by an arbitrary one-pixel strip. Locate the intended '
            'object from the image. Indices below are zero-based.\n'
            f'Invalid entries: {json.dumps(errors)}\n'
            f'Previous native plan:\n{response}')


def validate_correction(original_regions, proposal_regions, original_global,
                        proposal_global, invalid_indices, size):
    if not isinstance(proposal_regions, list) or len(proposal_regions) != len(original_regions):
        raise ValueError('The correction changed the region count or could not be parsed')
    if original_global != proposal_global:
        raise ValueError('The correction changed the global instruction')
    for index, (old, new) in enumerate(zip(original_regions, proposal_regions, strict=True)):
        if not isinstance(new, dict):
            raise ValueError('A corrected region is not an object')
        if index not in invalid_indices:
            if old != new:
                raise ValueError(f'The correction changed an already-valid region: {index}')
        elif {k: v for k, v in old.items() if k != 'bbox_2d'} != {
                k: v for k, v in new.items() if k != 'bbox_2d'}:
            raise ValueError(f'The correction changed a hint or another region field: {index}')
    errors = invalid_boxes(proposal_regions, size)
    if errors:
        raise ValueError(f'The correction still contains invalid boxes: {errors}')


def merge_single_region(response, regions, proposal_regions, invalid_indices, size):
    """Project only a uniquely identified invalid entry's native predicted box."""
    if len(invalid_indices) != 1 or not isinstance(proposal_regions, list) or len(proposal_regions) != 1:
        raise ValueError('Single-region recovery requires exactly one invalid entry and one proposal')
    index = next(iter(invalid_indices))
    proposal = proposal_regions[0]
    if proposal.get('hint', '').strip().lower() != regions[index]['hint'].strip().lower():
        raise ValueError('The single-region planner changed the requested operation')
    if invalid_boxes(proposal_regions, size):
        raise ValueError('The single-region proposal has invalid coordinates')
    merged = copy.deepcopy(regions)
    merged[index]['bbox_2d'] = proposal['bbox_2d']
    corrected = re.sub(r'<region>.*?</region>',
                       lambda _: '<region>' + json.dumps(merged) + '</region>',
                       response, count=1, flags=re.DOTALL)
    return corrected, merged


def context(root, case):
    from samtok_benchmark.external_mira.data import load_bundle
    from samtok_benchmark.external_mira.adapters import native_request

    if read(root / 'STATUS.json')['status'] not in ('complete', 'finished_with_missing'):
        raise ValueError('Wait until the original full evaluation has ended')
    run = read(root / 'run_001/RUN.json')
    config = read(root / 'run_001/CONFIG.json')
    bundle = load_bundle(Path(run['bundle']), [case])
    item = next(item for item in bundle['cases'] if item['case_id'] == case)
    public = read(item['public'])
    plan_path = root / 'run_001/replan/plan' / case / 'result.json'
    failure_path = root / 'run_001/replan/edit' / case / 'result.json'
    plan, failure = read(plan_path), read(failure_path)
    if plan['status'] != 'completed' or failure['status'] != 'failed':
        raise ValueError('This diagnostic requires an actual failed edit and a returned plan')
    if failure['identity']['previous_sha256'] != sha(plan_path):
        raise ValueError('The failure is not bound to this original plan')
    call = native_request('replan', public, config)
    native = plan['native']
    if (native['prompt'] != call['prompt'] or native['planner_image_sha256'] != sha(call['planner_image'])
            or native['public_input_digest'] != public['input_digest']):
        raise ValueError('Original native input identity mismatch')
    source = Path(config['paths']['sources']) / 'replan/replan/pipelines/replan.py'
    functions = native_functions(source)
    regions = functions['extract_bbox_from_response'](None, native['response'])
    original_global = functions['extract_gen_image_prompt'](None, native['response'])
    errors = invalid_boxes(regions, public['source']['size'])
    if not errors:
        raise ValueError('The original failure is not an invalid-box case')
    identity = {'case_id': case, 'original_plan_sha256': sha(plan_path),
                'original_failure_sha256': sha(failure_path), 'native_source_sha256': sha(source),
                'public_sha256': sha(item['public']), 'config_sha256': sha(root / 'run_001/CONFIG.json'),
                'diagnostic_script_sha256': sha(__file__)}
    return config, public, item, native, call, functions, regions, original_global, errors, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('audit', 'plan', 'edit'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--strategy', choices=('full_feedback', 'single_region'), default='full_feedback')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    if out == root or out.is_relative_to(root):
        raise ValueError('Repair diagnostics must stay outside the formal experiment')
    (config, public, item, native, call, functions, regions,
     original_global, errors, identity) = context(root, args.case)
    identity['repair_strategy'] = args.strategy
    invalid_indices = {error['region_index'] for error in errors}
    if args.strategy == 'single_region' and len(invalid_indices) != 1:
        raise ValueError('The single-region diagnostic requires exactly one invalid entry')
    if args.stage == 'audit':
        replay = []
        for error in errors:
            try:
                box = functions['expand_bbox'](None, error['bbox_2d'], public['source']['size'],
                                               call['parameters']['expand_value'])
                replay.append({'region_index': error['region_index'], 'native_result': box})
            except Exception as exc:
                replay.append({'region_index': error['region_index'], 'native_error': repr(exc)})
        result = {'identity': identity, 'invalid_regions': errors, 'native_cpu_replay': replay,
                  'raw_response_equals_decoded_trace': native['response'] == native['trace'][-1]['response'],
                  'original_diffusion_started': False,
                  'correction_budget': 1, 'uses_evaluation_annotations': False,
                  'protocol_change': f'One additional native planner call using {args.strategy}; diagnostic only'}
        save(out / 'AUDIT.json', result)
        print(json.dumps(result, indent=2), flush=True)
        return

    if read(out / 'AUDIT.json')['identity'] != identity:
        raise ValueError('Audit identity changed')
    stage_out = out / args.stage
    stage_out.mkdir(parents=True, exist_ok=True)
    with (stage_out / 'ADMITTED.json').open('x') as stream:
        json.dump({'identity': identity, 'time': datetime.now(timezone.utc).isoformat()}, stream)
    tick = time.monotonic()
    result = {'identity': identity, 'status': 'failed', 'diagnostic_only': True}
    try:
        from samtok_benchmark.ifbench.fairness_dev_worker import NativeBackend

        if args.stage == 'plan':
            repair_call = dict(call)
            repair_call['prompt'] = (correction_prompt(call['prompt'], native['response'], errors,
                                                       public['source']['size'])
                                     if args.strategy == 'full_feedback'
                                     else regions[next(iter(invalid_indices))]['hint'])
            repair_call['configuration_id'] = f'mira-replan-{args.strategy}-diagnostic-v1'
            save(stage_out / 'call.json', repair_call)
            load_tick = time.monotonic()
            backend = NativeBackend('replan', 'planner', config, stage_out)
            result['load_seconds'] = time.monotonic() - load_tick
            backend.reset()
            _, proposal = backend.run(repair_call, public, stage_out)
            backend.synchronize()
            save(stage_out / 'native_response.json', proposal)
            proposed_regions = functions['extract_bbox_from_response'](None, proposal['response'])
            corrected_response = proposal['response']
            if args.strategy == 'single_region':
                corrected_response, proposed_regions = merge_single_region(
                    native['response'], regions, proposed_regions, invalid_indices, public['source']['size'])
            proposed_global = functions['extract_gen_image_prompt'](None, corrected_response)
            validate_correction(regions, proposed_regions, original_global, proposed_global,
                                invalid_indices, public['source']['size'])
            result.update(native=proposal, validated_regions=proposed_regions,
                          corrected_response=corrected_response,
                          additional_native_planner_calls=1, generation_config=backend.runner.pipe.vlm_model.generation_config.to_dict())
        else:
            plan_path = out / 'plan/result.json'
            proposal = read(plan_path)
            if proposal['status'] != 'completed' or proposal['identity'] != identity:
                raise ValueError('No accepted correction bound to this failed request')
            corrected_response = proposal['corrected_response']
            validate_correction(regions, proposal['validated_regions'], original_global,
                                functions['extract_gen_image_prompt'](None, corrected_response),
                                invalid_indices, public['source']['size'])
            import torch
            from PIL import Image
            from samtok_benchmark.ifbench.canvas import restore_output

            save(stage_out / 'call.json', {'original_editor_request': call,
                 'corrected_response': corrected_response,
                 'correction_record_sha256': sha(plan_path),
                 'protocol_change': 'Use one validated native self-correction instead of the failed original plan'})
            load_tick = time.monotonic()
            backend = NativeBackend('replan', 'edit', config, stage_out)
            result['load_seconds'] = time.monotonic() - load_tick
            backend.reset()
            params = dict(call['parameters'])
            expand, switch = params.pop('expand_value'), params.pop('attention_switch_step')
            source = Image.open(call['editor_image']).convert('RGB')
            with torch.inference_mode():
                raw, _, detail = backend.runner.pipe.region_edit_with_attention(
                    source, call['prompt'], corrected_response, skip_save=True,
                    collect_latency=True, expand_value=expand, attention_switch_step=switch,
                    pipeline_kwargs={'generator': torch.Generator('cuda').manual_seed(call['seed']), **params})
            backend.synchronize()
            detail.pop('edited_image', None)
            raw.save(stage_out / 'raw.png')
            restored = restore_output(raw, item['geometry'])
            restored.save(stage_out / 'output.png')
            result.update(native_result=detail, raw_size=list(raw.size), output_size=list(restored.size),
                          raw_sha256=sha(stage_out / 'raw.png'), output_sha256=sha(stage_out / 'output.png'),
                          correction_record_sha256=sha(plan_path), diffusion_calls=1)
        result.update(status='completed', metrics=backend.metrics, memory=backend.memory(),
                      environment=backend.environment())
    except Exception as exc:
        result.update(error=repr(exc), traceback=traceback.format_exc())
    result['wall_seconds'] = time.monotonic() - tick
    save(stage_out / 'result.json', result)
    print(json.dumps({k: result.get(k) for k in ('status', 'error', 'wall_seconds')}, indent=2), flush=True)
    if result['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
