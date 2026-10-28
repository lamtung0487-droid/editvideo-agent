const $ = id => document.getElementById(id);
const state = {project:null,projects:[],dirty:false,timelineDirty:false,timeline:null,job:null,health:null,tab:'script'};
const sample = 'Một chiếc lá nhỏ có thể làm một việc đáng kinh ngạc: biến ánh sáng thành năng lượng.\nTrong quá trình quang hợp, cây sử dụng ánh sáng, nước và khí các-bô-níc để tạo ra chất hữu cơ.\nÔ-xy được giải phóng như một sản phẩm của quá trình ấy.\nVì vậy, bảo vệ cây xanh cũng là chăm sóc môi trường sống của chúng ta.';
const esc = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = obj => JSON.parse(JSON.stringify(obj));
function toast(message,error=false){$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,error?8500:4000);}
async function api(path,options={}){
  const response = await fetch('/api'+path,{...options,headers:{...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...options.headers}});
  if(!response.ok){let message=`Lỗi ${response.status}`;try{const b=await response.json();message=typeof b.detail==='string'?b.detail:JSON.stringify(b.detail);}catch{}throw new Error(message);}
  return response.json();
}
async function attempt(fn){try{return await fn();}catch(e){toast(e.message,true);return null;}}
function pid(){if(!state.project)throw new Error('Hãy tạo dự án trước');return state.project.id;}
function assetUrl(a,thumb=false){return `/api/projects/${pid()}/assets/${a.id}/file${thumb?'?thumbnail=true':''}`;}
function fileUrl(job,name){return `/api/projects/${job.project_id}/jobs/${job.id}/${name}`;}
function currentBusy(){return state.project?.jobs.some(j=>['running','queued'].includes(j.state));}
function markDirty(){state.dirty=true;$('save-project').disabled=false;$('save-project').textContent='Lưu thay đổi';countWords();updateButtons();}
function countWords(){$('word-count').textContent=($('script').value.trim().split(/\s+/).filter(Boolean).length)+' tiếng';}
function updateButtons(){
  const busy=currentBusy();
  $('plan').disabled=busy||!$('script').value.trim();
  $('render-preview').disabled=busy||state.dirty||state.timelineDirty||!state.project?.plan_current;
  $('render-final').disabled=$('render-preview').disabled;
  $('save-project').disabled=!state.dirty||busy;
  $('save-timeline').disabled=busy||!state.project?.plan_current;
  $('asset-files').disabled=busy;
}
function readConfig(){return {...state.project.config,title:$('title').value.trim()||'Video mới',script:$('script').value.trim(),spoken_text:$('spoken-text').value.trim(),profile:$('profile').value,style:$('style').value,voice:$('voice').value,voice_rate:Number($('voice-rate').value),narration_id:$('narration').value||null,music_id:$('music').value||null,music_volume:Number($('music-volume').value)/100,captions:$('captions-enabled').checked};}
async function saveConfig(){
  if(!state.dirty)return;
  const config=readConfig();
  await api(`/projects/${pid()}`,{method:'PUT',body:JSON.stringify(config)});
  state.dirty=false;state.timelineDirty=false;
  await refreshProject(true);
}
function tab(name){
  state.tab=name;
  document.querySelectorAll('.tab-content').forEach(e=>e.hidden=e.id!==`tab-${name}`);
  document.querySelectorAll('.tab').forEach(e=>{e.classList.toggle('active',e.dataset.tab===name);e.setAttribute('aria-selected',String(e.dataset.tab===name));});
}
function paintProjects(){
  $('project-count').textContent=state.projects.length;
  $('project-list').innerHTML=state.projects.map(p=>`<button class="project-item ${p.id===state.project?.id?'active':''}" data-pid="${p.id}"><span class="project-symbol">▣</span><span><strong>${esc(p.config.title)}</strong><small>${new Date(p.updated_at).toLocaleDateString('vi-VN')}</small></span></button>`).join('');
  document.querySelectorAll('[data-pid]').forEach(b=>b.onclick=()=>attempt(async()=>{await saveConfig();if(state.timelineDirty)await saveTimeline();await loadProject(b.dataset.pid);}));
}
async function refreshList(){state.projects=await api('/projects');paintProjects();}
async function loadProject(id){
  const p=await api(`/projects/${id}`);
  state.project=p;state.dirty=false;state.timelineDirty=false;state.timeline=p.timeline?clone(p.timeline):null;
  localStorage.setItem('editvideo-project',id);
  $('video').hidden=true;$('video').removeAttribute('src');$('video').load();
  $('welcome').hidden=true;$('studio').hidden=false;
  fillConfig();paintTimeline();paintAssets();paintOutputs();paintJob();paintProjects();updateButtons();
}
async function refreshProject(fill=false){
  if(!state.project)return;
  const p=await api(`/projects/${pid()}`);state.project=p;
  if(fill){state.timeline=p.timeline?clone(p.timeline):null;fillConfig();paintTimeline();}
  paintAssets();paintOutputs();paintJob();updateButtons();await refreshList();
}
function fillConfig(){
  const p=state.project,c=p.config;
  $('title').value=c.title;$('script').value=c.script;$('spoken-text').value=c.spoken_text||'';
  ['profile','style','voice'].forEach(k=>$(k).value=c[k]);
  if(!Array.from($('voice-rate').options).some(o=>Number(o.value)===c.voice_rate))$('voice-rate').add(new Option(c.voice_rate+'%',c.voice_rate));
  $('voice-rate').value=c.voice_rate;
  $('music-volume').value=Math.round(c.music_volume*100);$('volume-value').textContent=$('music-volume').value+'%';$('captions-enabled').checked=c.captions;
  fillAudioChoices();
  $('project-heading').textContent=c.title;$('header-title').textContent=c.title;$('revision').textContent=`Bản ${p.revision}`;
  $('preview-profile').textContent={vertical:'9:16',landscape:'16:9',square:'1:1'}[c.profile];
  $('save-project').textContent='Lưu thay đổi';
  $('srt-status').textContent=p.has_srt?'Đã dùng thời gian từ SRT':'Chưa nhập SRT';$('clear-srt').hidden=!p.has_srt;
  $('audio-listen').hidden=!p.timeline;
  if(p.timeline){const url=`/api/projects/${p.id}/voice?v=${p.plan_meta?.revision}`;if($('audio').getAttribute('src')!==url)$('audio').src=url;}
  countWords();
}
function fillAudioChoices(){
  const assets=state.project.assets.filter(a=>a.kind==='audio');
  const oldNarration=state.dirty?$('narration').value:state.project.config.narration_id||'';
  const oldMusic=state.dirty?$('music').value:state.project.config.music_id||'';
  const options=assets.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('');
  $('narration').innerHTML='<option value="">Tạo giọng bằng Edge TTS (cần Internet)</option>'+options;
  $('music').innerHTML='<option value="">Không dùng nhạc</option>'+options;
  $('narration').value=oldNarration;$('music').value=oldMusic;
}
function paintAssets(){
  if(!state.project)return;
  $('asset-count').textContent=state.project.assets.length;
  fillAudioChoices();
  $('asset-grid').innerHTML=state.project.assets.length?state.project.assets.map(a=>`<article class="asset-card">${a.kind==='audio'?'<div class="asset-audio">♫</div>':`<img src="${assetUrl(a,true)}" alt="${esc(a.name)}" loading="lazy">`}<div class="asset-info"><strong title="${esc(a.name)}">${esc(a.name)}</strong><small>${esc(a.kind)} ${a.duration?`· ${a.duration.toFixed(1)}s`:''}${a.width?` · ${a.width} × ${a.height}`:''}</small><input id="tags-${a.id}" aria-label="Nhãn mô tả ${esc(a.name)}" placeholder="Nhãn: cây xanh, ánh sáng, chiếc lá…" value="${esc(a.tags)}"><select id="role-${a.id}" aria-label="Vai trò ${esc(a.name)}">${[['illustration','Minh họa'],['evidence','Tư liệu chứng cứ'],['metaphor','Ẩn dụ'],['reconstruction','Tái dựng'],['decoration','Trang trí']].map(([v,l])=>`<option value="${v}" ${a.role===v?'selected':''}>${l}</option>`).join('')}</select><button class="text-button" data-label="${a.id}">Lưu nhãn ↗</button>${a.source_url?`<a class="text-button" href="${esc(a.source_url)}" target="_blank" rel="noopener">Nguồn tư liệu ↗</a>`:''}</div></article>`).join(''):'<div class="hint">Chưa có tư liệu. Nếu thiếu hình, bộ dựng sẽ tạo đồ họa chữ từ nội dung lời đọc.</div>';
  document.querySelectorAll('[data-label]').forEach(b=>b.onclick=()=>attempt(async()=>{const a=b.dataset.label;await saveConfig();await api(`/projects/${pid()}/assets/${a}`,{method:'PATCH',body:JSON.stringify({tags:$('tags-'+a).value,role:$('role-'+a).value})});await refreshProject();toast('Đã lưu nhãn. Lập cảnh lại để chọn tư liệu theo nhãn mới.');}));
}
async function uploadFiles(files){
  if(!files.length)return;
  await saveConfig();
  for(let i=0;i<files.length;i++){
    $('upload-status').textContent=`Đang nhập ${i+1}/${files.length}: ${files[i].name}`;
    const body=new FormData();body.append('file',files[i]);
    const stem=files[i].name.replace(/\.[^.]+$/,'').replace(/[_-]/g,' ');body.append('tags',stem);
    await api(`/projects/${pid()}/assets`,{method:'POST',body});
  }
  $('upload-status').textContent=`Đã nhập ${files.length} tư liệu.`;await refreshProject();
}
function markTimelineDirty(){state.timelineDirty=true;$('save-timeline').textContent='Lưu bản dựng •';updateButtons();}
function paintTimeline(){
  const t=state.timeline;
  $('timeline-empty').hidden=!!t;$('timeline-editor').hidden=!t;
  $('save-timeline').textContent='Lưu bản dựng';
  if(!t)return;
  $('duration-tag').textContent=`${(t.total_frames/30).toFixed(1)} GIÂY · ${t.shots.length} CẢNH`;
  const estimated=t.timing_method.startsWith('estimated');
  $('timing-note').classList.toggle('warning',estimated||!state.project.plan_current);
  $('timing-note').textContent=!state.project.plan_current?'Đầu vào đã thay đổi. Hãy lập cảnh lại để cập nhật giọng và thời gian.':estimated?'Mốc phụ đề đang ước lượng theo kịch bản, chưa căn theo từng từ. Ông có thể sửa mốc ở dưới hoặc nhập SRT để khớp chính xác.':t.timing_method==='supplied_srt'?'Phụ đề sử dụng mốc thời gian từ SRT của ông.':'Phụ đề neo vào mốc từng từ do dịch vụ giọng đọc trả về.';
  $('timeline-ribbon').innerHTML=t.shots.map((s,i)=>`<button data-jump="${i}" style="flex:${s.end_frame-s.start_frame}" title="${esc(s.text)}">${String(i+1).padStart(2,'0')}</button>`).join('');
  $('shot-list').innerHTML=t.shots.map((s,i)=>{
    const a=state.project.assets.find(a=>a.id===s.asset_id);
    return `<article class="shot-card" id="shot-ui-${i}"><div class="shot-heading">${a?`<img src="${assetUrl(a,true)}" alt="">`:'<span class="brand-icon">T</span>'}<div><h3>Cảnh ${String(i+1).padStart(2,'0')} <span class="tag">${s.role==='evidence'?'CHỨNG CỨ':s.asset_id?'MINH HỌA':'ĐỒ HỌA CHỮ'}</span></h3><small>${(s.start_frame/30).toFixed(2)} → ${(s.end_frame/30).toFixed(2)}s · ${((s.end_frame-s.start_frame)/30).toFixed(2)}s</small></div></div><p class="shot-text">${esc(s.text)}</p><div class="shot-fields"><div class="full"><label>Tư liệu cho cảnh</label><select data-shot="${i}" data-field="asset_id"><option value="">Đồ họa chữ</option>${state.project.assets.filter(a=>a.kind==='image'||a.kind==='video').map(a=>`<option value="${a.id}" ${s.asset_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select></div><div><label>Chuyển động ảnh</label><select data-shot="${i}" data-field="motion">${[['hold','Giữ hình'],['push','Tiến nhẹ'],['pull','Lùi nhẹ'],['pan','Lướt ngang']].map(([v,l])=>`<option value="${v}" ${s.motion===v?'selected':''}>${l}</option>`).join('')}</select></div><div><label>Hiển thị</label><select data-shot="${i}" data-field="fit"><option value="cover" ${s.fit==='cover'?'selected':''}>Lấp khung hình</option><option value="contain" ${s.fit==='contain'?'selected':''}>Giữ trọn hình</option></select></div><div><label>Vị trí crop ngang (0–1)</label><input type="number" step="0.05" min="0" max="1" value="${s.focus_x}" data-shot="${i}" data-field="focus_x"></div><div><label>Vị trí crop dọc (0–1)</label><input type="number" step="0.05" min="0" max="1" value="${s.focus_y}" data-shot="${i}" data-field="focus_y"></div><div><label>Điểm bắt đầu trong clip (s)</label><input type="number" step="0.1" min="0" value="${s.source_start}" data-shot="${i}" data-field="source_start"></div>${i<t.shots.length-1?`<div><label>Điểm cắt sang cảnh kế (s)</label><input type="number" step="0.033333" min="${(s.start_frame+1)/30}" max="${(t.shots[i+1].end_frame-1)/30}" value="${(s.end_frame/30).toFixed(3)}" data-boundary="${i}"></div>`:''}<div class="full"><label>Chữ trên đồ họa (không đổi lời đọc)</label><textarea rows="2" data-shot="${i}" data-field="text">${esc(s.text)}</textarea></div></div><div class="reason">${esc(s.reason)}</div></article>`;
  }).join('');
  document.querySelectorAll('[data-shot]').forEach(e=>e.oninput=()=>{const s=t.shots[Number(e.dataset.shot)],k=e.dataset.field;s[k]=['source_start','focus_x','focus_y'].includes(k)?Number(e.value):k==='asset_id'?e.value||null:e.value;if(k==='asset_id'){const a=state.project.assets.find(a=>a.id===s[k]);s.role=a?.role||'decoration';}markTimelineDirty();});
  document.querySelectorAll('[data-boundary]').forEach(e=>e.onchange=()=>{const i=Number(e.dataset.boundary);const end=Math.round(Number(e.value)*30);if(!Number.isFinite(end)||end<=t.shots[i].start_frame||end>=t.shots[i+1].end_frame){toast('Điểm cắt phải nằm giữa hai cảnh.',true);e.value=(t.shots[i].end_frame/30).toFixed(3);return;}t.shots[i].end_frame=end;t.shots[i+1].start_frame=end;markTimelineDirty();});
  document.querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.jump);$('shot-ui-'+i).scrollIntoView({behavior:'smooth',block:'center'});if(!$('video').hidden)$('video').currentTime=t.shots[i].start_frame/30;});
  $('cue-list').innerHTML=t.cues.map((c,i)=>`<div class="cue-row"><input type="number" min="0" step="0.01" value="${c.start.toFixed(2)}" data-cue="${i}" data-field="start" aria-label="Phụ đề ${i+1} bắt đầu"><input type="number" min="0" step="0.01" value="${c.end.toFixed(2)}" data-cue="${i}" data-field="end" aria-label="Phụ đề ${i+1} kết thúc"><textarea rows="2" data-cue="${i}" data-field="text" aria-label="Nội dung phụ đề ${i+1}">${esc(c.text)}</textarea></div>`).join('');
  document.querySelectorAll('[data-cue]').forEach(e=>e.oninput=()=>{t.cues[Number(e.dataset.cue)][e.dataset.field]=e.dataset.field==='text'?e.value:Number(e.value);markTimelineDirty();});
}
function showVideo(job){
  const name=job.kind==='final'?'final.mp4':'preview.mp4',url=fileUrl(job,name);
  $('preview-placeholder').hidden=true;$('video').hidden=false;
  if($('video').getAttribute('src')!==url)$('video').src=url;
  $('preview-label').textContent=`${job.kind==='final'?'Full HD':'Bản xem nhanh'} · Bản ${job.revision}${job.revision!==state.project.revision?' · đầu vào đã đổi':''}`;
}
async function saveTimeline(){
  if(state.dirty)throw new Error('Lưu nội dung rồi lập cảnh lại trước khi chỉnh timeline.');
  const result=await api(`/projects/${pid()}/timeline`,{method:'PUT',body:JSON.stringify({base_revision:state.project.revision,timeline:state.timeline})});
  state.project=result;state.timeline=clone(result.timeline);state.timelineDirty=false;
  fillConfig();paintTimeline();paintOutputs();updateButtons();await refreshList();
}
function paintOutputs(){
  const outputs=state.project.jobs.filter(j=>j.state==='completed'&&j.kind!=='plan');
  $('output-list').innerHTML=outputs.length?outputs.map(j=>`<article class="output-card"><h3>${j.kind==='final'?'Video Full HD':'Bản xem nhanh'} <span class="tag">BẢN ${j.revision}</span></h3><small>${new Date(j.created_at).toLocaleString('vi-VN')}${j.revision!==state.project.revision?' · phiên bản đầu vào trước':''}</small><div class="output-links"><button class="button secondary small" data-watch="${j.id}">▷ Xem video</button><a class="button primary small" href="${fileUrl(j,j.kind==='final'?'final.mp4':'preview.mp4')}" download>Tải MP4 ↓</a><a class="button secondary small" href="${fileUrl(j,'captions.srt')}">Phụ đề SRT ↓</a>${j.kind==='final'?`<a class="button secondary small" href="${fileUrl(j,'delivery.zip')}">Gói bàn giao ↓</a>`:''}<a class="text-button" href="${fileUrl(j,'timeline.json')}">Timeline JSON</a></div><details class="advanced"><summary>Xem các khung hình</summary><img src="${fileUrl(j,'storyboard.jpg')}" alt="Các khung hình từ video đã dựng" loading="lazy"></details></article>`).join(''):'<div class="empty-state">Bấm “Dựng bản xem nhanh” hoặc “Xuất video Full HD” sau khi lập cảnh.</div>';
  document.querySelectorAll('[data-watch]').forEach(b=>b.onclick=()=>showVideo(outputs.find(j=>j.id===b.dataset.watch)));
  const current=outputs.find(j=>j.revision===state.project.revision)||outputs[0];
  if(current&&$('video').hidden)showVideo(current);
  if(!current){$('video').hidden=true;$('video').removeAttribute('src');$('preview-placeholder').hidden=false;$('preview-label').textContent='Chưa có video';}
}
function paintJob(){
  const active=state.project.jobs.find(j=>['running','queued'].includes(j.state));
  const recent=active||state.project.jobs[0];state.job=active||null;
  $('job-status').hidden=!recent;
  if(!recent)return;
  $('job-message').textContent=recent.message;$('job-progress').value=recent.progress;
  $('cancel-job').hidden=!active;$('job-error').textContent=recent.error||'';
  updateButtons();
}
async function submit(kind){
  if(kind==='plan'){await saveConfig();state.timelineDirty=false;}
  if(state.timelineDirty)throw new Error('Lưu bản dựng trước khi xuất video');
  const job=await api(`/projects/${pid()}/jobs`,{method:'POST',body:JSON.stringify({kind})});
  state.project.jobs.unshift(job);paintJob();updateButtons();
}
async function poll(){
  if(!state.job)return;
  try{
    const j=await api(`/jobs/${state.job.id}`);state.project.jobs=state.project.jobs.map(x=>x.id===j.id?j:x);paintJob();
    if(!['running','queued'].includes(j.state)){
      const fill=j.kind==='plan'&&j.state==='completed';await refreshProject(fill);
      if(j.state==='completed'){
        if(j.kind==='plan'){tab('timeline');toast('Đã lập cảnh theo giọng đọc. Ông có thể chỉnh hình hoặc xuất ngay.');}
        else{showVideo(j);toast('Video đã sẵn sàng.');tab('output');}
      }
    }
  }catch(e){$('job-error').textContent='Mất kết nối với ứng dụng. Đang kết nối lại…';}
}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
['title','script','spoken-text','profile','style','voice','voice-rate','narration','music','captions-enabled'].forEach(id=>$(id).addEventListener('input',markDirty));
$('music-volume').oninput=()=>{$('volume-value').textContent=$('music-volume').value+'%';markDirty();};
$('save-project').onclick=()=>attempt(async()=>{await saveConfig();toast('Đã lưu nội dung.');});
$('sample-script').onclick=()=>{$('script').value=sample;markDirty();};
$('plan').onclick=()=>attempt(()=>submit('plan'));
$('render-preview').onclick=()=>attempt(()=>submit('preview'));
$('render-final').onclick=()=>attempt(()=>submit('final'));
$('cancel-job').onclick=()=>attempt(async()=>{if(state.job)await api(`/jobs/${state.job.id}/cancel`,{method:'POST'});await refreshProject();});
$('save-timeline').onclick=()=>attempt(async()=>{await saveTimeline();toast('Đã lưu bản dựng.');});
$('asset-files').onchange=()=>attempt(async()=>{await uploadFiles(Array.from($('asset-files').files));$('asset-files').value='';});
const dz=$('drop-zone');dz.ondragover=e=>{e.preventDefault();dz.classList.add('dragging');};dz.ondragleave=()=>dz.classList.remove('dragging');dz.ondrop=e=>{e.preventDefault();dz.classList.remove('dragging');attempt(()=>uploadFiles(Array.from(e.dataTransfer.files)));};
$('srt-file').onchange=()=>attempt(async()=>{const f=$('srt-file').files[0];if(!f)return;await saveConfig();const body=new FormData();body.append('file',f);await api(`/projects/${pid()}/captions`,{method:'POST',body});await refreshProject(true);$('srt-file').value='';toast('Đã nhập SRT. Lập cảnh lại để dùng mốc mới.');});
$('clear-srt').onclick=()=>attempt(async()=>{await api(`/projects/${pid()}/captions`,{method:'DELETE'});await refreshProject(true);});
function newDialog(){$('new-dialog').showModal();$('new-title').focus();}
$('new-project').onclick=newDialog;$('welcome-new').onclick=newDialog;$('close-dialog').onclick=()=>$('new-dialog').close();
$('new-form').onsubmit=e=>{e.preventDefault();attempt(async()=>{await saveConfig();if(state.timelineDirty)await saveTimeline();const p=await api('/projects',{method:'POST',body:JSON.stringify({title:$('new-title').value})});$('new-dialog').close();$('new-title').value='';await refreshList();await loadProject(p.id);tab('script');});};
$('stock-search').onclick=()=>attempt(async()=>{
  const query=$('stock-query').value.trim();$('stock-results').textContent='Đang tìm…';
  const results=await api('/stock?query='+encodeURIComponent(query));
  $('stock-results').innerHTML=results.map(p=>`<article class="asset-card"><img src="${esc(p.thumbnail)}" alt="${esc(p.alt)}" loading="lazy"><div class="asset-info"><strong>${esc(p.author)}</strong><small>${esc(p.alt)}</small><button class="button secondary small" data-stock="${p.id}">Thêm vào tư liệu ＋</button></div></article>`).join('')||'<div class="hint">Chưa có kết quả phù hợp.</div>';
  document.querySelectorAll('[data-stock]').forEach(b=>b.onclick=()=>attempt(async()=>{b.disabled=true;await saveConfig();await api(`/projects/${pid()}/stock`,{method:'POST',body:JSON.stringify({photo_id:Number(b.dataset.stock),tags:query})});await refreshProject();b.textContent='Đã thêm';toast('Đã tải ảnh vào thư viện. Thêm nhãn tiếng Việt để chọn đúng cảnh.');}));
});
window.addEventListener('beforeunload',e=>{if(state.dirty||state.timelineDirty){e.preventDefault();e.returnValue='';}});
async function init(){
  state.health=await api('/health');$('engine-status').textContent=state.health.ffmpeg?'FFmpeg · '+(state.health.planner_ai?'Planner AI':'Planner theo nhãn'):'Chưa tìm thấy FFmpeg';
  $('stock-hint').textContent=state.health.pexels?'Đã kết nối Pexels. Tìm ảnh và tải vào thư viện.':'Chưa đặt PEXELS_API_KEY. Ông vẫn dựng được bằng tư liệu riêng.';
  await refreshList();const requested=new URLSearchParams(location.search).get('project')||localStorage.getItem('editvideo-project');const p=state.projects.find(p=>p.id===requested)||state.projects[0];if(p)await loadProject(p.id);
  setInterval(poll,1200);
}
attempt(init);
