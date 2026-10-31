"""Read-only progress for the corrected HiDream full evaluation."""
import json
from pathlib import Path

EXP = Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
LAUNCH = EXP / 'launch/hidream_2k_20261021'
state = json.loads((LAUNCH / 'status.json').read_text())
stages = {'generation': 'HiDream 生成', 'prepare_judge': '构建 judge 裁剪证据',
          'judge': 'Qwen3.8 judge', 'report': '校验并汇总结果', 'complete': '全部完成', 'failed': '任务失败'}
print('当前阶段:', stages.get(state['stage'], state['stage']))
print('生成配置: HiDream-O1-Image Full / 官方约 4 MP / 50 steps / CFG 4 / GPU 0–7')
counts = {p.name: len(list((p / 'images').glob('*.png'))) for p in sorted((EXP / 'runs/hidream_o1_image/shards').glob('shard*'))}
print(f'已保存生成图: {sum(counts.values())}/1084（生成完成前为文件计数）')
print('各卡:', ' | '.join(f'{k}: {v}' for k, v in counts.items()))
print(f"Judge 有效记录: {state.get('judge_ok', 0)}/1084；待补解析: {state.get('judge_parse_errors', 0)}")
print('状态更新时间 UTC:', state.get('updated_at'))
if state.get('error'):
    print('错误:', state['error'])
try:
    cleanup = json.loads((LAUNCH / 'cleanup_manifest.json').read_text())
    size = sum(item.get('deleted_bytes', 0) for item in cleanup['directories'])
    print(f"错误版本清理: {cleanup['status']}；已确认删除 {size / 1024 ** 3:.2f} GiB")
except (OSError, ValueError):
    print('错误版本清理: 正在更新记录')
print('日志目录:', LAUNCH)
