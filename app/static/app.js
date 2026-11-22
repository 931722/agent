const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null, activeTrace = null, asking = false;
const statusNames = {WAITING:'等待前置工序',READY:'可排程',RESERVED:'已保留',RUNNING:'製作中',DONE:'已完成'};
async function api(path, method='GET', data) {
  const response = await fetch(path,{method,headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || (body.detail ? '輸入格式不正確，請檢查欄位。' : `操作失敗 (${response.status})`));
  return body;
}
function showError(message) {$('error').textContent=message;$('error').hidden=false;}
function clearError() {$('error').hidden=true;}
async function guarded(fn, button) {
  clearError(); if(button) button.disabled=true;
  try {await fn();} catch(e) {showError(e.message);} finally {if(button) button.disabled=false;}
}

function renderStation(station,tasks,chefs) {
  const active=tasks.find(task=>task.station_id===station.id&&['RESERVED','RUNNING'].includes(task.status));
  const status=!station.available?'OFFLINE':active?.status||'IDLE';
  const label={OFFLINE:'已停用',IDLE:'空閒',RESERVED:'已保留',RUNNING:'製作中'}[status];
  const work=active?`${escapeHtml(active.order_id)} · ${escapeHtml(active.dish)} · ${active.step==='cook'?'烹調':'出餐'}<br>${escapeHtml(chefs[active.chef_id]?.name||'未指定廚師')} · ${active.status==='RESERVED'?'等待按「開工」':'等待現場回報完成'}`:station.available?'目前沒有已保留或製作中的工序':'恢復啟用後才能派工';
  const busy=Boolean(active);
  return `<div class="resource station-resource" data-station-state="${status}"><div class="station-info"><div class="station-title"><strong><i class="dot ${status.toLowerCase()}"></i>${escapeHtml(station.name)}</strong><span class="status ${status} station-status">${label}</span></div><span>${station.available?'設備啟用':'設備停用'} · ${escapeHtml(station.id)}</span><span class="station-work">${work}</span></div><button class="quiet" data-station="${escapeHtml(station.id)}" data-kind="${station.available?'station_offline':'station_online'}" ${busy?'disabled title="請先完成此工作站的工序，再停用設備"':''}>${station.available?'停用':'恢復'}</button></div>`;
}

async function refresh() {
  const [s, risks, history]=await Promise.all([api('/api/state'),api('/api/risks'),api('/api/traces')]);state=s;
  $('mode').textContent=s.mode==='demo'?'固定規則模擬 · 非 LLM':'Ollama · 真實模型模式';$('mode').classList.toggle('demo',s.mode==='demo');
  $('model-name').textContent=s.mode==='demo'?'Deterministic demo':s.model;
  $('notice').textContent=`虛構單店模擬環境 · 時間由按鈕手動推進，工序不會自動完成。${s.mode==='demo'?'目前未呼叫 LLM，模擬紀錄不能當作模型實測。':'顯示真實模型模式不代表模型已連線成功；請提出需求驗證。'}`;
  $('clock').textContent=`第 ${s.clock} 分鐘`;$('order-count').textContent=Object.keys(s.orders).length;
  const tasks=Object.values(s.tasks);$('task-count').textContent=tasks.filter(t=>['READY','WAITING'].includes(t.status)).length;$('running-count').textContent=tasks.filter(t=>t.status==='RUNNING').length;
  $('stations').innerHTML=Object.values(s.stations).map(station=>renderStation(station,tasks,s.chefs)).join('');
  $('chefs').innerHTML=Object.values(s.chefs).map(x=>`<div class="resource"><div><strong>${escapeHtml(x.name)}</strong><span>${x.skills.map(k=>({wok:'炒台',soup:'湯台',pass:'出餐'}[k]||k)).join('、')}</span></div><span>${tasks.some(t=>t.chef_id===x.id&&['RESERVED','RUNNING'].includes(t.status))?'已占用':'空閒'}</span></div>`).join('');
  $('tasks').innerHTML=tasks.map(t=>`<tr><td>${escapeHtml(t.order_id)}<small>${escapeHtml(t.id)}</small></td><td>${escapeHtml(t.dish)} · ${t.step==='cook'?'烹調':'出餐'}<small>標準 ${t.minutes} 分鐘</small></td><td><span class="status ${escapeHtml(t.status)}">${statusNames[t.status]||escapeHtml(t.status)}</span></td><td>${escapeHtml(s.stations[t.station_id]?.name||'—')}<small>${escapeHtml(s.chefs[t.chef_id]?.name||'')}</small></td><td>${t.status==='RESERVED'?`<button data-task="${escapeHtml(t.id)}" data-kind="start">開工</button>`:t.status==='RUNNING'?`<button data-task="${escapeHtml(t.id)}" data-kind="complete">完成</button>`:'—'}</td></tr>`).join('');
  $('risks').innerHTML=risks.orders.map(o=>`<tr><td>${escapeHtml(o.order_id)}</td><td>第 ${o.due_at} 分鐘</td><td>${o.completed?'已完成':`第 ${o.earliest_finish_lower_bound} 分鐘`}</td><td>${escapeHtml(o.status)}</td></tr>`).join('');
  if(!$('dish').options.length) $('dish').innerHTML=Object.entries(s.menu).map(([k,v])=>`<option value="${escapeHtml(k)}">${escapeHtml(v.name)}</option>`).join('');
  $('history').innerHTML=history.length?history.map(t=>`<div class="history-row"><span>${escapeHtml(t.user_input)}<small>${escapeHtml(t.mode)} · ${escapeHtml(t.status)} · ${escapeHtml(new Date(t.created_at).toLocaleString())}</small></span><button class="quiet" data-trace="${escapeHtml(t.id)}">查看</button></div>`).join(''):'<p class="empty">尚無紀錄。</p>';
}
function renderProposals(proposals, historical=false) {
  $('proposals').innerHTML=proposals.map(p=>`<div class="proposal"><h3>FIFO 派工提案</h3><small>根據狀態版本 ${p.state_version} · ${historical?'歷史提案，僅供檢視':'尚未確認'}</small>${p.assignments.map(a=>`<div class="assignment"><strong>${escapeHtml(a.order_id)} · ${escapeHtml(a.dish)} ${a.step==='cook'?'烹調':'出餐'}</strong><span>${escapeHtml(a.station_name)} / ${escapeHtml(a.chef_name)} / 標準 ${a.minutes} 分鐘</span><span>${escapeHtml(a.reason)}</span></div>`).join('')}<p class="small muted">${p.blocked.length} 項就緒工序在產生提案時受阻。${historical?'目前進度請查看下方工序表；需要派工時請重新查詢。':'確認時會重新檢查資源。'}</p>${historical?'':`<button data-confirm="${escapeHtml(p.proposal_id)}">確認派工</button>`}</div>`).join('');
}
function renderTrace(t, historical=false) {
  activeTrace=t;$('answer-box').hidden=false;$('answer').textContent=t.answer;$('answer-mode').textContent=`${t.mode==='demo'?'模擬流程 · 非 LLM':t.model} · ${t.status} · ${t.duration_ms} ms`;
  $('download-trace').disabled=false;renderProposals(t.proposals||[],historical);
  const names={decision:'工具選擇',tool_call:'工具呼叫',observation:'結果觀察',final:'最後回覆',error:'錯誤'};
  $('trace').innerHTML=t.steps.map((s,i)=>`<details class="trace-item" ${s.type==='error'?'open':''}><summary>${i+1}. ${names[s.type]||escapeHtml(s.type)}${s.name?' · '+escapeHtml(s.name):''}${s.type==='error'?' · '+escapeHtml(s.code):''}</summary><pre>${escapeHtml(JSON.stringify(s,null,2))}</pre></details>`).join('');
}
$('chat-form').addEventListener('submit',e=>{e.preventDefault();if(asking)return;guarded(async()=>{asking=true;$('ask').disabled=true;$('reset-simulation').disabled=true;$('chat-status').textContent='正在讀取狀態與執行工具，本機模型首次載入可能需要較久…';$('proposals').replaceChildren();try{const t=await api('/api/chat','POST',{message:$('message').value});renderTrace(t);await refresh();}finally{asking=false;$('ask').disabled=false;$('reset-simulation').disabled=false;$('chat-status').textContent='每次提問獨立處理，最多 6 次工具呼叫。';}});});
$('order-form').addEventListener('submit',e=>{e.preventDefault();guarded(async()=>{await api('/api/orders','POST',{id:$('order-id').value,items:[{dish:$('dish').value,quantity:Number($('quantity').value)}],due_in:Number($('due').value)});await refresh();let n=4;while(state.orders['O'+String(n).padStart(3,'0')])n++;$('order-id').value='O'+String(n).padStart(3,'0');},e.submitter);});
$('refresh').onclick=e=>guarded(refresh,e.target);
$('direct-schedule').onclick=e=>guarded(async()=>{await refresh();const p=await api('/api/schedule','POST',{state_version:state.version});if(!p.ok)throw new Error(p.error.message);renderProposals([p]);activeTrace=null;$('download-trace').disabled=true;$('trace').innerHTML='<p class="empty">這次為直接工具操作，沒有 Agent 執行紀錄。</p>';$('answer-box').hidden=false;$('answer-mode').textContent='直接執行 Python 工具 · 非 LLM';$('answer').textContent='已執行 FIFO 排程。這筆操作沒有經過 Agent 模型，不產生模型執行證據。';$('proposals').scrollIntoView({behavior:'smooth',block:'center'});},e.target);
$('download-trace').onclick=()=>{if(!activeTrace)return;const url=URL.createObjectURL(new Blob([JSON.stringify(activeTrace,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`trace-${activeTrace.mode}-${activeTrace.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.message){$('message').value=b.dataset.message;$('message').focus();}
  if(b.dataset.minutes)guarded(async()=>{await api('/api/clock','POST',{minutes:Number(b.dataset.minutes)});await refresh();},b);
  if(b.dataset.station)guarded(async()=>{if(!confirm(`確認${b.dataset.kind==='station_offline'?'停用':'恢復'}這個工作站？`))return;await api('/api/events','POST',{event_id:crypto.randomUUID(),kind:b.dataset.kind,target_id:b.dataset.station});await refresh();},b);
  if(b.dataset.task)guarded(async()=>{await api('/api/events','POST',{event_id:crypto.randomUUID(),kind:b.dataset.kind,target_id:b.dataset.task});await refresh();},b);
  if(b.dataset.confirm)guarded(async()=>{await api(`/api/proposals/${encodeURIComponent(b.dataset.confirm)}/confirm`,'POST');$('proposals').replaceChildren();await refresh();},b);
  if(b.dataset.trace)guarded(async()=>{renderTrace(await api(`/api/traces/${encodeURIComponent(b.dataset.trace)}`),true);$('answer-box').scrollIntoView({behavior:'smooth'});},b);
});
guarded(refresh);

$('reset-simulation').onclick=()=>{if(asking){showError('請等待助理回答完成後再重置。');return;}$('reset-dialog').showModal();};
$('reset-cancel').onclick=()=>$('reset-dialog').close();
$('reset-confirm').onclick=e=>guarded(async()=>{
  if(asking)throw new Error('請等待助理回答完成後再重置。');
  $('reset-dialog').close();
  const controls=[...document.querySelectorAll('button,input,select,textarea')];
  const disabled=controls.map(control=>control.disabled);
  controls.forEach(control=>control.disabled=true);
  $('reset-result').hidden=false;$('reset-result').textContent='正在備份資料並重置，請稍候…';
  try{
    const result=await api('/api/simulation/reset','POST',{state_version:state.version});
    activeTrace=null;$('answer-box').hidden=true;$('proposals').replaceChildren();
    $('trace').innerHTML='<p class="empty">已重置模擬。提出需求後，這裡會顯示新的執行流程。</p>';
    $('message').value='';$('order-id').value='O004';
    await refresh();
    $('reset-result').textContent=result.message+' 備份已儲存：'+result.backup_path+' ';
    const link=document.createElement('a');link.href=result.backup_url;link.textContent='下載重置前備份';link.download=result.backup_name;$('reset-result').append(link);
  }catch(error){$('reset-result').hidden=true;await refresh();throw error;}
  finally{controls.forEach((control,index)=>control.disabled=disabled[index]);if(!activeTrace)$('download-trace').disabled=true;}
},e.target);
