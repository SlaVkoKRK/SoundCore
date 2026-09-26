let state={profiles:[],devices:[],notifications:[],hardware:{},training:{},cuda_repair:{}};
let updateInfo=null, trainingTimer=null, cudaTimer=null, sentenceIndex=0;
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
function toast(title,msg,level='info'){const t=document.createElement('div');t.className='toast';t.innerHTML=`<b>${esc(title)}</b><p>${esc(msg)}</p>`;$('toastHost').appendChild(t);setTimeout(()=>t.remove(),4200)}
function showPage(name){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===name));$(`page-${name}`).classList.add('active');$('pageTitle').textContent=pages[name][0];$('pageSubtitle').textContent=pages[name][1]}
function renderNotifications(){const rows=state.notifications||[];const unread=rows.filter(n=>!n.read).length;$('bellBadge').textContent=unread;$('bellBadge').classList.toggle('hidden',!unread);$('bellBtn').classList.toggle('has-unread',!!unread);$('notificationSummary').textContent=unread?`${unread} nowych`:'Brak nowych';$('notificationList').innerHTML=rows.length?rows.map(n=>`<div class="notification ${n.read?'':'unread'}"><span class="level ${esc(n.level)}"></span><div><b>${esc(n.title)}</b><p>${esc(n.message)}</p></div><time>${esc(n.time)}</time></div>`).join(''):'<div class="status-box" style="margin:14px">Brak powiadomień.</div>'}
function renderProfiles(){const ps=state.profiles||[];const options=ps.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');['dashProfile','synthProfile','trainProfile'].forEach(id=>$(id).innerHTML=options||'<option value="">Brak profili</option>');if(ps.length){$('summaryProfile').textContent=ps[0].name;$('summaryProfileSub').textContent=`${ps[0].duration_seconds}s · ${ps[0].dataset.samples} próbek datasetu`}else{$('summaryProfile').textContent='Brak profilu';$('summaryProfileSub').textContent='Dodaj profil, aby zacząć'}$('profileCards').innerHTML=ps.length?ps.slice(0,3).map(p=>`<div class="profile-card"><div class="profile-avatar">${esc((p.name[0]||'V').toUpperCase())}</div><div><b>${esc(p.name)}</b><small>${p.dataset.samples} próbek · ${p.dataset.duration_minutes} min · ${p.has_rvc_model?'XTTS + RVC':'XTTS v2'}</small></div></div>`).join(''):'<div class="status-box">Brak profili. Dodaj pierwszy głos.</div>';$('profilesTable').innerHTML=ps.length?ps.map(p=>`<div class="profile-row"><div class="profile-avatar">${esc((p.name[0]||'V').toUpperCase())}</div><div><b>${esc(p.name)}</b><small>Referencja ${p.duration_seconds}s · dataset ${p.dataset.samples} próbek / ${p.dataset.duration_minutes} min</small></div><div class="profile-row-actions"><button onclick="playProfile('${encodeURIComponent(p.name)}')">▶ Odsłuchaj</button><button onclick="deleteProfile('${encodeURIComponent(p.name)}')">🗑 Usuń</button></div></div>`).join(''):'<div class="status-box">Nie masz jeszcze profili głosowych.</div>';updateDatasetStats()}
function renderDevices(){const o=(state.devices||[]).map(d=>`<option value="${d.index}">${esc(d.name)}</option>`).join('');['profileDevice','trainDevice','trainProfileDevice'].forEach(id=>$(id).innerHTML=o||'<option value="">Brak mikrofonu</option>')}
function renderHardware(){const h=state.hardware||{};$('summaryGpu').textContent=h.gpu_detected?h.gpu_name:(h.cpu||'CPU');$('summaryGpuSub').textContent=h.gpu_detected?`${h.gpu_memory_mb?Math.round(h.gpu_memory_mb/1024)+' GB VRAM · ':''}${h.torch_cuda_available?'CUDA aktywna':'PyTorch CPU-only'}`:'Tryb CPU';$('gpuPill').textContent=h.torch_cuda_available?'GPU':'CPU';$('gpuPill').className=`status-pill ${h.torch_cuda_available?'green':'neutral'}`;$('trainGpuName').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU';$('trainGpuNote').textContent=h.note||'';$('cudaState').textContent=h.torch_cuda_available?'Aktywna':'Nieaktywna';$('cudaVersion').textContent=h.torch_cuda_available?`CUDA ${h.torch_cuda_version||''}`:(h.gpu_detected?'Wymaga instalacji builda CUDA':'Brak kompatybilnego GPU');$('settingsGpu').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU';$('settingsGpuExtra').textContent=h.gpu_memory_mb?`${Math.round(h.gpu_memory_mb/1024)} GB VRAM · sterownik ${h.nvidia_driver||'—'}`:(h.note||'');$('settingsCuda').textContent=h.torch_cuda_available?`Aktywna ${h.torch_cuda_version||''}`:'Nieaktywna';$('dashTrainDevice').textContent=h.torch_cuda_available?'GPU':'CPU';$('trainerDeviceBadge').textContent=h.torch_cuda_available?'CUDA':'CPU';const needs=!!h.gpu_detected&&!h.torch_cuda_available;$('cudaBanner').classList.toggle('hidden',!needs);$('cudaRepairBox').classList.toggle('hidden',!needs);if(needs)$('cudaBannerText').textContent=`${h.gpu_name} jest widoczny. Zainstalujemy PyTorch 2.5.1 z runtime CUDA 12.4.`}
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
  $('dashTrainEpoch').textContent=t.device?`Urządzenie: ${String(t.device).toUpperCase()}`:'Brak aktywnego zadania';
  $('dashTrainLoss').textContent=t.loss!=null?`Loss ${Number(t.loss).toFixed(4)}`:'Loss —';
  $('startTraining').disabled=active;
  $('stopTraining').classList.toggle('hidden',!active); $('stopTraining').disabled=!active;
  $('dashStopTraining').classList.toggle('hidden',!active); $('dashStopTraining').disabled=!active;
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
function renderState(){const u=state.user||{};const initial=(u.name||'U')[0].toUpperCase();$('userName').textContent=u.name||'Użytkownik';$('userRole').textContent=u.role||'Lokalny profil';$('userAvatar').textContent=initial;$('userMenuAvatar').textContent=initial;$('userMenuName').textContent=u.name||'Użytkownik';$('userMenuVersion').textContent=`SoundCore v${state.version||'—'}`;$('settingsUser').textContent=u.name||'—';$('settingsVersion').textContent=state.version;$('sidebarVersion').textContent=`v${state.version}`;$('currentVersion').textContent=`v${state.version}`;$('updatesCurrent').textContent=`v${state.version}`;renderHardware();renderDevices();renderProfiles();renderNotifications();renderTraining(state.training);renderCudaRepair(state.cuda_repair)}
async function refreshState(){try{state=await api('get_state');renderState()}catch(e){toast('Błąd uruchomienia',e.message,'error')}}
async function refreshTraining(){try{renderTraining(await api('training_status'))}catch(e){}}
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

  $('trainProfile').onchange=()=>{updateDatasetStats();loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value)};
  $('profileDuration').onchange=()=>loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile',$('newProfileName').value);
  $('profileNewPrompt').onclick=()=>loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile',$('newProfileName').value);
  $('trainingDuration').onchange=()=>loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);
  $('nextSentence').onclick=()=>loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);
  $('trainProfileDuration').onchange=()=>loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile',$('trainNewProfileName').value);
  $('trainProfileNewPrompt').onclick=()=>loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile',$('trainNewProfileName').value);
  $('toggleTrainProfileCreate').onclick=()=>$('trainProfileCreator').classList.toggle('hidden');

  $('recordProfileBtn').onclick=async()=>{
    const b=$('recordProfileBtn');
    try{
      b.disabled=true;$('recordProfileStatus').textContent='Nagrywanie w toku… czytaj pokazany tekst.';
      const r=await api('record_profile',$('newProfileName').value,Number($('profileDuration').value),Number($('profileDevice').value),$('profileReadingText').value);
      state.profiles=r.profiles;renderProfiles();$('recordProfileStatus').textContent=`Profil ${r.profile} zapisany.`;toast('Profil gotowy',r.profile,'success');
    }catch(e){$('recordProfileStatus').textContent=e.message;toast('Nagrywanie',e.message,'error')}finally{b.disabled=false}
  };

  $('createProfileInTraining').onclick=async()=>{
    const b=$('createProfileInTraining');
    try{
      b.disabled=true;$('trainProfileCreateStatus').textContent='Nagrywanie referencji… czytaj pokazany tekst.';
      const r=await api('record_profile',$('trainNewProfileName').value,Number($('trainProfileDuration').value),Number($('trainProfileDevice').value),$('trainProfileReadingText').value);
      state.profiles=r.profiles;renderProfiles();
      $('trainProfile').value=r.profile;updateDatasetStats();
      $('trainProfileCreateStatus').textContent=`Profil ${r.profile} utworzony i wybrany do treningu.`;
      toast('Profil gotowy',r.profile,'success');
    }catch(e){$('trainProfileCreateStatus').textContent=e.message;toast('Profil',e.message,'error')}finally{b.disabled=false}
  };

  $('recordTrainingSample').onclick=async()=>{
    const b=$('recordTrainingSample');
    try{
      b.disabled=true;$('sampleStatus').textContent='Nagrywanie próbki… czytaj pokazany tekst.';
      const r=await api('record_training_sample',$('trainProfile').value,$('trainingSentence').value,Number($('trainingDuration').value),Number($('trainDevice').value));
      $('sampleStatus').textContent=`Dodano ${r.sample.id}. Dataset: ${r.dataset.samples} próbek / ${r.dataset.duration_minutes} min.`;
      await refreshState();
      await loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value);
      toast('Próbka dodana',r.sample.id,'success');
    }catch(e){$('sampleStatus').textContent=e.message;toast('Dataset',e.message,'error')}finally{b.disabled=false}
  };

