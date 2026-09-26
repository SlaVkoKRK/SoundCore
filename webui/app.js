let state={profiles:[],devices:[],notifications:[],hardware:{},training:{},cuda_repair:{}};
let updateInfo=null, trainingTimer=null, cudaTimer=null, sentenceIndex=0, updatePollTimer=null;
let continuousSession={active:false,count:0,startedAt:0};
let lastTrainingState="";
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const pages={dashboard:['Pulpit','Twórz, trenuj i zarządzaj swoimi modelami głosu.'],synthesis:['Synteza mowy','Studio generowania mowy z profili SoundCore.'],profiles:['Profile głosu','Nagrywaj i zarządzaj referencjami głosowymi.'],training:['Trening modelu','Buduj dataset i trenuj własny model XTTS v2.'],updates:['Aktualizacje','Aktualizacje pobierane i weryfikowane bezpośrednio z GitHuba.'],settings:['Ustawienia','Informacje o aplikacji, użytkowniku i środowisku.']};
let promptNonce=1;
async function loadPrompt(targetId,metaId,duration,purpose,profileName=''){
  try{
    const r=await api('get_reading_prompt',Number(duration),purpose,promptNonce++,profileName||'');
    $(targetId).value=r.text||'';
    if(metaId && $(metaId)){
      const hist=r.history_count?` · historia ${r.history_count}`:'';
      const reused=r.reused_sentences?` · wykorzystano ${r.reused_sentences} powt.`:'';
      $(metaId).textContent=`${r.word_count} słów · ok. ${r.estimated_seconds} s · cel ${r.target_seconds} s${hist}${reused}`;
    }
    return r;
  }catch(e){toast('Tekst do nagrania',e.message,'error');return null}
}

function api(method,...args){if(!window.pywebview?.api?.[method])return Promise.reject(new Error(`API ${method} niedostępne`));return window.pywebview.api[method](...args)}

let startupTimer=null,startupLast='';
function renderStartupServices(payload){
  const services=payload?.services||state.services||{};
  Object.entries(services).forEach(([key,v])=>{
    const el=document.querySelector(`[data-service="${key}"]`); if(!el)return;
    el.className=`startup-service ${v.state||'pending'}`;
    const b=el.querySelector('b'), sm=el.querySelector('small');
    if(b)b.textContent=v.label||key; if(sm)sm.textContent=v.message||'';
  });
  const busy=Object.values(services).some(v=>v.state==='loading'||v.state==='pending');
  if($('summaryStatus'))$('summaryStatus').textContent=busy?'Uruchamianie usług…':'System gotowy';
  if($('summaryStatusSub'))$('summaryStatusSub').textContent=busy?'Ciężkie moduły ładują się w tle':'SoundCore działa lokalnie';
}
async function pollStartup(){
  try{
    const r=await api('startup_status');
    const sig=JSON.stringify(r.services||{});
    if(sig!==startupLast){startupLast=sig; state.services=r.services||{}; renderStartupServices(r)}
    if(r.ready){
      clearInterval(startupTimer);startupTimer=null;
      state=await api('get_state');renderState();renderStartupServices({services:state.services});
    }
  }catch(e){}
}

