"""Render seven-model figures and reviewed report sections from frozen evaluation files.

Run from the repository root after analyze_results.py --tables-only.
CPU-only rendering; does not invoke editors or change judge scores.
"""
from pathlib import Path
from collections import Counter
import csv, json, math, importlib.util, shutil, xml.etree.ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

ROOT=Path.cwd(); PUB=ROOT/'docs/publication/2.6.0'; AS=PUB/'assets'; REPORT=ROOT/'docs/reports/2.6.0'
EXP=Path('/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines')
MODELS={'flux3_klein':'FLUX.3 Klein','qwen_image_21':'Qwen-Image-2.1','flux2_klein_4b':'FLUX.2 Klein-4B','longcat_image_edit':'LongCat-Image-Edit','qwen_image_edit_2511':'Qwen-Image-Edit-2511','hidream_o1_image':'HiDream-O1-Image','step1x_edit':'Step1X-Edit'}
SHORT=['FLUX.3 Klein','Qwen-Image-2.1','FLUX.2 Klein-4B','LongCat','Qwen Edit 2511','HiDream-O1','Step1X-Edit']
COLORS=['#8A61AF','#3575B4','#419881','#B65B74','#D18A26','#846B55','#697A9C']
def jl(p):return [json.loads(s) for s in p.open() if s.strip()]
def csvrows(name):return list(csv.DictReader((REPORT/name).open()))
main=csvrows('main_table.csv'); kd=csvrows('k_jointpass.csv'); loc=csvrows('locator_impact.csv'); fail=csvrows('failure_modes.csv')
reports={m:json.loads((EXP/'judge'/m/'Qwen3.8-Flash-Next-FP8/report.json').read_text()) for m in MODELS}
jobs={m:{j['case_id']:j for j in jl(EXP/'judge_inputs'/m/'judge_jobs.jsonl')} for m in MODELS}
cases={c['id']:c for c in jl(ROOT/'data/v2_2.6.0/cases.jsonl')}; ks=Counter(len(c['units']) for c in cases.values())
notes=json.loads((PUB/'case_study_notes.json').read_text())['models']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#A3ABB7','text.color':'#202C3D','axes.labelcolor':'#334155','xtick.color':'#475569','ytick.color':'#475569','figure.facecolor':'white','savefig.facecolor':'white','pdf.fonttype':42})
def save(fig,name):
 for ext in ['png','pdf']:
  fig.savefig(AS/(name+'.'+ext),dpi=160,bbox_inches='tight');shutil.copy2(AS/(name+'.'+ext),REPORT/'figures'/(name+'.'+ext))
 plt.close(fig)
def grid(ax):ax.set_axisbelow(True);ax.grid(axis='y',color='#E8EDF2',lw=.7)
fig,axs=plt.subplots(1,2,figsize=(12,5.2),gridspec_kw={'width_ratios':[1,1.5]},layout='constrained')
y=np.arange(len(MODELS));a=axs[0];bars=a.barh(y,[float(r['joint_rate'])*100 for r in main],color=COLORS,height=.58);a.set_yticks(y,SHORT);a.invert_yaxis();a.bar_label(bars,fmt='%.2f%%',padding=5,fontsize=10);a.set_xlim(0,31);a.set_xlabel('JointPass (%)');a.set_title('a  All requests + global checks',loc='left',fontweight='bold')
a=axs[1];vals=np.array([[float(r[k])*100 for k in ['E_unit_rate','P_unit_rate','Q_unit_rate','global_P_rate','global_Q_rate']] for r in main]);a.imshow(vals,vmin=0,vmax=100,cmap='Blues',aspect='auto');a.set_xticks(range(5),['Unit E','Unit P','Unit Q','Global P','Global Q']);a.set_yticks(range(7),SHORT);a.tick_params(length=0);a.set_title('b  Dimension pass rates (%)',loc='left',fontweight='bold')
for i in range(7):
 for j in range(5):a.text(j,i,f'{vals[i,j]:.1f}',ha='center',va='center',color='white' if vals[i,j]>60 else '#16314D',fontsize=11)
