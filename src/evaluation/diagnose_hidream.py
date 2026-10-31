"""Small controlled HiDream inference probes; never overwrites benchmark runs."""
import argparse, json, time, sys, math, hashlib, os
from pathlib import Path
import torch
from PIL import Image

ROOT=Path.cwd(); EXP=Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
D=EXP/'diagnostics/hidream_noise_20261021'; D.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'evaluation/diffsynth'))
from adapters import _load, output_size
from prompt import build_prompt
# Isolated diagnostic dependency; do not change shared inference environments.
sys.path.insert(0, '/tmp/samtok-hidream-diagnostic-deps')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--engine',choices=['diffsynth','official'],default='diffsynth');ap.add_argument('--variants',nargs='+',default=['baseline']);ap.add_argument('--cases',nargs='+',default=['v2-sa_10006079']);a=ap.parse_args()
 legacy=EXP/'launch/hidream_2k_20261021/legacy_metadata'
 job_path=legacy/'judge_inputs/judge_jobs.jsonl' if legacy.exists() else EXP/'judge_inputs/hidream_o1_image/judge_jobs.jsonl'
 config_path=legacy/'runs/config.json' if legacy.exists() else EXP/'runs/hidream_o1_image/config.json'
 jobs={j['case_id']:j for j in map(json.loads,job_path.open())}
 config=json.loads(config_path.read_text());model_path='/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/HiDream-O1-Image'
 if a.engine=='diffsynth':
  pipe=_load(config);orig_model_fn=pipe.model_fn;orig_step=pipe.step;orig_noise=pipe.generate_noise
  ref_unit=next(u for u in pipe.units if hasattr(u,'get_sizes'));orig_sizes=ref_unit.get_sizes
  from diffsynth.diffusion import FlowMatchScheduler
  from diffsynth.models.hidream_common import patchify,unpatchify
 else:
  sys.path.insert(0,str(D/'official'))
  from transformers import AutoProcessor
  from models import qwen3_vl_transformers as om
  import models.pipeline as op
  from models.utils import find_closest_resolution
  from inference import add_special_tokens
  # Official code requests flash-attention, but this environment provides SDPA.
  # Preserve its two-pass attention and GQA semantics with the PyTorch kernel.
  def flash_sdpa(q,k,v,softmax_scale=None,causal=False,**kw):
   q=q.transpose(1,2);k=k.transpose(1,2);v=v.transpose(1,2)
   if q.shape[1]!=k.shape[1]:
    n=q.shape[1]//k.shape[1];k=k.repeat_interleave(n,dim=1);v=v.repeat_interleave(n,dim=1)
   return torch.nn.functional.scaled_dot_product_attention(q,k,v,scale=softmax_scale,is_causal=causal).transpose(1,2)
  om._flash_attn_func=flash_sdpa
  processor=AutoProcessor.from_pretrained(model_path);add_special_tokens(processor.tokenizer)
  pipe=om.Qwen3VLForConditionalGeneration.from_pretrained(model_path,torch_dtype=torch.bfloat16,device_map='cuda').eval()
 for cid in a.cases:
  job=jobs[cid]['public_job'];sw,sh=job['source_size'];w,h=output_size(sw,sh,1048576,16,16);ims=[Image.open(p).convert('RGB') for p in job['images']];prompt=build_prompt(job,'image')
  for variant in a.variants:
   dest=D/(a.engine+'_'+variant)/cid;dest.mkdir(parents=True,exist_ok=True)
   if (dest/'result.json').exists():print('SKIP',dest,flush=True);continue
   options=dict(prompt=prompt,negative_prompt=' ',cfg_scale=4.0,height=h,width=w,seed=0,rand_device='cuda',num_inference_steps=50,model_type='full',shift=3.0,noise_scale=8.0,edit_image=ims,keep_original_aspect=False)
   if variant in ['native_resolution','native_fp32','native_resolution_lowref']:
    sys.path.insert(0,str(D/'official'));from models.utils import find_closest_resolution
    options['width'],options['height']=find_closest_resolution(w,h)
   if variant=='cpu_noise':options['rand_device']='cpu'
   if variant=='simple_single':options['edit_image']=ims[:1];options['prompt']="Change the woman's yellow tank top to teal and remove the black bag from the boat. Keep everything else unchanged."
   steps=[];start=time.time();print('START',a.engine,variant,cid,options['width'],options['height'],flush=True)
   if a.engine=='diffsynth':
    pipe.scheduler=FlowMatchScheduler('HiDream-O1-Image');pipe.model_fn=orig_model_fn;pipe.step=orig_step;pipe.generate_noise=orig_noise;ref_unit.get_sizes=orig_sizes
    if variant=='native_resolution_lowref':
     ref_unit.get_sizes=lambda K,hh,ww:orig_sizes(K,math.ceil(h/32)*32,math.ceil(w/32)*32)
    if variant=='low_resolution_highref':
     sys.path.insert(0,str(D/'official'));from models.utils import find_closest_resolution
     nw,nh=find_closest_resolution(w,h);ref_unit.get_sizes=lambda K,hh,ww:orig_sizes(K,nh,nw)
    if variant=='cpu_noise':
     def fp32_noise(shape,seed=None,rand_device='cpu',rand_torch_dtype=None,**kw):return orig_noise(shape,seed=seed,rand_device='cpu',rand_torch_dtype=torch.float32,**kw)
     pipe.generate_noise=fp32_noise
    if variant in ['fp32_math','native_fp32','official_scheduler']:
     def stable_model_fn(dit,latents,timestep,input_ids,position_ids,token_types,vinput_mask,pixel_values=None,image_grid_thw=None,ref_patches=None,progress_id=0,**kw):
      b,c,hh,ww=latents.shape;x=patchify(latents);n=x.shape[1]
      if ref_patches is not None:x=torch.cat([x,ref_patches],dim=1)
      sigma=pipe.scheduler.timesteps[progress_id].float().to(latents.device).reshape(1)/1000
      out=dit(input_ids=input_ids,position_ids=position_ids,vinputs=x,timestep=1-sigma,token_types=token_types,pixel_values=pixel_values,image_grid_thw=image_grid_thw)
      xp=unpatchify(out.x_pred[0,vinput_mask[0]][:n].unsqueeze(0),hh,ww)
      return (latents.float()-xp.float())/sigma.clamp_min(.001)
     pipe.model_fn=stable_model_fn
     if variant=='official_scheduler':
      sys.path.insert(0,str(D/'official'));from models.fm_solvers_unipc import FlowUniPCMultistepScheduler
      class UniPC:
       training=False
       def set_timesteps(self,n,shift=3,**kw):
        self.inner=FlowUniPCMultistepScheduler(use_dynamic_shifting=False,shift=shift);self.inner.set_timesteps(n,device='cuda');self.timesteps=self.inner.timesteps;self.sigmas=self.inner.sigmas
       def step(self,model_output,timestep,sample,**kw):return self.inner.step(model_output.float(),timestep.float(),sample.float(),return_dict=False)[0]
      pipe.scheduler=UniPC()
    def instrumented_step(scheduler,latents,progress_id,noise_pred,**kw):
     if variant in ['fp32_math','native_fp32','official_scheduler']:
      result=scheduler.step(noise_pred.float(),scheduler.timesteps[progress_id],latents.float()).to(torch.bfloat16)
     else:result=orig_step(scheduler,latents,progress_id,noise_pred,**kw)
     x=result.float();steps.append({'step':progress_id,'t':float(scheduler.timesteps[progress_id]),'mean':x.mean().item(),'std':x.std().item(),'absmax':x.abs().max().item(),'finite':bool(x.isfinite().all())})
     return result
    pipe.step=instrumented_step
    result=pipe(**options)
   else:
    # Default is the unmodified official resolution snap and UniPC sampling.
    op.find_closest_resolution=find_closest_resolution
    if variant=='same_resolution':op.find_closest_resolution=lambda w,h:(math.ceil(w/32)*32,math.ceil(h/32)*32)
    def preview(i,n,fn):
     if i in [0,24,49]:fn().save(dest/f'prediction_{i:02d}.jpg',quality=85)
    result=op.generate_image(model=pipe,processor=processor,prompt=prompt,ref_image_paths=job['images'],height=h,width=w,num_inference_steps=50,guidance_scale=4,shift=3,seed=0,keep_original_aspect=False,callback=preview)
   result.save(dest/'native.png');result.resize((sw,sh),Image.Resampling.LANCZOS).save(dest/'output.png')
   summary={'engine':a.engine,'variant':variant,'case_id':cid,'seconds':time.time()-start,'native_size':result.size,'seed':0,'torch':torch.__version__,'cuda':os.environ.get('CUDA_VISIBLE_DEVICES'),'options':{k:v for k,v in options.items() if k!='edit_image'},'input_image_count':len(options['edit_image']), 'input_files':job.get('input_files'), 'ref_resolution_ablation':variant if variant in ['native_resolution_lowref','low_resolution_highref'] else None,'steps':steps,'official_attention_backend':'torch SDPA shim' if a.engine=='official' else None}
   (dest/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print('DONE',a.engine,variant,cid,round(summary['seconds'],2),flush=True)
if __name__=='__main__':main()
