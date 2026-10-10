'use strict';
const $=id=>document.getElementById(id), colors=['#e72d52','#008cdb','#00a966','#c88400'];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let index=[],filtered=[],reviews={},metadata={},current=null,source=null,position=0,version=0,activeUnit=null,viewModes={},maskCache=new Map(),dirty=false;
async function json(url,options){const response=await fetch(url,{cache:'no-store',...options});const value=await response.json();if(!response.ok)throw new Error(value.error||`HTTP ${response.status}`);return value}
function fail(error){$('error').textContent=error.message||String(error)}
function image(url){return new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(new Error(`图片加载失败：${url}`));im.src=url})}
function mode(u){return (u.interaction.has_ref?'ref':'no-ref')+'+'+(u.interaction.locator==='none'?'only':u.interaction.locator)}
function setDirty(){dirty=true;$('save-state').textContent='有未保存修改'}
function rows(){
 $('list-count').textContent=`${filtered.length} 条 / 共 ${index.length} 条`;
 $('cases').innerHTML=filtered.map(c=>`<button class="case-row ${current?.id===c.id?'active':''}" data-case="${esc(c.id)}"><strong>${String(c.index+1).padStart(3,'0')} · ${esc(c.id)}</strong><small>${esc(c.dataset)} · ${c.objects} 对象 · ${esc(c.operations.join(' / '))}</small><small class="state">${({pending:'未审核',accept:'保留',revise:'待修改',reject:'剔除'})[reviews[c.id]?.decision||'pending']}</small></button>`).join('');
 for(const b of document.querySelectorAll('[data-case]'))b.onclick=()=>select(b.dataset.case);
 $('position').textContent=filtered.length?`${position>=0?position+1:'—'} / ${filtered.length}`:'0 / 0';
}
function filter(){const query=$('search').value.toLowerCase();filtered=index.filter(c=>(!$('dataset').value||c.dataset===$('dataset').value)&&(!$('count').value||c.objects===+$('count').value)&&(!$('status').value||(reviews[c.id]?.decision||'pending')===$('status').value)&&(!query||JSON.stringify(c).toLowerCase().includes(query)));position=filtered.findIndex(c=>c.id===current?.id);rows()}
function fit(){if(!source)return;const width=Math.min(source.width,Math.max(180,$('viewport').clientWidth-2));$('viewer').style.width=`${Math.round(width*+$('zoom').value)}px`}
async function coloredMask(u,color){
 if(maskCache.has(u.id))return maskCache.get(u.id);
 const promise=(async()=>{const raw=await image(u.target.mask);const canvas=document.createElement('canvas');canvas.width=raw.width;canvas.height=raw.height;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(raw,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);const rgb=color.match(/\w\w/g).map(x=>parseInt(x,16));for(let i=0;i<pixels.data.length;i+=4){const a=pixels.data[i];pixels.data[i]=rgb[0];pixels.data[i+1]=rgb[1];pixels.data[i+2]=rgb[2];pixels.data[i+3]=Math.round(a*.4)}ctx.putImageData(pixels,0,0);return canvas})();maskCache.set(u.id,promise);return promise
}
let drawSerial=0;
async function draw(){
 if(!source||!current)return;const ticket=++drawSerial,caseVersion=version,c=current,src=source;
 try{const layers=await Promise.all(c.units.map(async(u,i)=>({u,i,mode:viewModes[u.id]||'none',mask:viewModes[u.id]==='mask'?await coloredMask(u,colors[i]):null})));if(ticket!==drawSerial||caseVersion!==version)return;
 const canvas=$('viewer');canvas.width=src.width;canvas.height=src.height;const ctx=canvas.getContext('2d');ctx.drawImage(src,0,0);const line=Math.max(2,Math.min(src.width,src.height)/180),font=Math.max(12,Math.min(src.width,src.height)/30);ctx.lineWidth=line;ctx.font=`bold ${font}px sans-serif`;
 for(const {u,i,mode,mask} of layers){if(mode==='none')continue;ctx.strokeStyle=colors[i];ctx.fillStyle=colors[i];let [x,y]=u.target.point;if(mode==='mask')ctx.drawImage(mask,0,0);else if(mode==='box'){const [x1,y1,x2,y2]=u.target.box;ctx.strokeRect(x1+.5,y1+.5,x2-x1-1,y2-y1-1);[x,y]=[x1,y1]}else{ctx.beginPath();ctx.arc(x,y,line*2.5,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=Math.max(1,line*.6);ctx.stroke();ctx.lineWidth=line}const tw=ctx.measureText(u.id).width+8,th=font+7,lx=Math.max(0,Math.min(x+7,src.width-tw)),ly=Math.max(th,Math.min(y-7,src.height));ctx.fillStyle=colors[i];ctx.fillRect(lx,ly-th,tw,th);ctx.fillStyle='#fff';ctx.fillText(u.id,lx+4,ly-5)}fit();$('viewer').dataset.modes=JSON.stringify(viewModes);
 }catch(e){if(caseVersion===version)fail(e)}
}
function units(){
 const record=reviews[current.id]||{};
 $('units').innerHTML=current.units.map((u,i)=>{const p=current.public_units.find(p=>p.id===u.id);return `<article class="unit ${activeUnit===u.id?'active':''}" id="unit-${u.id}" style="--color:${colors[i]}"><button class="select-unit" data-unit="${u.id}">${u.id} · 选中此对象</button><h3>${esc(u.target.category)} · ${esc(u.operation)}${u.attribute_kind?' / '+esc(u.attribute_kind):''}</h3><div class="form">正式输入：${esc(mode(u))} · 父物体 ${esc(u.target.parent_instance_id)}</div><label>在源图上显示<select data-mode="${u.id}" aria-label="${u.id} 标注形式"><option value="none">不显示</option><option value="point">point</option><option value="box">box</option><option value="mask">mask</option></select></label><p>${esc(p.instruction)}</p><details><summary>私有指代、范围及完成标准</summary><p>ref：${esc(u.target.ref)}</p><p>范围：${esc(u.target.scope)}</p><p>${esc(u.completion_requirement)}</p><p>面积 ${(u.target.geometry.area_fraction*100).toFixed(2)}%；有效连通块 ${u.target.geometry.significant_components}。多个连通块仍是一个 object。</p></details><details><summary>对象备注 / 指令修改建议</summary><textarea data-unit-note="${u.id}" placeholder="此对象的标注或指代问题…">${esc(record.unit_notes?.[u.id]||'')}</textarea><textarea data-suggestion="${u.id}" placeholder="可选：正式指令的修改建议…">${esc(record.instruction_suggestions?.[u.id]||'')}</textarea></details></article>`}).join('');
 for(const select of document.querySelectorAll('[data-mode]')){select.value=viewModes[select.dataset.mode]||'none';select.onchange=()=>{viewModes[select.dataset.mode]=select.value;activeUnit=select.dataset.mode;highlight();setDirty();draw()}}
 for(const b of document.querySelectorAll('[data-unit]'))b.onclick=()=>{activeUnit=b.dataset.unit;highlight()};
 document.querySelectorAll('[data-unit-note],[data-suggestion]').forEach(el=>el.oninput=setDirty);
}
function highlight(){document.querySelectorAll('.unit').forEach(el=>el.classList.toggle('active',el.id==='unit-'+activeUnit))}
function capture(){const record={case_id:current.id,manifest_sha256:metadata.manifest_sha256,decision:$('decision').value,reviewer:$('reviewer').value,note:$('note').value,view_modes:{...viewModes},unit_notes:{},instruction_suggestions:{}};document.querySelectorAll('[data-unit-note]').forEach(el=>record.unit_notes[el.dataset.unitNote]=el.value);document.querySelectorAll('[data-suggestion]').forEach(el=>record.instruction_suggestions[el.dataset.suggestion]=el.value);return record}
async function save(){if(!current)return;try{const {record}=await json('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(capture())});reviews[current.id]=record;dirty=false;$('save-state').textContent='已保存到审核包';rows();return true}catch(e){fail(e);return false}}
async function select(id){
 if(current?.id===id)return;if(dirty&&!await save())return;
 const ticket=++version;drawSerial++;$('load-state').textContent='加载所选 case…';$('error').textContent='';$('formal-details').open=false;$('formal-image').removeAttribute('src');
 try{const c=await json('cases/'+encodeURIComponent(id)+'.json');const src=await image(c.source.image);if(ticket!==version)return;current=c;source=src;maskCache=new Map();activeUnit=c.units[0].id;position=Math.max(0,filtered.findIndex(x=>x.id===id));const record=reviews[id]||{};viewModes=Object.fromEntries(c.units.map(u=>[u.id,record.view_modes?.[u.id]||'none']));$('case-title').textContent=c.id;$('evidence').textContent=c.difficulty.evidence_zh;$('original').href=c.source.image;$('decision').value=record.decision||'pending';$('reviewer').value=record.reviewer||$('reviewer').value;$('note').value=record.note||'';$('save-state').textContent='';dirty=false;units();rows();await draw();$('load-state').textContent='';history.replaceState(null,'','#'+encodeURIComponent(id));document.querySelector(`[data-case="${id}"]`)?.scrollIntoView({block:'nearest'})}catch(e){if(ticket===version){fail(e);$('load-state').textContent='加载失败'}}
}
function allModes(value){if(!current)return;for(const u of current.units)viewModes[u.id]=value==='formal'?u.interaction.locator:value;document.querySelectorAll('[data-mode]').forEach(el=>el.value=viewModes[el.dataset.mode]);setDirty();draw()}
$('clear').onclick=()=>allModes('none');$('formal-modes').onclick=()=>allModes('formal');document.querySelectorAll('[data-all]').forEach(b=>b.onclick=()=>allModes(b.dataset.all));$('zoom').onchange=fit;
$('prev').onclick=()=>{if(position>0)select(filtered[position-1].id)};$('next').onclick=()=>{if(position+1<filtered.length)select(filtered[position+1].id)};$('save').onclick=save;
for(const id of ['decision','reviewer','note'])$(id).addEventListener('input',setDirty);
for(const id of ['search','dataset','count','status'])$(id).addEventListener(id==='search'?'input':'change',filter);
$('formal-details').addEventListener('toggle',()=>{if($('formal-details').open&&current&&!$('formal-image').getAttribute('src'))$('formal-image').src=current.formal_input_image});
window.addEventListener('resize',fit);window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;if(e.key==='ArrowLeft')$('prev').click();if(e.key==='ArrowRight')$('next').click()});
(async()=>{try{[index,metadata]=await Promise.all([json('cases.json'),json('package_metadata.json')]);reviews=(await json('/api/reviews')).cases;filtered=index;rows();$('summary').textContent=`${metadata.cases} 条 · ${metadata.units} 个物体 · 点击列表按需加载`;const requested=decodeURIComponent(location.hash.slice(1));await select(index.find(c=>c.id===requested)?.id||index[0].id)}catch(e){fail(e)}})();