for sp in a.spines.values():sp.set_visible(False)
save(fig,'main_results')
fig,axs=plt.subplots(2,4,figsize=(13,7.0),layout='constrained')
for i,m in enumerate(MODELS):
 a=axs.flat[i];rows=[r for r in kd if r['model_key']==m];x=[int(r['K']) for r in rows];actual=[float(r['measured_joint_rate'])*100 for r in rows];prod=[float(r['p_u_product'])*100 for r in rows]
 allu=[100*np.mean([all(all(u[d]['pass'] for d in 'EPQ') for u in c['units']) for c in reports[m]['case_results'] if c['expected_units']==k]) for k in x]
 a.plot(x,actual,'o-',color=COLORS[i],lw=2,label='JointPass');a.plot(x,prod,'s--',color='#566476',lw=1.3,ms=4,label='Product of unit marginals');a.plot(x,allu,':',color=COLORS[i],lw=1.8,label='All units pass (no globals)');a.set_title(SHORT[i],loc='left',fontweight='bold');a.set_xticks(x,[f'{k}\n(n={ks[k]})' for k in x]);a.set_ylim(-1,58);a.set_xlabel('Targets K');grid(a)
 a.text(.96,.92,f'JointPass K=2: {actual[0]:.2f}%\nK=5: {actual[-1]:.2f}%',ha='right',va='top',transform=a.transAxes,fontsize=9)
 if i%4==0:a.set_ylabel('Pass rate (%)')
a=axs.flat[7];a.axis('off');h,l=axs.flat[0].get_legend_handles_labels();a.legend(h,l,loc='upper left',frameon=False,fontsize=9);a.text(0,.54,'Same y-axis across all models.\n\nMarginals are estimated within K.\nDifferences are descriptive;\nnot a causal interference estimate.',va='top',fontsize=9,color='#64748B',linespacing=1.5);save(fig,'composition')
def metric(m,g):return float(next(r for r in loc if r['model_key']==m and r['group']==g)['unit_joint_rate'])*100
fig,axs=plt.subplots(1,2,figsize=(12,5.2),gridspec_kw={'width_ratios':[1.3,1]},layout='constrained')
a=axs[0]
for i,m in enumerate(MODELS):
 ref,noref=metric(m,'ref'),metric(m,'no-ref');a.plot([noref,ref],[i,i],color=COLORS[i],lw=2);a.scatter(ref,i,color=COLORS[i],s=55,marker='o');a.scatter(noref,i,color=COLORS[i],s=55,marker='v');a.text(max(ref,noref)+2,i,f'{ref-noref:.2f} pp',va='center',fontsize=9)
a.set_yticks(range(7),SHORT);a.invert_yaxis();a.set_xlim(0,94);a.set_xlabel('UnitPass (%)');a.set_title('a  Reference vs. blind reference',loc='left',fontweight='bold');a.scatter([],[],color='#475569',marker='o',label='ref');a.scatter([],[],color='#475569',marker='v',label='no-ref');a.legend(loc='lower right',frameon=False);a.grid(axis='x',color='#E8EDF2');a.set_axisbelow(True)
a=axs[1];v=np.array([[metric(m,g) for g in ['point','box','mask']] for m in MODELS]);a.imshow(v,vmin=0,vmax=75,cmap='Blues',aspect='auto');a.set_xticks(range(3),['Point','Box','Mask']);a.set_yticks(range(7),SHORT);a.tick_params(length=0);a.set_title('b  Locator subgroups · UnitPass (%)',loc='left',fontweight='bold')
for i in range(7):
 for j in range(3):a.text(j,i,f'{v[i,j]:.2f}',ha='center',va='center',color='white' if v[i,j]>45 else '#16314D',fontsize=11)
