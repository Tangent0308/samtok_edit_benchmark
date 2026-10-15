"""Local VLM authoring assistance. Outputs are ALWAYS pending, never accepted."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from PIL import Image
from transformers import AutoProcessor
from vllm import LLM, SamplingParams

PROMPT='''You are proposing SA-1B benchmark photo edits, not approving them.
Image 1 is the clean photograph. Image 2 shows candidate masks: the target retains its original colors, the outside is dimmed, and a pink contour outlines the mask. The ID is the ORIGINAL annotation ID. Annotation category names can be WRONG; trust the pixels. The clean image on top of the sheet provides context.
Choose 2-5 targets with DIFFERENT PHYSICAL PARENT OBJECTS. Two body parts or garments on ONE person, two wheels of ONE vehicle, or windows of ONE building do not count as independent parents. A separately carried bag is an independent object. Masks must accurately select a real object/part; reject masks that fill background holes, include neighbors, select reflections/printed depictions as real objects, or cannot be grounded. Select targets supporting actual difficulty: thin structures, holes, occlusion, similar adjacent instances, small parts, or disconnected visible pieces. A busy background alone is not enough.
For each selected target author ONE natural everyday photo-edit request, concise and unambiguous. Choose operations among add, replace, remove, attribute. Use distinct operations for 2-4 targets and all four for 5 targets; never force an absurd edit to achieve balance. Prefer two or three strong targets over four marginal ones. Do NOT force an add task. Return reserve if fewer than two are suitable. A garment worn by a person has that person as parent; a separate backpack has the backpack itself as parent. Parts of one building share one building parent even if on different floors. Verify each chosen ID against its own labeled crop; do not describe a camera when the marked region is the shirt around it. A color or material-only replacement is an ATTRIBUTE, not REPLACE. Do not invent whimsical additions such as a bow tie on a distant skyscraper advertisement or objects balanced on narrow railings.
The ref must be the shortest unambiguous noun phrase beginning with 'the', grounded in the full image (position, owner, original color or ordinal within an explicit group when needed). No parenthetical location clauses. 'scope' is a short noun describing EXACTLY what the mask selects, without position, e.g. 'shirt sleeve', not generic 'object'.
ADD: existing mask is the DIRECT physical host where an addition rests/attaches; preserve host. Prefer on/in/attached to/tied around/mounted on, never distant reference anchors. Use placement.site only for a necessary host sublocation (front, neck, top rail...). Propose a small scene-appropriate item, not arbitrary stickers everywhere. REPLACE changes category/structure, not only color/material. ATTRIBUTE changes appearance preserving identity/shape (one color/material/finish/pattern). REMOVE a removable whole object; never amputate a body part or nonsensically remove clothing exposing a person.
Return JSON only, with status 'proposal' or 'reserve', scene_zh, evidence_zh, mechanisms (list), protected_content_zh, rejected_targets [{object_id,reason_zh}], and targets. Each target has object_id (integer from pictured IDs), parent (unique English parent identifier), parent_zh, operation, ref, ref_zh, scope, scope_zh, payload (English new object/attribute; empty for remove), payload_zh, attribute_kind (only attribute: color/material/finish/pattern), placement (only add: {relation,site,anchor_mode:'support'}), instruction_zh (one short complete imperative), instruction_noref_zh (same edit but replace ref with '选中的'+scope_zh). Do not claim acceptance or direct assistant/human review.''' 

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--limit',type=int,default=32);p.add_argument('--model',default='/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-Flash-Next-FP8');a=p.parse_args()
 output=a.root/'proposals';output.mkdir(exist_ok=True)
 dirs=[d for d in sorted((a.root/'candidates').iterdir()) if (d/'candidate.json').exists() and not (a.root/'decisions'/f'{d.name}.json').exists() and not (output/f'{d.name}.json').exists()][:a.limit]
 if not dirs: print('No pending candidates');return
 processor=AutoProcessor.from_pretrained(a.model)
 llm=LLM(model=a.model,dtype='bfloat16',tensor_parallel_size=4,max_model_len=16384,max_num_seqs=8,max_num_batched_tokens=8192,gpu_memory_utilization=.82,enforce_eager=True,trust_remote_code=True,limit_mm_per_prompt={'image':2,'video':0},mm_encoder_attn_backend='TORCH_SDPA',enable_prefix_caching=True,moe_backend='triton',enable_flashinfer_autotune=False,engram_config={'cpu_offload':True})
 for start in range(0,len(dirs),8):
  chunk=dirs[start:start+8];requests=[];meta=[]
  for d in chunk:
   row=json.loads((d/'source.json').read_text());c=json.loads((d/'candidate.json').read_text());objects={o['object_id']:o for o in row['objects']}
   width,height=Image.open(row['image_path']).size
   hints=[{'object_id':i,'category':objects[str(i)]['category'],'bbox_1000':[round(v/(width if k%2==0 else height)*1000) for k,v in enumerate(objects[str(i)]['bbox'])]} for i in c['object_ids']]
   prompt=PROMPT+'\nSource ID: '+d.name+'\nCandidate IDs and xyxy boxes normalized to 0..1000 relative to the clean image: '+json.dumps(hints)
   images=[Image.open(row['image_path']).convert('RGB'),Image.open(d/'candidate.jpg').convert('RGB')]
   images[0].thumbnail((1536,1536));images[1].thumbnail((1800,1800))
   messages=[{'role':'user','content':[{'type':'image'},{'type':'image'},{'type':'text','text':prompt}]}]
   text=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
   requests.append({'prompt':text,'multi_modal_data':{'image':images}});meta.append((d,row,prompt))
  began=time.monotonic();results=llm.generate(requests,SamplingParams(max_tokens=3000,temperature=.2),use_tqdm=False)
  elapsed=time.monotonic()-began
  for (d,row,prompt),result in zip(meta,results):
   raw=result.outputs[0].text
   record={'source_id':d.name,'status':'pending_direct_visual_review','model':a.model,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'source_sha256':sha(row['image_path']),'card_sha256':sha(d/'candidate.jpg'),'raw':raw,'batch_seconds':elapsed,'batch_size':len(chunk),'finish_reason':result.outputs[0].finish_reason}
   try:record['proposal']=json.loads(raw[raw.index('{'):raw.rindex('}')+1])
   except (ValueError,json.JSONDecodeError) as e:record['parse_error']=str(e)
   (output/f'{d.name}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps({'source_id':d.name,'status':record.get('proposal',{}).get('status','parse_error'),'targets':len(record.get('proposal',{}).get('targets',[]))}),flush=True)
  print(f'Batch {start//8+1}: {len(chunk)} sources in {elapsed:.1f}s',flush=True)
if __name__=='__main__':main()