const synth=async dash=>{const text=dash?$('dashText').value:$('synthText').value,profile=dash?$('dashProfile').value:$('synthProfile').value,lang=dash?$('dashLanguage').value:$('synthLanguage').value,rvc=dash?false:$('synthRvc').checked,btn=dash?$('dashGenerate'):$('synthGenerate');try{btn.disabled=true;const old=btn.textContent;btn.dataset.old=old;btn.textContent='Generowanie…';const r=await api('synthesize',text,profile,lang,rvc);$('playerStatus').textContent=r.name;$('synthResult').textContent=`Gotowe: ${r.path}`;toast('Synteza gotowa',r.name,'success');await refreshState()}catch(e){toast('Synteza',e.message,'error');$('synthResult').textContent=e.message}finally{btn.disabled=false;btn.textContent=btn.dataset.old||'Generuj'}};$('dashGenerate').onclick=()=>synth(true);$('synthGenerate').onclick=()=>synth(false);['dashPlay','playerPlay','synthPlay'].forEach(id=>$(id).onclick=async()=>{try{await api('play_last_generated')}catch(e){toast('Odtwarzanie',e.message,'error')}});$('refreshGpu').onclick=async()=>{try{state.hardware=await api('refresh_hardware');renderHardware();toast('GPU',state.hardware.note,state.hardware.torch_cuda_available?'success':'info')}catch(e){toast('GPU',e.message,'error')}};$('cudaInstallQuick').onclick=$('installCudaBtn').onclick=startCudaRepair;$('restartAfterCuda').onclick=async()=>{await api('restart_app')};$('startTraining').onclick=async()=>{try{renderTraining(await api('start_training',$('trainProfile').value,'pl',Number($('trainEpochs').value),$('trainCompute').value,Number($('trainBatch').value)));toast('Trening','Uruchomiono GPTTrainer','success')}catch(e){toast('Trening',e.message,'error')}};$('stopTraining').onclick=$('dashStopTraining').onclick=async()=>{try{renderTraining(await api('stop_training'));toast('Trening','Zatrzymano trening','info')}catch(e){toast('Trening',e.message,'error')}};
const check=async()=>{try{$('checkUpdates').disabled=true;$('updateStatus').textContent='Sprawdzanie kanału GitHub…';updateInfo=await api('check_updates');if(!updateInfo.ok)throw new Error(updateInfo.error);$('latestVersion').textContent=`v${updateInfo.latest_version}`;$('updatesLatest').textContent=`v${updateInfo.latest_version}`;$('latestState').textContent=updateInfo.update_available?'Dostępna aktualizacja':'Masz najnowszą wersję';$('installUpdate').disabled=!updateInfo.update_available;$('updateStatus').textContent=updateInfo.update_available?`Dostępna wersja ${updateInfo.latest_version}.`:'Masz najnowszą wersję SoundCore.';state.notifications=await api('notifications_state');renderNotifications()}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacje',e.message,'error')}finally{$('checkUpdates').disabled=false}};$('checkUpdates').onclick=$('dashCheckUpdates').onclick=check;$('installUpdate').onclick=async()=>{if(!confirm('Pobrać i zainstalować aktualizację z GitHuba?'))return;try{$('installUpdate').disabled=true;$('updateStatus').textContent='Pobieranie i weryfikacja SHA256…';const r=await api('install_update');if(r.restarting)$('updateStatus').textContent='Aktualizacja gotowa. Restart…'}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacja',e.message,'error');$('installUpdate').disabled=false}}}
window.addEventListener('pywebviewready',async()=>{wire();await refreshState();await hydrateUserMenu();await Promise.all([loadPrompt('profileReadingText','profilePromptMeta',$('profileDuration').value,'profile'),loadPrompt('trainingSentence','trainingPromptMeta',$('trainingDuration').value,'training',$('trainProfile').value),loadPrompt('trainProfileReadingText','trainProfilePromptMeta',$('trainProfileDuration').value,'profile')]);trainingTimer=setInterval(refreshTraining,1800);if(['starting','installing'].includes(state.cuda_repair?.state))cudaTimer=setInterval(refreshCuda,1500)});