for sp in a.spines.values():sp.set_visible(False)
fig.supxlabel('Micro-averages over units; locator groups are not paired versions of the same targets.',fontsize=9,color='#64748B');save(fig,'localization')
cats=['locator marker in output','not executed','occluded fragments/leftovers','wrong instance','wrong granularity','other E failure'];names=['Marker residue','Not executed','Fragments / leftovers','Wrong instance','Wrong granularity','Other'];palette=['#C6635C','#E2B468','#7097BA','#8D78B4','#78A391','#C9CED5']
fig,axs=plt.subplots(2,4,figsize=(12,6.8),layout='constrained')
for i,m in enumerate(MODELS):
 a=axs.flat[i];d={r['category']:int(r['count']) for r in fail if r['model_key']==m};total=sum(d.values());bottom=0
 for cat,name,col in zip(cats,names,palette):
  v=d.get(cat,0)/total*100;a.bar([0],[v],bottom=bottom,color=col,width=.65,label=name)
  if v>=8:a.text(0,bottom+v/2,f'{v:.0f}%',ha='center',va='center',fontsize=10)
  bottom+=v
 a.set_xlim(-.8,.8);a.set_xticks([]);a.set_title(f'{SHORT[i]}\n{total:,} E-failed units',fontsize=11);a.set_ylim(0,100)
 if i%4==0:a.set_ylabel('Share of E-failed units (%)')
