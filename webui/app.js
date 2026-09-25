const $ = (id) => document.getElementById(id);
let state = null;
let updateInfo = null;
let trainingTimer = null;
const sentences = [
  "Wieczorem temperatura powietrza spadła o kilka stopni, a miasto powoli cichło.",
  "Czy możesz sprawdzić, czy wszystkie urządzenia działają poprawnie i są gotowe do pracy?",
  "Jutro rano pojedziemy przez Kraków, a później skręcimy w stronę górskiej doliny.",
  "To jest próbka naturalnej mowy, wypowiedziana spokojnie, wyraźnie i bez pośpiechu.",
  "Liczby takie jak dwanaście, trzydzieści siedem i sto cztery powinny brzmieć naturalnie.",
  "Czasami mówię szybciej, czasami wolniej, ale zawsze staram się zachować dobrą dykcję.",
  "W domu jest cicho, więc mikrofon może dokładnie zarejestrować barwę i intonację mojego głosu.",
  "Dzień dobry, witam w SoundCore. To mój własny model głosu trenowany lokalnie na komputerze."
];
let sentenceIndex = 0;

function toast(title, message, level='info') {
  const box = document.createElement('div');
  box.className = `toast ${level}`;
  box.innerHTML = `<b>${escapeHtml(title)}</b><p>${escapeHtml(message)}</p>`;
  $('toastArea').appendChild(box);
  setTimeout(()=>box.remove(), 4200);
}
function escapeHtml(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
async function api(name, ...args) {
  if (!window.pywebview?.api?.[name]) throw new Error('Backend SoundCore nie jest jeszcze gotowy.');
  return await window.pywebview.api[name](...args);
}
function showPage(name) {
  const meta = {
    dashboard:['Pulpit','Witaj w SoundCore! Twórz, trenuj i zarządzaj swoimi modelami głosu.'],
    synthesis:['Synteza mowy','Generuj naturalną mowę przy użyciu swoich profili i XTTS v2.'],
    profiles:['Profile głosu','Nagrywaj referencje, zarządzaj profilami i przygotowuj dane do treningu.'],
    training:['Trening modelu','Zbieraj dataset i trenuj własny model XTTS/GPTTrainer na CPU lub GPU.'],
    updates:['Aktualizacje','Wszystkie aktualizacje SoundCore są pobierane z kanału GitHub Release.'],
    settings:['Ustawienia','Diagnostyka środowiska, wersji i akceleracji sprzętowej.']
  };
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  $(`page-${name}`).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.page===name));
  $('pageTitle').textContent=meta[name][0]; $('pageSubtitle').textContent=meta[name][1];
}
function renderNotifications() {
  const list = $('notificationList');
  const items = state?.notifications || [];
  list.innerHTML = items.length ? items.map(n=>`<div class="notification-item ${n.level||'info'} ${n.read?'':'unread'}"><i class="notification-dot"></i><div><b>${escapeHtml(n.title)}</b><p>${escapeHtml(n.message)}</p></div><time>${escapeHtml(n.time)}</time></div>`).join('') : '<div class="notification-item"><div></div><div><p>Brak powiadomień.</p></div></div>';
  const unread=items.filter(n=>!n.read).length; $('bellBadge').textContent=unread; $('bellBadge').style.display=unread?'flex':'none';
}
function profileOptions(select, profiles) {
  const prev=select.value;
  select.innerHTML = profiles.length ? profiles.map(p=>`<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`).join('') : '<option value="">Brak profili</option>';
  if (profiles.some(p=>p.name===prev)) select.value=prev;
}
function renderProfiles() {
  const profiles = state.profiles || [];
  [dashProfile,synthProfile,trainProfile].forEach(el=>profileOptions(el,profiles));
  if (profiles.length) {
    const p=profiles[0]; $('summaryProfile').textContent=p.name; $('summaryProfileSub').textContent=`${p.duration_seconds}s · ${p.dataset.samples} próbek treningowych`; $('dashDataset').textContent=`${p.dataset.duration_minutes} min`;
  } else { $('summaryProfile').textContent='Brak profilu'; $('summaryProfileSub').textContent='Dodaj profil, aby zacząć'; $('dashDataset').textContent='0 min'; }
  $('dashProfileCards').innerHTML = profiles.length ? profiles.slice(0,3).map(p=>`<div class="profile-card"><div class="profile-avatar">${escapeHtml(p.name[0]?.toUpperCase()||'V')}</div><div><b>${escapeHtml(p.name)}</b><small>${p.duration_seconds}s · ${p.dataset.samples} próbek</small><small>${p.has_rvc_model?'XTTS v2 + RVC':'XTTS v2'}</small></div></div>`).join('') : '<div class="status-box">Brak profili. Dodaj pierwszy profil głosu.</div>';
  $('profilesTable').innerHTML = profiles.length ? profiles.map(p=>`<div class="profile-row"><div class="profile-avatar">${escapeHtml(p.name[0]?.toUpperCase()||'V')}</div><div><b>${escapeHtml(p.name)}</b><small>Referencja ${p.duration_seconds}s · dataset ${p.dataset.samples} próbek / ${p.dataset.duration_minutes} min</small></div><div class="profile-row-actions"><button onclick="playProfile('${encodeURIComponent(p.name)}')">▶ Odsłuchaj</button><button onclick="deleteProfile('${encodeURIComponent(p.name)}')">🗑 Usuń</button></div></div>`).join('') : '<div class="status-box">Nie masz jeszcze profili głosowych.</div>';
  updateDatasetStats();
}
function renderHardware() {
  const h=state.hardware;
  $('summaryGpu').textContent=h.gpu_detected?h.gpu_name:h.cpu;
  $('summaryGpuSub').textContent=h.gpu_detected ? `${h.gpu_memory_mb?Math.round(h.gpu_memory_mb/1024)+' GB VRAM · ':''}${h.torch_cuda_available?'CUDA aktywna':'CUDA PyTorch nieaktywna'}` : 'Tryb CPU';
  $('gpuPill').textContent=h.torch_cuda_available?'GPU':'CPU';
  $('trainGpuName').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU'; $('trainGpuNote').textContent=h.note;
  $('settingsGpu').textContent=h.gpu_detected?h.gpu_name:'Brak NVIDIA GPU'; $('settingsGpuExtra').textContent=h.gpu_memory_mb?`${Math.round(h.gpu_memory_mb/1024)} GB VRAM · sterownik ${h.nvidia_driver||'—'}`:h.note;
  $('settingsCuda').textContent=h.torch_cuda_available?`Aktywna ${h.torch_cuda_version||''}`:'Nieaktywna';
  $('dashTrainDevice').textContent=h.torch_cuda_available?'GPU':'CPU';
}
function renderDevices() {
  const options=(state.devices||[]).map(d=>`<option value="${d.index}">${escapeHtml(d.name)}</option>`).join('');
  $('profileDevice').innerHTML=options||'<option value="">Brak mikrofonu</option>'; $('trainDevice').innerHTML=options||'<option value="">Brak mikrofonu</option>';
}
function updateDatasetStats() {
  const p=(state.profiles||[]).find(x=>x.name===$('trainProfile').value) || state.profiles?.[0];
  $('trainSampleCount').textContent=p?.dataset.samples||0; $('trainDuration').textContent=`${p?.dataset.duration_minutes||0} min`;
}
function renderState() {
  $('userName').textContent=state.user.name; $('userRole').textContent=state.user.role; $('userAvatar').textContent=(state.user.name||'U')[0].toUpperCase();
  $('settingsUser').textContent=state.user.name; $('settingsVersion').textContent=state.version; $('currentVersion').textContent=`v${state.version}`; $('updatesCurrent').textContent=`v${state.version}`;
  renderHardware(); renderDevices(); renderProfiles(); renderNotifications(); renderTraining(state.training);
}
function renderTraining(t) {
  t=t||{}; const progress=Math.max(0,Math.min(100,Number(t.progress||0)));
  $('trainProgressBar').style.width=`${progress}%`; $('dashTrainProgress').style.width=`${progress}%`; $('trainStatePercent').textContent=`${progress}%`; $('dashTrainPercent').textContent=`${progress}%`;
  const label={idle:'Gotowy',starting:'Uruchamianie',preparing:'Przygotowanie',downloading:'Pobieranie XTTS',training:'Trening w toku',completed:'Trening zakończony',error:'Błąd treningu',stopped:'Zatrzymany',unknown:'Nieznany'}[t.state]||t.state||'Gotowy';
  $('trainStateTitle').textContent=label; $('dashTrainTitle').textContent=label; $('trainStateMessage').textContent=t.message||'Czekam na uruchomienie zadania.'; $('dashTrainMessage').textContent=t.message||'Dodaj próbki treningowe, aby rozpocząć.'; $('dashTrainEpoch').textContent=t.device?`Urządzenie: ${String(t.device).toUpperCase()}`:'Brak aktywnego zadania';
}
async function refreshState() { try { state=await api('get_state'); renderState(); } catch(e){toast('Błąd startu',e.message,'error');} }
async function refreshTraining(){try{const t=await api('training_status'); renderTraining(t); if(t.state==='completed'||t.state==='error'){await refreshState();}}catch(e){}}