function waitMs(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
async function withRecordingTimer(durationSeconds,title,promptText,action,countdownSeconds=3){
  const overlay=$('recordingTimerOverlay'),phase=$('recordingTimerPhase'),value=$('recordingTimerValue'),ttl=$('recordingTimerTitle'),bar=$('recordingTimerBar'),hint=$('recordingTimerHint'),prompt=$('recordingTimerPrompt');
  const duration=Math.max(1,Number(durationSeconds)||1);
  overlay.classList.remove('hidden','is-recording','processing');ttl.textContent=title||'Nagrywanie';hint.textContent='Przygotuj się i zacznij czytać po odliczaniu.';prompt.textContent=String(promptText||'').trim();bar.style.width='0%';
  for(let n=Math.max(0,Number(countdownSeconds)||0);n>=1;n--){phase.textContent='PRZYGOTUJ SIĘ';value.textContent=String(n);await waitMs(1000)}
  overlay.classList.add('is-recording');phase.textContent='● NAGRYWANIE';ttl.textContent=title||'Nagrywanie w toku';hint.textContent='Czytaj tekst naturalnie. Nie zamykaj okna.';
  const started=performance.now(); let timer=null;
  const paint=()=>{const elapsed=(performance.now()-started)/1000;const left=Math.max(0,duration-elapsed);value.textContent=`${left.toFixed(1)} s`;bar.style.width=`${Math.min(100,elapsed/duration*100)}%`;if(left<=0){clearInterval(timer);overlay.classList.remove('is-recording');overlay.classList.add('processing');phase.textContent='PRZETWARZANIE';value.textContent='Gotowe';ttl.textContent='Zapisuję i przygotowuję nagranie…';hint.textContent='Nagranie zakończone.'}};
  paint();timer=setInterval(paint,100);
  try{return await action()}finally{clearInterval(timer);setTimeout(()=>overlay.classList.add('hidden'),350)}
}
function toast(title,msg,level='info'){const t=document.createElement('div');t.className='toast';t.innerHTML=`<b>${esc(title)}</b><p>${esc(msg)}</p>`;$('toastHost').appendChild(t);setTimeout(()=>t.remove(),4200)}
function showPage(name){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===name));$(`page-${name}`).classList.add('active');$('pageTitle').textContent=pages[name][0];$('pageSubtitle').textContent=pages[name][1]}
function renderNotifications(){const rows=state.notifications||[];const unread=rows.filter(n=>!n.read).length;$('bellBadge').textContent=unread;$('bellBadge').classList.toggle('hidden',!unread);$('bellBtn').classList.toggle('has-unread',!!unread);$('notificationSummary').textContent=unread?`${unread} nowych`:'Brak nowych';$('notificationList').innerHTML=rows.length?rows.map(n=>`<div class="notification ${n.read?'':'unread'}"><span class="level ${esc(n.level)}"></span><div><b>${esc(n.title)}</b><p>${esc(n.message)}</p></div><time>${esc(n.time)}</time></div>`).join(''):'<div class="status-box" style="margin:14px">Brak powiadomień.</div>'}
function renderProfiles(){
  const ps=state.profiles||[];
  const ids=['dashProfile','synthProfile','trainProfile'];
  const previous=Object.fromEntries(ids.map(id=>[id,$(id)?.value||'']));
  const options=ps.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');
  ids.forEach(id=>{const el=$(id);if(!el)return;el.innerHTML=options||'<option value="">Brak profili</option>';if(previous[id]&&ps.some(p=>p.name===previous[id]))el.value=previous[id]});
  if(ps.length){$('summaryProfile').textContent=ps[0].name;$('summaryProfileSub').textContent=`${ps[0].duration_seconds}s · ${ps[0].dataset.samples} próbek datasetu`}else{$('summaryProfile').textContent='Brak profilu';$('summaryProfileSub').textContent='Dodaj profil, aby zacząć'}
  const modelLabel=p=>`${p.xtts_mode==='trained'?'Wytrenowany XTTS':(p.has_trained_xtts?'XTTS v2 · model gotowy':'XTTS v2')}${p.has_rvc_model?' + RVC':''}`;
  $('profileCards').innerHTML=ps.length?ps.slice(0,3).map(p=>`<div class="profile-card"><div class="profile-avatar">${esc((p.name[0]||'V').toUpperCase())}</div><div><b>${esc(p.name)}</b><small>${p.dataset.samples} próbek · ${p.dataset.duration_minutes} min · ${modelLabel(p)}</small></div></div>`).join(''):'<div class="status-box">Brak profili. Dodaj pierwszy głos.</div>';
  $('profilesTable').innerHTML=ps.length?ps.map(p=>`<div class="profile-row"><div class="profile-avatar">${esc((p.name[0]||'V').toUpperCase())}</div><div><b>${esc(p.name)}</b><small>Referencja ${p.duration_seconds}s · dataset ${p.dataset.samples} próbek / ${p.dataset.duration_minutes} min · ${modelLabel(p)}</small></div><div class="profile-row-actions"><button onclick="playProfile('${encodeURIComponent(p.name)}')">▶ Odsłuchaj</button><button onclick="deleteProfile('${encodeURIComponent(p.name)}')">🗑 Usuń</button></div></div>`).join(''):'<div class="status-box">Nie masz jeszcze profili głosowych.</div>';
  updateDatasetStats();
}
function renderDevices(){const o=(state.devices||[]).map(d=>`<option value="${d.index}">${esc(d.name)}</option>`).join('');['profileDevice','trainDevice','trainProfileDevice'].forEach(id=>$(id).innerHTML=o||'<option value="">Brak mikrofonu</option>')}
function renderHardware(){const h=state.hardware||{};$('summaryGpu').textContent=h.gpu_detected?h.gpu_name:(h.cpu||'CPU');$('summaryGpuSub').textContent=h.gpu_detected?`${h.gpu_memory_mb?Math.round(h.gpu_memory_mb/1024)+' GB VRAM · ':''}${h.torch_cuda_available?'CUDA aktywna':'PyTorch CPU-only'}`:'Tryb CPU';$('gpuPill').textContent=h.torch_cuda_available?'GPU':'CPU';$('gpuPill').className=`status-pill ${h.torch_cuda_available?'green':'neutral'}`;$('trainGpuName').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU';$('trainGpuNote').textContent=h.note||'';$('cudaState').textContent=h.torch_cuda_available?'Aktywna':'Nieaktywna';$('cudaVersion').textContent=h.torch_cuda_available?`CUDA ${h.torch_cuda_version||''}`:(h.gpu_detected?'Wymaga instalacji builda CUDA':'Brak kompatybilnego GPU');$('settingsGpu').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU';$('settingsGpuExtra').textContent=h.gpu_memory_mb?`${Math.round(h.gpu_memory_mb/1024)} GB VRAM · sterownik ${h.nvidia_driver||'—'}`:(h.note||'');$('settingsCuda').textContent=h.torch_cuda_available?`Aktywna ${h.torch_cuda_version||''}`:'Nieaktywna';$('dashTrainDevice').textContent=h.torch_cuda_available?'GPU':'CPU';$('trainerDeviceBadge').textContent=h.torch_cuda_available?'CUDA':'CPU';const needs=!!h.gpu_detected&&!h.torch_cuda_available;$('cudaBanner').classList.toggle('hidden',!needs);$('cudaRepairBox').classList.toggle('hidden',!needs);if(needs)$('cudaBannerText').textContent=`${h.gpu_name} jest widoczny. Zainstalujemy PyTorch 2.5.1 z runtime CUDA 12.4.`}
function renderLossChart(history){
  const box=document.querySelector('.real-chart'),line=$('lossChartLine'),area=$('lossChartArea'),empty=$('lossChartEmpty');
  const pts=(history||[]).filter(x=>Number.isFinite(Number(x.loss)));
  if(!box||!line||!area)return;
  if(pts.length<2){box.classList.remove('has-data');line.setAttribute('d','');area.setAttribute('d','');return}
  box.classList.add('has-data');
  const w=520,h=130,pad=8,vals=pts.map(x=>Number(x.loss));
  let min=Math.min(...vals),max=Math.max(...vals);if(max-min<1e-9){max=min+1}
  const xy=vals.map((v,i)=>[pad+(w-2*pad)*(i/(vals.length-1)),pad+(h-2*pad)*(1-(v-min)/(max-min))]);
  const d=xy.map((p,i)=>`${i?'L':'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  line.setAttribute('d',d); area.setAttribute('d',`${d} L ${xy[xy.length-1][0].toFixed(1)} ${h-pad} L ${xy[0][0].toFixed(1)} ${h-pad} Z`);
}
function renderTrainingLog(t){
  const events=(t.events||[]).map(x=>`[${x.time||'--:--:--'}] ${x.message||''}`);
  const tech=(t.log_tail||[]).slice(-80);
  let rows=[]; if(events.length)rows.push('=== SOUNDCORE ===',...events); if(tech.length)rows.push('', '=== COQUI / TRAINER ===',...tech);
  $('trainingLog').textContent=rows.length?rows.join('\n'):'Brak logów.';
  $('trainingLog').scrollTop=$('trainingLog').scrollHeight;
}
function renderTraining(t){
  t=t||{};
  const p=Math.max(0,Math.min(100,Number(t.progress||0)));
  ['trainProgressBar','dashTrainProgress'].forEach(id=>$(id).style.width=`${p}%`);
  $('trainStatePercent').textContent=`${p}%`; $('dashTrainPercent').textContent=`${p}%`;
  const current=t.state||'idle';
  const active=['starting','preparing','downloading','training'].includes(current) || t.running===true;
  const label={idle:'Gotowy',starting:'Uruchamianie',preparing:'Przygotowanie',downloading:'Pobieranie XTTS',training:'Trening w toku',completed:'Trening zakończony',error:'Błąd treningu',stopped:'Zatrzymany'}[current]||current;
  $('trainStateTitle').textContent=label; $('dashTrainTitle').textContent=label;
  $('trainStateMessage').textContent=t.message||'Czekam na uruchomienie zadania.';
  $('dashTrainMessage').textContent=t.message||'Dodaj próbki, a następnie uruchom GPTTrainer.';
  const ep=t.epoch?`${t.epoch}/${t.epochs||'?'}`:'—'; const step=t.step!=null?t.step:'—'; const loss=t.loss!=null?Number(t.loss).toFixed(5):'—'; const lr=t.learning_rate!=null?Number(t.learning_rate).toExponential(2):'—';
  $('trainLiveEpoch').textContent=ep;$('trainLiveStep').textContent=step;$('trainLiveLoss').textContent=loss;$('trainLiveLr').textContent=lr;
  $('dashTrainEpoch').textContent=t.epoch?`Epoka ${ep} · krok ${step}`:(t.device?`Urządzenie: ${String(t.device).toUpperCase()}`:'Brak aktywnego zadania');
  $('dashTrainLoss').textContent=t.loss!=null?`Loss ${Number(t.loss).toFixed(4)}`:'Loss —';
  let stale=false,activity='Brak aktywności.'; if(t.last_activity){const sec=Math.max(0,Math.floor((Date.now()-new Date(t.last_activity).getTime())/1000));activity=`Ostatnia aktywność: ${sec} s temu`;stale=active&&sec>35}
  $('trainingActivity').textContent=activity+(stale?' · proces długo nie raportuje postępu':'');$('trainingActivity').classList.toggle('stale',stale);
  renderLossChart(t.loss_history||[]);renderTrainingLog(t);
  $('startTraining').disabled=active;
  $('stopTraining').classList.toggle('hidden',!active); $('stopTraining').disabled=!active;
  $('dashStopTraining').classList.toggle('hidden',!active); $('dashStopTraining').disabled=!active;
  if(current==='completed'&&lastTrainingState!=='completed'){toast('Trening zakończony','Checkpoint gotowy. Możesz podpiąć go pod profil.','success');loadProfileModelInfo()}
  lastTrainingState=current;
}
function renderCudaRepair(r){
  r=r||{};
  const cudaReady=!!state.hardware?.torch_cuda_available || !!r.torch_cuda_available || r.state==='verified';
  if(cudaReady){
    $('cudaRepairBox').classList.add('hidden');
    $('cudaRepairProgress').classList.add('hidden');
    $('restartAfterCuda').classList.add('hidden');
    return;
  }
  const active=['starting','installing','completed','error'].includes(r.state);
  $('cudaRepairProgress').classList.toggle('hidden',!active);
  if(!active){$('restartAfterCuda').classList.add('hidden');return;}
  const p=Number(r.progress||0); $('cudaRepairBar').style.width=`${p}%`; $('cudaRepairPercent').textContent=`${p}%`;
  $('cudaRepairTitle').textContent=r.state==='completed'?'CUDA zainstalowana':r.state==='error'?'Błąd instalacji':'Instalacja PyTorch CUDA';
  $('cudaRepairMessage').textContent=r.message||'';
  $('restartAfterCuda').classList.toggle('hidden',!(r.restart_required && !cudaReady));
}
function updateDatasetStats(){const p=(state.profiles||[]).find(x=>x.name===$('trainProfile').value)||(state.profiles||[])[0];$('trainSampleCount').textContent=p?.dataset.samples||0;$('trainDuration').textContent=`${p?.dataset.duration_minutes||0} min`;$('dashTrainDataset').textContent=`${p?.dataset.duration_minutes||0} min`}
function renderState(){const u=state.user||{};const initial=(u.name||'U')[0].toUpperCase();$('userName').textContent=u.name||'Użytkownik';$('userRole').textContent=u.role||'Lokalny profil';$('userAvatar').textContent=initial;$('userMenuAvatar').textContent=initial;$('userMenuName').textContent=u.name||'Użytkownik';$('userMenuVersion').textContent=`SoundCore v${state.version||'—'}`;$('settingsUser').textContent=u.name||'—';$('settingsVersion').textContent=state.version;$('sidebarVersion').textContent=`v${state.version}`;$('currentVersion').textContent=`v${state.version}`;$('updatesCurrent').textContent=`v${state.version}`;renderHardware();renderDevices();renderProfiles();renderNotifications();renderTraining(state.training);renderCudaRepair(state.cuda_repair);renderStartupServices({services:state.services||{}})}
async function refreshState(){try{state=await api('get_state');renderState()}catch(e){toast('Błąd uruchomienia',e.message,'error')}}
async function refreshTraining(){try{const t=await api('training_status');renderTraining(t)}catch(e){}}
async function refreshCuda(){try{const r=await api('cuda_repair_status');state.cuda_repair=r;if(r.torch_cuda_available){state.hardware=await api('refresh_hardware');renderHardware()}renderCudaRepair(r);if(['completed','verified','error'].includes(r.state)){clearInterval(cudaTimer);cudaTimer=null}}catch(e){}}
window.playProfile=async encoded=>{try{await api('play_profile',decodeURIComponent(encoded))}catch(e){toast('Odtwarzanie',e.message,'error')}};
window.deleteProfile=async encoded=>{const n=decodeURIComponent(encoded);if(!confirm(`Usunąć profil '${n}'?`))return;try{const r=await api('delete_profile',n);state.profiles=r.profiles;renderProfiles();toast('Profil usunięty',n,'success')}catch(e){toast('Błąd',e.message,'error')}};
async function startCudaRepair(){if(!confirm('SoundCore zainstaluje w aktywnym środowisku Python oficjalny PyTorch 2.5.1 + CUDA 12.4. Pobieranie może być duże. Kontynuować?'))return;try{state.cuda_repair=await api('install_cuda_runtime');renderCudaRepair(state.cuda_repair);toast('CUDA','Rozpoczęto instalację PyTorch CUDA.','info');clearInterval(cudaTimer);cudaTimer=setInterval(refreshCuda,1500)}catch(e){toast('CUDA',e.message,'error')}}

const searchCatalog=[
  {title:'Pulpit',subtitle:'Podsumowanie SoundCore',page:'dashboard',icon:'⌂',keywords:'start dashboard główna'},
  {title:'Synteza mowy',subtitle:'Generowanie mowy XTTS',page:'synthesis',icon:'◉',keywords:'tts generuj audio mowa'},
  {title:'Profile głosu',subtitle:'Nagrywanie i zarządzanie profilami',page:'profiles',icon:'◌',keywords:'profil głos mikrofon referencja'},
  {title:'Trening modelu',subtitle:'Dataset i GPTTrainer',page:'training',icon:'◎',keywords:'trening model dataset gpttrainer cuda'},
  {title:'Aktualizacje',subtitle:'GitHub update channel',page:'updates',icon:'↓',keywords:'update aktualizacja github wersja'},
  {title:'Ustawienia',subtitle:'Aplikacja i sprzęt',page:'settings',icon:'⚙',keywords:'ustawienia gpu cuda użytkownik'}
];
function getSearchItems(){
  const profiles=(state.profiles||[]).map(p=>({title:p.name,subtitle:`Profil głosu · ${p.dataset?.samples||0} próbek`,page:'profiles',icon:(p.name[0]||'P').toUpperCase(),keywords:`profil głos ${p.name}`}));
  return [...searchCatalog,...profiles];
}
function renderSearchResults(query){
  const box=$('searchResults');
  const q=String(query||'').trim().toLocaleLowerCase('pl');
  if(!q){box.classList.add('hidden');box.innerHTML='';return}
  const rows=getSearchItems().filter(x=>`${x.title} ${x.subtitle} ${x.keywords||''}`.toLocaleLowerCase('pl').includes(q)).slice(0,8);
  box.innerHTML=rows.length?rows.map((x,i)=>`<button class="search-result ${i===0?'active':''}" data-search-page="${esc(x.page)}"><span class="sr-icon">${esc(x.icon)}</span><div><b>${esc(x.title)}</b><small>${esc(x.subtitle)}</small></div></button>`).join(''):'<div class="search-empty">Brak wyników dla „'+esc(query)+'”.</div>';
  box.classList.remove('hidden');
  box.querySelectorAll('[data-search-page]').forEach(b=>b.onclick=()=>{showPage(b.dataset.searchPage);box.classList.add('hidden');$('globalSearch').value=''});
}
function openFirstSearchResult(){
  const first=$('searchResults').querySelector('[data-search-page]');
  if(first)first.click();
}
async function hydrateUserMenu(){
  try{
    const info=await api('get_user_menu_info');
    $('userMenuName').textContent=info.name||'Użytkownik';
    $('userMenuVersion').textContent=`SoundCore v${info.version||state.version||'—'}`;
    $('userMenuPath').textContent=info.base_dir||'';
    $('userMenuPath').title=info.base_dir||'';
  }catch(e){}
}
function fmtSessionTime(sec){sec=Math.max(0,Math.floor(sec));return `${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`}
function updateContinuousMeta(msg='Sesja aktywna'){if(!$('continuousSessionMeta'))return;$('continuousSessionCount').textContent=`${continuousSession.count} próbek`;$('continuousSessionTime').textContent=fmtSessionTime((Date.now()-continuousSession.startedAt)/1000);$('continuousSessionState').textContent=msg}
async function stopContinuousSession(reason='Zatrzymano'){continuousSession.active=false;$('startContinuousRecording').classList.remove('hidden');$('stopContinuousRecording').classList.add('hidden');$('recordTrainingSample').disabled=false;updateContinuousMeta(reason);$('sampleStatus').textContent=`Sesja ciągła zakończona: ${continuousSession.count} próbek.`}
async function runContinuousSession(){
  const profile=$('trainProfile').value.trim(); if(!profile){toast('Sesja ciągła','Najpierw wybierz profil.','error');return}
  continuousSession={active:true,count:0,startedAt:Date.now()};$('continuousSessionMeta').classList.remove('hidden');$('startContinuousRecording').classList.add('hidden');$('stopContinuousRecording').classList.remove('hidden');$('recordTrainingSample').disabled=true;updateContinuousMeta('Start sesji');
  let first=true;
  try{while(continuousSession.active){
    const text=$('trainingSentence').value.trim(); if(!text){await loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',profile);continue}
    const duration=Number($('trainingDuration').value);updateContinuousMeta(first?'Odliczanie':'Następna próbka');
    const r=await withRecordingTimer(duration,`Sesja ciągła · próbka ${continuousSession.count+1}`,text,()=>api('record_training_sample',profile,text,duration,Number($('trainDevice').value)),first?3:1);
    continuousSession.count++; if(r.profiles)state.profiles=r.profiles;renderProfiles();updateContinuousMeta('Próbka zapisana');
    if(!continuousSession.active)break;
    const next=await loadPrompt('trainingSentence','trainingPromptMeta',duration,'training',profile);
    if(next&&Number(next.fresh_sentences_remaining)<=0){await stopContinuousSession('Wykorzystano wszystkie świeże teksty z banku');toast('Sesja ciągła','Wykorzystano wszystkie teksty z banku dla tego profilu.','success');break}
    first=false;await waitMs(650);
  }}catch(e){toast('Sesja ciągła',e.message,'error');await stopContinuousSession('Błąd sesji')}finally{if(continuousSession.active)await stopContinuousSession('Zakończono')}
}
async function loadProfileModelInfo(){const profile=$('trainProfile')?.value;if(!profile)return;try{const r=await api('profile_model_info',profile);$('trainedModelState').textContent=r.mode==='trained'?'Wytrenowany XTTS aktywny':(r.has_trained_model?'Wytrenowany model dostępny':'Bazowy XTTS v2');$('trainedModelDetail').textContent=r.has_trained_model?`${r.trained_model.checkpoint_name||'checkpoint'} · ${r.trained_model.trained_at||''}`:'Po zakończeniu treningu checkpoint pojawi się tutaj.';$('activateTrainedModel').disabled=!r.has_trained_model||r.mode==='trained';$('useBaseModel').disabled=r.mode!=='trained'}catch(e){$('trainedModelDetail').textContent=e.message}}
function renderUpdateOverlay(st){const ov=$('updateOverlay');if(!ov)return;const state=st?.state||'idle';if(state==='idle'){ov.classList.add('hidden');return}ov.classList.remove('hidden');const p=Number(st.progress||0);$('updateOverlayBar').style.width=`${p}%`;$('updateOverlayPercent').textContent=`${p}%`;$('updateOverlayMessage').textContent=st.message||'';$('updateOverlayTitle').textContent=state==='downloading'?'Pobieranie aktualizacji':state==='verified'?'Weryfikacja zakończona':state==='restarting'?'Restart SoundCore…':state==='error'?'Błąd aktualizacji':'Przygotowanie aktualizacji'}
async function pollUpdateInstall(){try{const st=await api('update_install_status');renderUpdateOverlay(st);$('updateStatus').textContent=st.message||'';if(['error','idle'].includes(st.state)){clearInterval(updatePollTimer);updatePollTimer=null;if(st.state==='error')setTimeout(()=>$('updateOverlay').classList.add('hidden'),1800)}}catch(e){}}
function wire(){
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>showPage(b.dataset.page));
  document.querySelectorAll('[data-goto]').forEach(b=>b.onclick=()=>showPage(b.dataset.goto));
  const search=$('globalSearch');
  search.oninput=()=>renderSearchResults(search.value);
  search.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();openFirstSearchResult()}if(e.key==='Escape'){$('searchResults').classList.add('hidden');search.blur()}};
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();search.focus();search.select();renderSearchResults(search.value)}});
  document.addEventListener('click',e=>{if(!e.target.closest('.search-wrap'))$('searchResults').classList.add('hidden')});

  $('userMenuBtn').onclick=e=>{e.stopPropagation();const menu=$('userMenu');const willOpen=menu.classList.contains('hidden');menu.classList.toggle('hidden');$('userMenuBtn').classList.toggle('open',willOpen);$('userMenuBtn').setAttribute('aria-expanded',String(willOpen));$('notificationPanel').classList.add('hidden')};
  $('userSettingsBtn').onclick=()=>{showPage('settings');$('userMenu').classList.add('hidden');$('userMenuBtn').classList.remove('open')};
  $('userFolderBtn').onclick=async()=>{try{await api('open_data_folder');$('userMenu').classList.add('hidden')}catch(e){toast('Folder SoundCore',e.message,'error')}};
  $('userRestartBtn').onclick=async()=>{if(confirm('Uruchomić ponownie SoundCore?'))await api('restart_app')};
  document.addEventListener('click',e=>{if(!e.target.closest('.user-wrap')){$('userMenu').classList.add('hidden');$('userMenuBtn').classList.remove('open');$('userMenuBtn').setAttribute('aria-expanded','false')}});
  $('bellBtn').onclick=e=>{e.stopPropagation();$('notificationPanel').classList.toggle('hidden');$('userMenu').classList.add('hidden');$('userMenuBtn').classList.remove('open')};
  $('markReadBtn').onclick=async()=>{await api('mark_notifications_read');state.notifications=await api('notifications_state');renderNotifications()};
  document.addEventListener('click',e=>{if(!e.target.closest('.notification-wrap'))$('notificationPanel').classList.add('hidden')});

  $('trainProfile').onchange=()=>{updateDatasetStats();loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);loadProfileModelInfo()};
  $('profileDuration').onchange=()=>loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile',$('newProfileName').value);
  $('profileNewPrompt').onclick=()=>loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile',$('newProfileName').value);
  $('trainingDuration').onchange=()=>loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);
  $('nextSentence').onclick=()=>loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);
  $('trainProfileDuration').onchange=()=>loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile',$('trainNewProfileName').value);
  $('trainProfileNewPrompt').onclick=()=>loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile',$('trainNewProfileName').value);
  $('toggleTrainProfileCreate').onclick=()=>$('trainProfileCreator').classList.toggle('hidden');
  $('startContinuousRecording').onclick=runContinuousSession;
  $('stopContinuousRecording').onclick=()=>{continuousSession.active=false;updateContinuousMeta('STOP — kończę bieżącą próbkę…')};
  $('copyTrainingLog').onclick=async()=>{try{await navigator.clipboard.writeText($('trainingLog').textContent||'');toast('Log treningu','Skopiowano log do schowka.','success')}catch(e){toast('Log treningu','Nie udało się skopiować.','error')}};
  $('activateTrainedModel').onclick=async()=>{const profile=$('trainProfile').value;try{const r=await api('activate_trained_xtts',profile);state.profiles=r.profiles;renderProfiles();await loadProfileModelInfo();toast('Model profilu','Wytrenowany XTTS jest teraz aktywny.','success')}catch(e){toast('Model profilu',e.message,'error')}};
  $('useBaseModel').onclick=async()=>{const profile=$('trainProfile').value;try{const r=await api('use_base_xtts',profile);state.profiles=r.profiles;renderProfiles();await loadProfileModelInfo();toast('Model profilu','Przywrócono bazowy XTTS v2.','info')}catch(e){toast('Model profilu',e.message,'error')}};

  $('recordProfileBtn').onclick=async()=>{
    const b=$('recordProfileBtn');
    const profileName=$('newProfileName').value.trim();
    const readingText=$('profileReadingText').value.trim();
    if(!profileName){$('recordProfileStatus').textContent='Najpierw wpisz nazwę profilu.';toast('Profil','Najpierw wpisz nazwę profilu.','error');$('newProfileName').focus();return}
    if(!readingText){$('recordProfileStatus').textContent='Brak tekstu do przeczytania.';toast('Nagrywanie','Wygeneruj lub wpisz tekst do przeczytania.','error');$('profileReadingText').focus();return}
    try{
      b.disabled=true;$('recordProfileStatus').textContent='Nagrywanie w toku… czytaj tekst z okna nagrywania.';
      const duration=Number($('profileDuration').value);
      const r=await withRecordingTimer(duration,'Nagranie referencyjne',readingText,()=>api('record_profile',profileName,duration,Number($('profileDevice').value),readingText));
      state.profiles=r.profiles;renderProfiles();$('recordProfileStatus').textContent=`Profil ${r.profile} zapisany.`;toast('Profil gotowy',r.profile,'success');
    }catch(e){$('recordProfileStatus').textContent=e.message;toast('Nagrywanie',e.message,'error')}finally{b.disabled=false}
  };

  $('createProfileInTraining').onclick=async()=>{
    const b=$('createProfileInTraining');
    const profileName=$('trainNewProfileName').value.trim();
    const readingText=$('trainProfileReadingText').value.trim();
    if(!profileName){$('trainProfileCreateStatus').textContent='Najpierw wpisz nazwę profilu.';toast('Profil','Najpierw wpisz nazwę profilu.','error');$('trainNewProfileName').focus();return}
    if(!readingText){$('trainProfileCreateStatus').textContent='Brak tekstu do przeczytania.';toast('Nagrywanie','Wygeneruj lub wpisz tekst do przeczytania.','error');$('trainProfileReadingText').focus();return}
    try{
      b.disabled=true;$('trainProfileCreateStatus').textContent='Nagrywanie referencji… czytaj tekst z okna nagrywania.';
      const duration=Number($('trainProfileDuration').value);
      const r=await withRecordingTimer(duration,'Nagranie referencyjne',readingText,()=>api('record_profile',profileName,duration,Number($('trainProfileDevice').value),readingText));
      state.profiles=r.profiles;renderProfiles();
      $('trainProfile').value=r.profile;updateDatasetStats();
      $('trainProfileCreateStatus').textContent=`Profil ${r.profile} utworzony i wybrany do treningu.`;
      toast('Profil gotowy',r.profile,'success');
    }catch(e){$('trainProfileCreateStatus').textContent=e.message;toast('Profil',e.message,'error')}finally{b.disabled=false}
  };

  $('recordTrainingSample').onclick=async()=>{
    const b=$('recordTrainingSample');
    const profileName=$('trainProfile').value.trim();
    const readingText=$('trainingSentence').value.trim();
    if(!profileName){$('sampleStatus').textContent='Najpierw wybierz profil głosu.';toast('Dataset','Najpierw wybierz profil głosu.','error');return}
    if(!readingText){$('sampleStatus').textContent='Brak tekstu próbki.';toast('Dataset','Wygeneruj lub wpisz tekst próbki przed nagrywaniem.','error');$('trainingSentence').focus();return}
    try{
      b.disabled=true;$('sampleStatus').textContent='Nagrywanie próbki… czytaj tekst z okna nagrywania.';
      const duration=Number($('trainingDuration').value);
      const r=await withRecordingTimer(duration,'Próbka treningowa',readingText,()=>api('record_training_sample',profileName,readingText,duration,Number($('trainDevice').value)));
      $('sampleStatus').textContent=`Dodano ${r.sample.id}. Dataset: ${r.dataset.samples} próbek / ${r.dataset.duration_minutes} min.`;
      if(r.profiles)state.profiles=r.profiles;else await refreshState();
      renderProfiles();
      if($('recordingsProfile')){$('recordingsProfile').value=profileName;await loadRecordings()}
      await loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',profileName);
      toast('Próbka dodana',r.sample.id,'success');
    }catch(e){$('sampleStatus').textContent=e.message;toast('Dataset',e.message,'error')}finally{b.disabled=false}
  };

const synth=async dash=>{const text=dash?$('dashText').value:$('synthText').value,profile=dash?$('dashProfile').value:$('synthProfile').value,lang=dash?$('dashLanguage').value:$('synthLanguage').value,rvc=dash?false:$('synthRvc').checked,btn=dash?$('dashGenerate'):$('synthGenerate');try{btn.disabled=true;const old=btn.textContent;btn.dataset.old=old;btn.textContent='Generowanie…';const r=await api('synthesize',text,profile,lang,rvc);$('playerStatus').textContent=r.name;$('synthResult').textContent=`Gotowe: ${r.path}`;toast('Synteza gotowa',r.name,'success');await refreshState()}catch(e){toast('Synteza',e.message,'error');$('synthResult').textContent=e.message}finally{btn.disabled=false;btn.textContent=btn.dataset.old||'Generuj'}};$('dashGenerate').onclick=()=>synth(true);$('synthGenerate').onclick=()=>synth(false);['dashPlay','playerPlay','synthPlay'].forEach(id=>$(id).onclick=async()=>{try{await api('play_last_generated')}catch(e){toast('Odtwarzanie',e.message,'error')}});$('refreshGpu').onclick=async()=>{try{state.hardware=await api('refresh_hardware');renderHardware();toast('GPU',state.hardware.note,state.hardware.torch_cuda_available?'success':'info')}catch(e){toast('GPU',e.message,'error')}};$('cudaInstallQuick').onclick=$('installCudaBtn').onclick=startCudaRepair;$('restartAfterCuda').onclick=async()=>{await api('restart_app')};$('startTraining').onclick=async()=>{try{renderTraining(await api('start_training',$('trainProfile').value,'pl',Number($('trainEpochs').value),$('trainCompute').value,Number($('trainBatch').value)));toast('Trening','Uruchomiono GPTTrainer','success')}catch(e){toast('Trening',e.message,'error')}};$('stopTraining').onclick=$('dashStopTraining').onclick=async()=>{try{renderTraining(await api('stop_training'));toast('Trening','Zatrzymano trening','info')}catch(e){toast('Trening',e.message,'error')}};
const check=async()=>{try{$('checkUpdates').disabled=true;$('updateStatus').textContent='Sprawdzanie kanału GitHub…';updateInfo=await api('check_updates');if(!updateInfo.ok)throw new Error(updateInfo.error);$('latestVersion').textContent=`v${updateInfo.latest_version}`;$('updatesLatest').textContent=`v${updateInfo.latest_version}`;$('latestState').textContent=updateInfo.update_available?'Dostępna aktualizacja':'Masz najnowszą wersję';$('installUpdate').disabled=!updateInfo.update_available;const src=updateInfo.source?` · źródło: ${updateInfo.source}`:'';$('updateStatus').textContent=(updateInfo.update_available?`Dostępna wersja ${updateInfo.latest_version}.`:'Masz najnowszą wersję SoundCore.')+src;state.notifications=await api('notifications_state');renderNotifications()}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacje',e.message,'error')}finally{$('checkUpdates').disabled=false}};$('checkUpdates').onclick=$('dashCheckUpdates').onclick=check;$('installUpdate').onclick=async()=>{if(!confirm('Pobrać i przygotować aktualizację w tle? SoundCore zrestartuje się dopiero na końcu.'))return;try{$('installUpdate').disabled=true;const st=await api('install_update');renderUpdateOverlay(st);clearInterval(updatePollTimer);updatePollTimer=setInterval(pollUpdateInstall,500);pollUpdateInstall()}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacja',e.message,'error');$('installUpdate').disabled=false}}}
window.addEventListener('pywebviewready',async()=>{wire();await refreshState();await hydrateUserMenu();api('start_background_services').catch(()=>{});startupTimer=setInterval(pollStartup,650);pollStartup();Promise.all([loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile'),loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value),loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile')]);trainingTimer=setInterval(refreshTraining,1200);loadProfileModelInfo();if(['starting','installing'].includes(state.cuda_repair?.state))cudaTimer=setInterval(refreshCuda,1500)});

// SoundCore 0.3.8 - recording library + audio/video trim editor
let mediaSession=null;
const _renderProfiles038=renderProfiles;
renderProfiles=function(){
  _renderProfiles038();
  syncRecordingProfileOptions();
};
function syncRecordingProfileOptions(){
  const sel=$('recordingsProfile'); if(!sel)return;
  const current=sel.value;
  const ps=state.profiles||[];
  sel.innerHTML=ps.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('')||'<option value="">Brak profili</option>';
  if(current && ps.some(p=>p.name===current))sel.value=current;
  else if(ps.length)sel.value=ps[0].name;
}
async function loadRecordings(){
  const profile=$('recordingsProfile')?.value;
  if(!profile){$('recordingsList').innerHTML='<div class="status-box">Najpierw utwórz profil głosu.</div>';return}
  try{
    const r=await api('list_profile_recordings',profile);
    const rows=r.recordings||[];
    $('recordingsStats').textContent=`${rows.length} nagrań · dataset ${r.stats.samples} próbek · ${r.stats.duration_minutes} min`;
    $('recordingsList').innerHTML=rows.length?rows.map(x=>`<div class="recording-row"><div class="recording-type">${x.kind==='reference'?'R':'A'}</div><div><b>${esc(x.kind==='reference'?'Referencja profilu':x.id)}</b><small>${Number(x.duration_seconds||0).toFixed(2)} s · ${esc(x.source_name||'SoundCore')}</small></div><div class="recording-transcript" title="${esc(x.text||'')}">${esc(x.text||'Brak transkrypcji')}</div><div class="recording-row-actions"><button data-rec-play="${esc(x.id)}">▶</button>${x.deletable?`<button data-rec-edit="${esc(x.id)}">✎</button><button class="danger" data-rec-del="${esc(x.id)}">🗑</button>`:''}</div></div>`).join(''):'<div class="status-box">Brak nagrań dla profilu.</div>';
    $('recordingsList').querySelectorAll('[data-rec-play]').forEach(b=>b.onclick=async()=>{try{await api('play_profile_recording',profile,b.dataset.recPlay)}catch(e){toast('Odtwarzanie',e.message,'error')}});
    $('recordingsList').querySelectorAll('[data-rec-edit]').forEach(b=>b.onclick=async()=>{const row=b.closest('.recording-row');const current=row?.querySelector('.recording-transcript')?.textContent||'';const text=prompt('Wpisz dokładną transkrypcję próbki:',current==='Brak transkrypcji'?'':current);if(text===null)return;try{const r=await api('update_profile_recording_text',profile,b.dataset.recEdit,text);if(r.profiles){state.profiles=r.profiles;renderProfiles()}await loadRecordings();toast('Transkrypcja','Zapisano tekst próbki.','success')}catch(e){toast('Transkrypcja',e.message,'error')}});
    $('recordingsList').querySelectorAll('[data-rec-del]').forEach(b=>b.onclick=async()=>{if(!confirm(`Usunąć próbkę ${b.dataset.recDel}?`))return;try{const r=await api('delete_profile_recording',profile,b.dataset.recDel);if(r.profiles){state.profiles=r.profiles;renderProfiles()}await loadRecordings();toast('Próbka','Usunięto nagranie','success')}catch(e){toast('Usuwanie',e.message,'error')}});
  }catch(e){$('recordingsList').innerHTML=`<div class="status-box">${esc(e.message)}</div>`}
}
function drawMediaWave(peaks){
  const c=$('mediaWaveCanvas'); if(!c)return; const ctx=c.getContext('2d');
  const dpr=window.devicePixelRatio||1; const rect=c.getBoundingClientRect(); c.width=Math.max(600,Math.floor(rect.width*dpr)); c.height=Math.floor(rect.height*dpr); ctx.scale(dpr,dpr);
  const w=rect.width,h=rect.height,mid=h/2; ctx.clearRect(0,0,w,h);
  ctx.fillStyle='#f8faff';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#e7edf7';ctx.lineWidth=1;for(let i=1;i<6;i++){const y=h*i/6;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}
  const vals=peaks||[]; if(!vals.length)return; const gap=w/vals.length; ctx.strokeStyle='#5679ff';ctx.lineWidth=Math.max(1,Math.min(3,gap*.55));
  vals.forEach((v,i)=>{const x=i*gap+gap/2,amp=Math.max(1,v*(h*.42));ctx.beginPath();ctx.moveTo(x,mid-amp);ctx.lineTo(x,mid+amp);ctx.stroke()});
}
function updateMediaSelection(){
  if(!mediaSession)return; const dur=Number(mediaSession.duration_seconds||0); let a=Number($('mediaStartRange').value),b=Number($('mediaEndRange').value); if(a>b-.05){if(document.activeElement===$('mediaStartRange'))a=Math.max(0,b-.05);else b=Math.min(dur,a+.05)} $('mediaStartRange').value=a;$('mediaEndRange').value=b;
  $('mediaStartLabel').textContent=`${a.toFixed(2)} s`; $('mediaEndLabel').textContent=`${b.toFixed(2)} s`; $('mediaClipLength').textContent=`${Math.max(0,b-a).toFixed(2)} s`;
  const left=dur?100*a/dur:0,right=dur?100*b/dur:100; const sel=$('waveSelection');sel.style.left=`${left}%`;sel.style.width=`${Math.max(0,right-left)}%`;
}
async function openMediaEditor(){
  const profile=$('recordingsProfile').value;if(!profile){toast('Import','Wybierz profil.','error');return}
  const b=$('importMediaBtn');try{b.disabled=true;b.textContent='Importuję…';const r=await api('begin_media_import',profile);if(r.cancelled)return;mediaSession=r;$('mediaSourceName').textContent=r.source_name;$('mediaStartRange').max=r.duration_seconds;$('mediaEndRange').max=r.duration_seconds;$('mediaStartRange').value=0;$('mediaEndRange').value=r.duration_seconds;$('mediaTranscript').value='';$('mediaEditor').classList.remove('hidden');requestAnimationFrame(()=>{drawMediaWave(r.peaks);updateMediaSelection()});$('mediaEditorStatus').textContent=`Źródło: ${r.source_name} · ${Number(r.duration_seconds).toFixed(2)} s. Zaznacz fragment z właściwym głosem.`}catch(e){toast('Import pliku',e.message,'error')}finally{b.disabled=false;b.textContent='＋ Importuj audio / film'}}
async function closeMediaEditor(){if(mediaSession){try{await api('close_media_import',mediaSession.session_id)}catch(e){}}mediaSession=null;$('mediaEditor').classList.add('hidden')}
async function previewMedia(){if(!mediaSession)return;try{$('mediaEditorStatus').textContent='Odtwarzam zaznaczony fragment…';await api('preview_media_clip',mediaSession.session_id,Number($('mediaStartRange').value),Number($('mediaEndRange').value))}catch(e){toast('Podgląd',e.message,'error')}}
async function saveMedia(){if(!mediaSession)return;const profile=$('recordingsProfile').value;const b=$('saveMediaClip');try{b.disabled=true;b.textContent='Zapisuję…';const r=await api('save_media_clip',profile,mediaSession.session_id,Number($('mediaStartRange').value),Number($('mediaEndRange').value),$('mediaTranscript').value);if(r.profiles){state.profiles=r.profiles;renderProfiles()}$('mediaEditorStatus').textContent=`Zapisano ${r.sample.id} · ${Number(r.sample.duration_seconds).toFixed(2)} s.`;await loadRecordings();await refreshState();toast('Próbka zapisana',`${r.sample.id} z ${r.sample.source_name}`,'success')}catch(e){toast('Zapis próbki',e.message,'error')}finally{b.disabled=false;b.textContent='✦ Zapisz jako próbkę'}}
function wireRecordingLibrary(){
  if(!$('recordingsProfile'))return; syncRecordingProfileOptions(); $('recordingsProfile').onchange=loadRecordings; $('importMediaBtn').onclick=openMediaEditor; $('mediaStartRange').oninput=updateMediaSelection;$('mediaEndRange').oninput=updateMediaSelection;$('previewMediaClip').onclick=previewMedia;$('saveMediaClip').onclick=saveMedia;$('closeMediaEditor').onclick=closeMediaEditor;$('mediaEditor').onclick=e=>{if(e.target===$('mediaEditor'))closeMediaEditor()}; window.addEventListener('resize',()=>{if(mediaSession)drawMediaWave(mediaSession.peaks)}); loadRecordings();
}
window.addEventListener('pywebviewready',()=>setTimeout(wireRecordingLibrary,80));