a=axs.flat[7];a.axis('off');h,l=axs.flat[0].get_legend_handles_labels();a.legend(h,l,loc='upper left',frameon=False,fontsize=9);a.text(0,.23,'Heuristic, exclusive categories.\nNot a full-output residue rate.\nEvidence-based screening;\nnot a causal attribution.',va='top',fontsize=9,color='#64748B');save(fig,'failure_modes')

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def font(n):return ImageFont.truetype(FONT,n)
def put(canvas,im,x,y,w,h):
 im=im.convert('RGB');im.thumbnail((w,h),Image.Resampling.LANCZOS);canvas.paste(im,(x+(w-im.width)//2,y+(h-im.height)//2))
cid='v2-sa_10044652';j=jobs['qwen_image_21'][cid];p=Image.new('RGB',(1800,800),'white');d=ImageDraw.Draw(p)
d.text((28,15),'TWO-IMAGE INPUT / visual_locator_v2 · mixed',font=font(30),fill='#183249')
for i,(path,label) in enumerate(zip(j['public_job']['images'],['Image 1: clean source','Image 2: point + box + mask'])):
 d.text((30+i*900,76),label,font=font(26),fill='#334155');put(p,Image.open(path),25+i*900,125,850,550)
d.text((28,705),'FLUX.3 Klein | Qwen-Image-2.1 | FLUX.2 Klein-4B',font=font(25),fill='#334155');d.text((28,750),'Qwen-Image-Edit-2511 | HiDream-O1-Image',font=font(25),fill='#334155');p.save(AS/'actual_inputs.jpg',quality=86,optimize=True,progressive=True)
p=Image.new('RGB',(1800,780),'white');d=ImageDraw.Draw(p);d.text((28,15),'SINGLE-IMAGE INPUT / visual_locator_v2 · mixed',font=font(30),fill='#183249')
input_evidence={}
for i,m in enumerate(['longcat_image_edit','step1x_edit']):
 job=jobs[m][cid];path=job['public_job']['images'][-1];im=Image.open(path).convert('RGB');original=im.size
 if m=='step1x_edit':
  ratio=im.width/im.height;w=math.sqrt(1048576*ratio);im=im.resize((round(w/16)*16,round(w/ratio/16)*16),Image.Resampling.LANCZOS)
 input_evidence[m]={'case_id':cid,'input_file':path,'source_size':original,'adapter_image_size':im.size,'clean_source_passed':False}
 d.text((30+i*900,76),MODELS[m]+' / only image',font=font(26),fill='#334155');put(p,im,25+i*900,125,850,550);d.text((30+i*900,703),f'Adapter input: {im.width} x {im.height}',font=font(23),fill='#475569')
d.text((28,746),'Both receive the marked photo only; no clean reference image is passed.',font=font(23),fill='#475569');p.save(AS/'single_inputs.jpg',quality=86,optimize=True,progressive=True)
(PUB/'actual_input_evidence.json').write_text(json.dumps(input_evidence,ensure_ascii=False,indent=2)+'\n')

# Shared authoring tree gives identical text, tables and images to Markdown and Lark.
nodes=[];md=[]
def h(level,s):e=ET.Element('h'+str(level));e.text=s;nodes.append(e);md.append('#'*level+' '+s)
def p(s):e=ET.Element('p');e.text=s;nodes.append(e);md.append(s)
def image(path,caption):
 path=Path(path);e=ET.Element('img',{'path':'@./'+str(path.relative_to(ROOT)),'caption':caption,'name':path.name});nodes.append(e);md.append(f'![{caption}]({path.relative_to(PUB)})')
def table(headers,rows):
 t=ET.Element('table');th=ET.SubElement(t,'thead');tr=ET.SubElement(th,'tr')
 for s in headers:ET.SubElement(ET.SubElement(tr,'th'),'p').text=str(s)
 tb=ET.SubElement(t,'tbody')
 for row in rows:
  tr=ET.SubElement(tb,'tr')
  for s in row:ET.SubElement(ET.SubElement(tr,'td'),'p').text=str(s)
 nodes.append(t);md.append('\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows]))
def pct(x):return f'{float(x)*100:.2f}%'
h(2,'4. 评测设置与评分');h(3,'4.1 模型输入与推理')
p('七个模型均保留 visual_locator_v2 / mixed 的原始 point、box、mask 与 U 标签。五个模型接收干净原图和定位图两张图；LongCat、Step1X 的适配器只向单图编辑接口传入带标记的原图。公开 job 中保存两张图，不代表每个 pipeline 都接收到两张。')
image(AS/'actual_inputs.jpg','实际双图输入：FLUX.3、Qwen-Image-2.1、FLUX.2、Qwen-Image-Edit-2511、HiDream')
image(AS/'single_inputs.jpg','实际单图输入：LongCat 与 Step1X；未传入干净原图')
table(['模型','实际输入','推理入口 / checkpoint','Steps / guidance'],[
 ['FLUX.3 Klein','干净图 + 定位图','BFL reference pipeline + prompt upsampler','16（distilled）'],
 ['Qwen-Image-2.1','干净图 + 定位图','DiffSynth QwenImage21Pipeline','40 / CFG 1.0'],
 ['FLUX.2 Klein-4B','干净图 + 定位图','DiffSynth Flux2ImagePipeline','4 / guidance 1.0'],
 ['LongCat-Image-Edit','仅定位图','Diffusers LongCatImageEditPipeline','50 / guidance 4.5'],
 ['Qwen-Image-Edit-2511','干净图 + 定位图','DiffSynth QwenImagePipeline','40 / CFG 4.0'],
 ['HiDream-O1-Image','干净图 + 定位图','DiffSynth HiDreamO1ImagePipeline；full','50 / CFG 4.0'],
 ['Step1X-Edit','仅定位图','DiffSynth FluxImagePipeline；step1x-edit-i1258','28 / CFG 6.0']])
p('统一 seed=0。Step1X 在适配器内按源图比例缩放到约 1 MP、16 像素对齐；LongCat 把原尺寸定位图交给 pipeline 预处理；HiDream 按官方宽高比分桶生成约 4 MP 图像（resolution_policy=hidream_official_2k_buckets_v1，32 像素对齐），其余使用各自配置的约 1 MP 目标尺寸。最终输出映射回源图坐标。HiDream 使用 Full 权重、shift=3、noise_scale=8、keep_original_aspect=False。各模型不是等算力比较；单图/双图条件不同，排名包含输入适配的影响。')
p('双图 prompt 指明图 1 是待编辑照片、图 2 仅用于定位；单图 prompt 指明在标记下的照片上编辑并去除标记。两者均按 U 绑定颜色与定位形式，要求同时执行全部指令。Qwen-Image-Edit-2511 使用 Picture 1/2，其余双图模型使用 Image 1/2；FLUX.3 另经过官方 prompt 扩展。单图 prompt 中“不要保留任何颜色”的英文措辞也可能产生歧义，其影响尚未做隔离验证。')
p('HunyuanImage 尚无完整评测结果，未纳入表格。HiDream 使用上述约 4 MP 配置完成全部 1,084 个 case 的生成与评分（2026-10-21 完成）；本文指标、图表和所有案例列均对应这批结果。')
h(3,'4.2 Judge 与指标')
p('Judge 为 Qwen3.8-Flash-Next-FP8，通过 vLLM 以 TP=8、temperature=0、seed=0 调用。每个 case 联合评判全部 U，查看源图/输出全图及同坐标局部图，结合私有 gold 指代、完成要求和保护契约评分。私有 mask 与契约不输入编辑模型。')
table(['维度','判断内容','通过阈值'],[['E：执行','正确实例/部件，完整操作、数量与可见碎块','4/4'],['P：保持','非目标部件、邻近物、遮挡与背景保持','≥3/4'],['Q：质量','结构、材质、边缘、接触与光影自然','≥3/4'],['global_P / global_Q','整图保持 / 整体质量','≥3/4']])
p('UnitPass = E∧P∧Q；JointPass = 所有 U 的 UnitPass ∧ global_P ∧ global_Q。单元指标按 3,872 个 U 微平均，全图指标按 1,084 个 case 平均。七个模型均有 1,084 条有效评分；新增三模型共 3,252 条，解析错误为 0。评分成功只表示记录有效，不代表编辑成功。')
p('冻结 rubric 仍有一处“no-ref 保留部件类型”的历史表述，与协议 2.0 不完全一致；judge 同时获得 gold 指代和完成契约，本文沿用原评分口径。')
h(3,'4.3 数据与结果路径')
p('Manifest：data/v2_2.6.0/cases.jsonl；SHA256：818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb。数据根：/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2。')
p('评测结果根：'+str(EXP)+'。以下路径相对于该目录；model_key 见表。')
table(['模型','model_key'],[[name,m] for m,name in MODELS.items()])
p('公开输入：inputs/visual_locator_v2_mixed/jobs.jsonl；实际适配参数：runs/<model_key>/config.json；生成登记：runs/<model_key>/outputs.jsonl；原始图：runs/<model_key>/shards/shardXX/images/；评分输入：judge_inputs/<model_key>/judge_jobs.jsonl；逐条分数与汇总：judge/<model_key>/Qwen3.8-Flash-Next-FP8/{scores.jsonl,report.json}。')
p('HiDream 本批运行记录：launch/hidream_2k_20261021/{status.json,queue.log,run_environment.json}；对应生成和评分均位于上述 hidream_o1_image 路径。')
p('仓库报告：docs/reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md；配套 CSV 与失败证据同目录。图像和逐模型案例审查记录：docs/publication/2.6.0/assets/、case_study_notes.json、model_case_studies.json；适配器 prompt 示例：actual_adapter_prompts.json。')
h(2,'5. 结果与分析');h(3,'5.1 整体表现');image(AS/'main_results.png','七模型主结果：JointPass 与单元、全图通过率')
table(['模型','JointPass','E','P','Q','global_P','global_Q'],[[r['model'],f"{r['joint_pass']}/{r['cases']} ({pct(r['joint_rate'])})"]+[pct(r[k]) for k in ['E_unit_rate','P_unit_rate','Q_unit_rate','global_P_rate','global_Q_rate']] for r in main])
p('FLUX.3 仍最好，但 JointPass 仅 24.91%。LongCat 的 E=42.41%，与 FLUX.2 的 42.15% 接近，P/Q 则低至 32.57%/43.08%，表明完成操作之外的保持与质量也构成瓶颈。HiDream 有 13 个 case 通过（1.20%），单元 E=27.69%，低于 P=58.68% 与 Q=54.08%；执行不足仍是主要瓶颈，global_P/Q 也仅为 17.71%/21.40%。Step1X 仅 1 个 case 通过。')
h(3,'5.2 多目标组合');image(AS/'composition.png','JointPass 随目标数 K 变化，与单元边际通过率乘积对照')
p('FLUX.3 在 K=2→5 时从 46.26% 降至 3.53%；其余六模型在 K=5 均为 0/85。LongCat 的 K=2/3/4/5 分别为 6.12%/3.14%/0.67%/0%；HiDream 分别为 4.08%/1.96%/0.34%/0%；Step1X 仅 K=2 有 1/147 通过。')
p('在同一模型、同一 K 的 case 中，p_u 是 Uu 的 UnitPass 比例；∏u p_u 是假定各位置独立时“全部单元通过”的参考值。例如 LongCat 在 K=2 时乘积为 6.64%，JointPass 为 6.12%；K=3 时乘积为 0.93%，JointPass 反而为 3.14%。因此不能统一声称实测低于独立期望。')
p('图中彩色点线展示不含 global 门槛的“全部 U 通过”，便于与乘积比较。单元边际来自多目标任务，且各 K 场景不同；共享难度、成功相关性和全图门槛都会影响差值，不能直接作为请求间干扰的因果估计。')
h(3,'5.3 定位方式');image(AS/'localization.png','ref/no-ref 与 point/box/mask 的 UnitPass')
locrows=[]
for m,name in MODELS.items():
 ref,noref=metric(m,'ref'),metric(m,'no-ref');locrows.append([name,f'{ref:.2f}%',f'{noref:.2f}%',f'{noref-ref:.2f} pp']+[f'{metric(m,g):.2f}%' for g in ['point','box','mask']])
table(['模型','ref','no-ref','no-ref − ref','point','box','mask'],locrows)
p('LongCat 的 no-ref 相比 ref 下降 15.89 个百分点，point 子组仅 12.83%。HiDream 从 ref 的 28.30% 降至 no-ref 的 12.41%，下降 15.89 个百分点；point/box/mask 分别为 19.96%/21.16%/23.06%。Step1X 的 ref/no-ref 差距仅 3.39 个百分点，但绝对通过率很低，不能据此认为视觉定位更强。')
p('no-ref 为 1,660 个单元的微平均（point 554、box/mask 各 553），不是三个独立 setting 的平均。ref 共 2,212 个单元，包含 none；point/box/mask 列混合 ref 与 no-ref。各子组并非同目标配对，差值同时受样本难度影响。')
h(3,'5.4 失败模式');image(AS/'failure_modes.png','七模型 E 失败单元的启发式互斥分类')
table(['模型','E 失败数','标记','未执行','碎块/残留','实例','粒度','其他'],[[name,sum(int(r['count']) for r in fail if r['model_key']==m)]+[next((int(r['count']) for r in fail if r['model_key']==m and r['category']==c),0) for c in cats] for m,name in MODELS.items()])
p('当前案例可确认的失败原因如下（对应第 6 节图片）：')
reasons=[
'1. 遗漏或做错操作：FLUX.3 的包未删除，只变为蓝色；FLUX.2 的红长椅未改绿；Step1X 的远处车辆仍在。',
'2. 实例/部位选错：FLUX.3 把莲花放到另一只手；Qwen-Image-2.1 把椅背而非木框改黑；LongCat 将中间整尊雕像改金，右侧目标皇冠仍为原色。',
'3. 多请求串位：FLUX.2 将 U4 的白鞋要求应用到 U2；Qwen-Image-Edit-2511 将 U1 的喇叭袖要求应用到 U2 人物。',
'4. 超出编辑范围：Qwen-Image-Edit-2511 对只授权改色的外套改了袖型；Step1X 将皇冠改金扩大到多个雕像。',
'5. 标记被生成：Qwen-Image-2.1 的胸前红点、Qwen-Image-Edit-2511 的红框/U 标签、LongCat 的红底文字，以及 Step1X 的框/标签均出现在原始输出。它们可在 E 通过时仍导致 P/Q 失败。',
'6. 结构与非目标内容被改动：Step1X 用平面青色色块代替夹克；HiDream 漏改黄色背心、未删除背包，并额外生成记号笔；另一例把喇叭袖改到另一只手臂，同时改变姿势。']
for s in reasons:p(s)
p('计数沿用旧分类器：仅筛选 E 失败单元，按标记→未执行→碎块→实例→粒度→其他的关键词优先级互斥归类；可观察原因可同时出现。标记计数不是全部输出的残留率，E 通过但 P/Q 失败的标记例子被排除。碎块类可能命中证据中对遮挡的描述，不等于全部经人工确认的碎块遗漏。')
p('HiDream 的 2,800 个 E 失败单元中，1,838 个被归为未执行（65.64%），374 个归为标记残留，179 个归为粒度错误。人工查看的两例可见漏改、错部位和额外生成物体；记号笔由何种机制产生，尚不能仅凭这些案例确定。')
h(2,'6. 案例研究：按模型表现分析')
p('按本次全量 JointPass 从高到低排列，每个模型两例，共 14 组模型—案例组合，涉及 7 张源图；复用场景便于跨模型对照。选例用于诊断，不代表失败比例。总览分两行：上行为 FLUX.3、Qwen-Image-2.1、FLUX.2、LongCat；下行为 Qwen-Image-Edit-2511、HiDream、Step1X；每行重复原图和定位图方便对照。')
p('总览展示原始输出，仅缩放压缩，未添加 mask 轮廓；局部图叠加红色源 mask 轮廓并标出每个 U 的 E/P/Q。浅蓝外框与 * 指示当前分析模型。LongCat、Step1X 只收到定位图，其余五模型收到两图；请勿把局部红轮廓误认为模型生成标记。')
for rank,(m,name) in enumerate(MODELS.items(),1):
 g=reports[m]['groups']['mixed/all'];h(3,f"6.{rank} {name}｜JointPass {pct(g['joint_success_rate'])}");p('单元 E/P/Q 通过率：'+' / '.join(f"{g['dimension_rates'][d]['unit_micro_rate']*100:.2f}" for d in 'EPQ')+'（%）。'+notes[m]['summary'])
 for n,c in enumerate(notes[m]['cases'],1):
  cid=c['case_id'];stem=m+'_'+cid;h(4,f"案例 {n}：{c['title']}");p('Case：'+cid+'。'+c['analysis']);image(AS/'model_cases'/(stem+'_overview.jpg'),name+' · '+cid+' · 原图、定位图与七模型原始输出')
  for u in cases[cid]['units']:
   ref=u['interaction']['has_ref'];key='instruction_ref' if ref else 'instruction_noref';h(5,u['id']+' · '+('ref' if ref else 'no-ref')+' / '+u['interaction']['locator']);p(u[key]);p(u[key+'_zh']);image(AS/'model_cases'/(stem+'_'+u['id']+'.jpg'),cid+' '+u['id']+' · 局部源 mask 轮廓与逐模型 E/P/Q')
xml='\n'.join(ET.tostring(n,encoding='unicode') for n in nodes);(PUB/'.seven-report.xml').write_text(xml);(PUB/'.seven-report.md').write_text('\n\n'.join(md)+'\n')
report='# SAMTok Edit Benchmark 2.6.0 结果分析\n\n更新：2026-10-22。七个模型各完成 1,084 个 case；本报告统计冻结的 visual_locator_v2 / mixed 运行结果。\n\n'+'\n\n'.join(md)
# In the standalone results report, settings/results/cases become sections 1/2/3.
import re
report=re.sub(r'^(#{2,5}) ([456])(?=[. ])',lambda m:m[1]+' '+str(int(m[2])-3),report,flags=re.M).replace('第 6 节','第 3 节')
report=re.sub(r'\]\((assets/[^)]+)\)',r'](../../publication/2.6.0/\1)',report)
(REPORT/'RESULT_ANALYSIS_2_6_0_ZH.md').write_text(report+'\n')
# Actual adapter-level prompt examples; FLUX.3 internal upsampler text is not archived.
spec=importlib.util.spec_from_file_location('pubprompt',ROOT/'src/evaluation/diffsynth/prompt.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
selected=sorted({c['case_id'] for v in notes.values() for c in v['cases']}|{cid})
prompts={c:{m:(mod.build_single_image_locator_prompt(jobs[m][c]['public_job']) if m in ['longcat_image_edit','step1x_edit'] else mod.build_prompt(jobs[m][c]['public_job'],'picture' if m=='qwen_image_edit_2511' else 'image')) for m in MODELS} for c in selected}
(PUB/'actual_adapter_prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2)+'\n')
(PUB/'figure_provenance.json').write_text(json.dumps({'experiment_root':str(EXP),'manifest_sha256':reports['flux3_klein']['manifest_sha256'],'model_keys':list(MODELS),'protocol':'visual_locator_v2','variant':'mixed','single_image_models':['longcat_image_edit','step1x_edit'],'case_selection':'case_study_notes.json','overview':'Original outputs, resized and JPEG-compressed only.','details':'Fixed-coordinate evaluator crops with red source-mask contour.','charts':'Frozen scores/reports; unchanged heuristic failure classification.','limitations':['Single-image and two-image inputs differ.','HiDream uses official approximately 4 MP resolution buckets; other model resolutions differ.','Marginal product is not a causal interference estimate.']},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'models':len(MODELS),'case_selections':sum(len(x['cases']) for x in notes.values()),'images_in_updated_sections':sum(n.tag=='img' for n in nodes),'xml':str(PUB/'.seven-report.xml')},ensure_ascii=False))