window.playProfile=async encoded=>{try{await api('play_profile',decodeURIComponent(encoded));}catch(e){toast('Odtwarzanie',e.message,'error')}};
window.deleteProfile=async encoded=>{const name=decodeURIComponent(encoded); if(!confirm(`Usunąć profil '${name}'?`))return; try{const r=await api('delete_profile',name);state.profiles=r.profiles;renderProfiles();toast('Profil usunięty',name,'success')}catch(e){toast('Błąd',e.message,'error')}};

function wire() {
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>showPage(b.dataset.page)); document.querySelectorAll('[data-goto]').forEach(b=>b.onclick=()=>showPage(b.dataset.goto));
  $('bellBtn').onclick=()=>{$('notificationPanel').classList.toggle('hidden');};
  $('markReadBtn').onclick=async()=>{await api('mark_notifications_read');state.notifications=await api('notifications_state');renderNotifications();};
  document.addEventListener('click',e=>{if(!e.target.closest('.notification-wrap'))$('notificationPanel').classList.add('hidden')});
  $('trainProfile').onchange=updateDatasetStats;
  $('nextSentence').onclick=()=>{sentenceIndex=(sentenceIndex+1)%sentences.length;$('trainingSentence').value=sentences[sentenceIndex]};
  $('recordProfileBtn').onclick=async()=>{const btn=$('recordProfileBtn');try{btn.disabled=true;$('recordProfileStatus').textContent='Nagrywanie w toku... mów teraz.';const r=await api('record_profile',$('newProfileName').value,Number($('profileDuration').value),Number($('profileDevice').value));state.profiles=r.profiles;renderProfiles();$('recordProfileStatus').textContent=`Profil ${r.profile} zapisany.`;toast('Profil gotowy',`Zapisano ${r.profile}`,'success')}catch(e){$('recordProfileStatus').textContent=e.message;toast('Nagrywanie',e.message,'error')}finally{btn.disabled=false}};
  $('recordTrainingSample').onclick=async()=>{const btn=$('recordTrainingSample');try{btn.disabled=true;$('sampleStatus').textContent='Nagrywanie próbki... mów dokładnie tekst z pola.';const r=await api('record_training_sample',$('trainProfile').value,$('trainingSentence').value,Number($('trainingDuration').value),Number($('trainDevice').value));$('sampleStatus').textContent=`Dodano ${r.sample.id}. Dataset: ${r.dataset.samples} próbek / ${r.dataset.duration_minutes} min.`;await refreshState();sentenceIndex=(sentenceIndex+1)%sentences.length;$('trainingSentence').value=sentences[sentenceIndex];toast('Próbka dodana',r.sample.id,'success')}catch(e){$('sampleStatus').textContent=e.message;toast('Dataset',e.message,'error')}finally{btn.disabled=false}};
  const synth=async(fromDash)=>{const text=fromDash?$('dashText').value:$('synthText').value;const profile=fromDash?$('dashProfile').value:$('synthProfile').value;const language=fromDash?$('dashLanguage').value:$('synthLanguage').value;const rvc=fromDash?false:$('synthRvc').checked;const btn=fromDash?$('dashGenerate'):$('synthGenerate');try{btn.disabled=true;btn.textContent='Generowanie...';const r=await api('synthesize',text,profile,language,rvc);$('playerStatus').textContent=r.name;$('synthResult').textContent=`Gotowe: ${r.path}`;toast('Synteza gotowa',r.name,'success');await refreshState()}catch(e){toast('Synteza',e.message,'error');$('synthResult').textContent=e.message}finally{btn.disabled=false;btn.textContent=fromDash?'✦ Generuj':'✦ Generuj i odtwórz'}};
  $('dashGenerate').onclick=()=>synth(true);$('synthGenerate').onclick=()=>synth(false);$('dashPlay').onclick=$('playerPlay').onclick=$('synthPlay').onclick=async()=>{try{await api('play_last_generated')}catch(e){toast('Odtwarzanie',e.message,'error')}};
  $('refreshGpu').onclick=async()=>{try{state.hardware=await api('refresh_hardware');renderHardware();state.notifications=await api('notifications_state');renderNotifications();toast('GPU',state.hardware.note,state.hardware.torch_cuda_available?'success':'info')}catch(e){toast('GPU',e.message,'error')}};
  $('startTraining').onclick=async()=>{try{const r=await api('start_training',$('trainProfile').value,'pl',Number($('trainEpochs').value),$('trainCompute').value,Number($('trainBatch').value));renderTraining(r);toast('Trening','Uruchomiono GPTTrainer','success')}catch(e){toast('Trening',e.message,'error')}};
  $('stopTraining').onclick=$('dashStopTraining').onclick=async()=>{try{renderTraining(await api('stop_training'));toast('Trening','Zatrzymano trening','info')}catch(e){toast('Trening',e.message,'error')}};
  const checkUpdates=async()=>{const btn=$('checkUpdates');try{btn.disabled=true;$('updateStatus').textContent='Sprawdzanie kanału GitHub...';updateInfo=await api('check_updates');if(!updateInfo.ok)throw new Error(updateInfo.error);$('latestVersion').textContent=`v${updateInfo.latest_version}`;$('updatesLatest').textContent=`v${updateInfo.latest_version}`;$('latestState').textContent=updateInfo.update_available?'Dostępna aktualizacja':'Masz najnowszą wersję';$('installUpdate').disabled=!updateInfo.update_available;$('updateStatus').textContent=updateInfo.update_available?`Dostępna wersja ${updateInfo.latest_version}. Możesz ją pobrać i zainstalować.`:'Masz najnowszą wersję SoundCore.';state.notifications=await api('notifications_state');renderNotifications()}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacje',e.message,'error')}finally{btn.disabled=false}};
  $('checkUpdates').onclick=$('dashCheckUpdates').onclick=checkUpdates;
  $('installUpdate').onclick=async()=>{if(!confirm('Pobrać aktualizację z GitHuba, zweryfikować SHA256 i zrestartować SoundCore?'))return;try{$('installUpdate').disabled=true;$('updateStatus').textContent='Pobieranie i weryfikacja paczki...';const r=await api('install_update');if(r.restarting)$('updateStatus').textContent='Aktualizacja gotowa. SoundCore uruchomi się ponownie...'}catch(e){$('updateStatus').textContent=e.message;toast('Aktualizacja',e.message,'error');$('installUpdate').disabled=false}};
}
window.addEventListener('pywebviewready',async()=>{wire();await refreshState();trainingTimer=setInterval(refreshTraining,1800);});
