const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (url, options={}) => {
  const response = await fetch(url, {headers: {'Content-Type':'application/json'}, ...options});
  if (!response.ok) throw new Error((await response.text()).replace(/<[^>]*>/g, '').trim());
  return response.status === 204 ? null : response.json();
};
const localDate = () => new Date().toLocaleDateString('sv-SE');
const currentYear = () => new Date().getFullYear();
const splitTags = value => (value || '').replaceAll('，', ',').split(',').map(x => x.trim()).filter(Boolean);
const tagsHtml = value => splitTags(value).map(x => `<span class="tag">${esc(x)}</span>`).join('');
let projects=[], allLogs=[], allTodos=[], logSeq=0, todoSeq=0;

function setTags(selector, value) {
  const select=$(selector), chosen=splitTags(value);
  select.innerHTML=projects.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');
  for (const name of chosen) if (![...select.options].some(x=>x.value===name)) select.add(new Option(name+'（历史标签）', name));
  [...select.options].forEach(x=>x.selected=chosen.includes(x.value));
}
const getTags = selector => [...$(selector).selectedOptions].map(x=>x.value).join(',');
async function loadProjects() {
  projects=await api('/api/projects');
  for (const id of ['#logProject','#todoProject']) {
    const previous=$(id).value;
    $(id).innerHTML='<option value="">全部项目</option>'+projects.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');
    $(id).value=previous;
  }
  setTags('#logTags','');setTags('#todoTags','');
}
function resetLogs() { for(const id of ['#logKeyword','#logType','#logProject']) $(id).value=''; $('#logFrom').value=`${currentYear()}-01-01`;$('#logTo').value=`${currentYear()}-12-31`; }
function resetTodos() { for(const id of ['#todoKeyword','#todoStatus','#todoProject']) $(id).value='';$('#todoFrom').value=`${currentYear()}-01-01`;$('#todoTo').value=`${currentYear()}-12-31`;$('#includeUndated').checked=true; }
async function logs() {
  const seq=++logSeq, q=new URLSearchParams({keyword:$('#logKeyword').value,date_from:$('#logFrom').value,date_to:$('#logTo').value,work_type:$('#logType').value,project:$('#logProject').value});
  const data=await api('/api/logs?'+q); if(seq!==logSeq)return; allLogs=data;
  $('#logList').innerHTML=data.length?data.map(x=>`<article class="card"><div class="date">${esc(x.logged_on)} · ${esc(x.work_type)}</div><h3>${esc(x.title)}</h3><div class="content">${esc(x.content)}</div><div class="tags">${tagsHtml(x.tags)}</div><div class="actions"><button class="link" onclick="makeTodo(${x.id})">生成待办</button><button class="link" onclick="editLog(${x.id})">编辑</button><button class="link" onclick="deleteLog(${x.id})">删除</button></div></article>`).join(''):'<div class="empty">没有符合查询条件的工作日志。</div>';
}
async function todos() {
  const seq=++todoSeq, q=new URLSearchParams({keyword:$('#todoKeyword').value,status:$('#todoStatus').value,project:$('#todoProject').value,due_from:$('#todoFrom').value,due_to:$('#todoTo').value,include_undated:$('#includeUndated').checked?'1':'0'});
  const data=await api('/api/todos?'+q);if(seq!==todoSeq)return;allTodos=data;
  $('#todoList').innerHTML=data.length?data.map(x=>`<article class="${x.status}"><input type="checkbox" ${x.status==='done'?'checked':''} onchange="toggleTodo(${x.id},this.checked)"><div class="todo-title">${esc(x.title)}<div class="todo-meta">${x.due_on?'截止 '+esc(x.due_on):'未设置截止日期'}${x.source_log_id?' · 来自工作日志':''} ${tagsHtml(x.tags)}</div></div><button class="link" onclick="editTodo(${x.id})">编辑</button><button class="link" onclick="deleteTodo(${x.id})">删除</button></article>`).join(''):'<div class="empty">没有符合查询条件的待办。</div>';
  const all=await api('/api/todos?status=open');$('#todoBadge').textContent=all.length||'';
}
window.deleteLog=async id=>{if(confirm('删除这篇日志？')){await api('/api/logs/'+id,{method:'DELETE'});await logs();}};
window.editLog=id=>{const x=allLogs.find(x=>x.id===id);$('#logId').value=x.id;$('#loggedOn').value=x.logged_on;$('#workType').value=x.work_type;$('#logTitle').value=x.title;$('#logContent').value=x.content;setTags('#logTags',x.tags);$('#logDialogTitle').textContent='编辑工作日志';$('#logDialog').showModal()};
window.makeTodo=id=>{const x=allLogs.find(x=>x.id===id);$('#todoForm').reset();$('#todoId').value='';$('#todoSource').value=id;$('#todoTitle').value='';setTags('#todoTags',x.tags);$('#todoDialog').showModal()};
window.editTodo=id=>{const x=allTodos.find(x=>x.id===id);$('#todoId').value=x.id;$('#todoSource').value=x.source_log_id||'';$('#todoTitle').value=x.title;$('#todoDue').value=x.due_on||'';setTags('#todoTags',x.tags);$('#todoDialog').showModal()};
window.toggleTodo=async(id,done)=>{await api('/api/todos/'+id,{method:'PATCH',body:JSON.stringify({status:done?'done':'open'})});todos()};
window.deleteTodo=async id=>{if(confirm('删除此待办？')){await api('/api/todos/'+id,{method:'DELETE'});todos()}};
$('#newLog').onclick=()=>{$('#logForm').reset();$('#logId').value='';$('#loggedOn').value=localDate();$('#workType').value=localStorage.getItem('lastWorkType')||'开发';setTags('#logTags',localStorage.getItem('lastProjects')||'');$('#logDialogTitle').textContent='新建工作日志';$('#logDialog').showModal()};
$('#newTodo').onclick=()=>{$('#todoForm').reset();$('#todoId').value='';$('#todoSource').value='';setTags('#todoTags','');$('#todoDialog').showModal()};
$('#logForm').onsubmit=async e=>{e.preventDefault();const id=$('#logId').value,data={logged_on:$('#loggedOn').value,work_type:$('#workType').value,title:$('#logTitle').value,content:$('#logContent').value,tags:getTags('#logTags')};try{await api('/api/logs'+(id?'/'+id:''),{method:id?'PUT':'POST',body:JSON.stringify(data)});localStorage.setItem('lastWorkType',data.work_type);localStorage.setItem('lastProjects',data.tags);$('#logDialog').close();logs()}catch(err){alert(err.message)}};
$('#todoForm').onsubmit=async e=>{e.preventDefault();const id=$('#todoId').value,data={title:$('#todoTitle').value,due_on:$('#todoDue').value,source_log_id:$('#todoSource').value,tags:getTags('#todoTags')};try{await api('/api/todos'+(id?'/'+id:''),{method:id?'PUT':'POST',body:JSON.stringify(data)});$('#todoDialog').close();todos()}catch(err){alert(err.message)}};
async function renderProjects(){await loadProjects();$('#projectList').innerHTML=projects.length?projects.map(x=>`<div><span>${esc(x.name)}</span><button class="link" type="button" onclick="deleteProject(${x.id})">删除</button></div>`).join(''):'<p>尚未设置项目标签。</p>'}
window.deleteProject=async id=>{if(confirm('删除此项目标签？历史记录将保留。')){await api('/api/projects/'+id,{method:'DELETE'});renderProjects()}};
$('#projectSettings').onclick=async()=>{await renderProjects();$('#projectDialog').showModal()};
$('#projectForm').onsubmit=async e=>{e.preventDefault();const name=$('#projectName').value.trim();if(!name)return;try{await api('/api/projects',{method:'POST',body:JSON.stringify({name})});$('#projectName').value='';await renderProjects()}catch(err){alert('添加失败：'+err.message)}};
const reportState={};
async function report(kind) {
  const period=$(kind==='month'?'#monthPicker':'#yearPicker').value;if(!period)return;
  const data=await api(`/api/reports/${kind}/${period}`);reportState[kind]=data;
  const target=$(kind==='month'?'#monthReport':'#yearReport');
  target.innerHTML=`<div class="summary"><div class="metric"><strong>${data.log_count}</strong>篇工作日志</div><div class="metric"><strong>${data.projects.length}</strong>个项目分类</div><div class="metric"><strong>${esc(Object.entries(data.types).map(([k,v])=>k+' '+v).join(' · ')||'—')}</strong>工作类型</div></div><div class="report-actions"><button class="link" onclick="copyReport('${kind}')">复制报表</button><button class="link" onclick="exportReport('${kind}','txt')">导出文本</button><button class="link" onclick="exportReport('${kind}','docx')">导出 Word</button></div>${data.projects.length?data.projects.map((group,index)=>`<article class="report-body"><h2>${esc(group.name)}</h2>${group.changed?'<p class="warning">日志已变化，保存的总结可能需要更新。</p>':''}<label>项目总结<textarea id="${kind}-summary-${index}" placeholder="手动填写，或点击生成 AI 初稿">${esc(group.summary)}</textarea></label><div><button class="primary" onclick="saveSummary('${kind}',${index})">保存总结</button> <button class="link" onclick="generateSummary('${kind}',${index})">生成 AI 初稿</button></div><ol class="highlights">${group.logs.map(x=>`<li><small>${esc(x.logged_on)} · ${esc(x.work_type)}</small><b>${esc(x.title)}</b><div>${esc(x.content)}</div></li>`).join('')}</ol></article>`).join(''):'<div class="empty">该时间段尚无工作日志。</div>'}`;
}
window.saveSummary=async(kind,index)=>{const d=reportState[kind],group=d.projects[index],content=$(`#${kind}-summary-${index}`).value;try{await api('/api/summaries',{method:'PUT',body:JSON.stringify({kind,period:d.period,project:group.name,content,fingerprint:group.fingerprint})});group.summary=content;group.changed=false;alert('总结已保存')}catch(err){alert(err.message)}};
window.generateSummary=async(kind,index)=>{const d=reportState[kind],group=d.projects[index],textarea=$(`#${kind}-summary-${index}`);if(!confirm(`将“${group.name}”在 ${d.period} 的日志发送给 OpenAI 生成初稿？当前编辑框内容将被替换。`))return;try{const result=await api('/api/summaries/generate',{method:'POST',body:JSON.stringify({kind,period:d.period,project:group.name})});textarea.value=result.content;alert('初稿已生成，请检查后点击“保存总结”。')}catch(err){alert(err.message)}};
function reportText(data){return [data.period+' 工作报告','日志总数：'+data.log_count,'工作类型：'+Object.entries(data.types).map(([k,v])=>k+' '+v).join('、'),...data.projects.flatMap(g=>['',g.name,g.summary||'暂无项目总结',...g.logs.map(x=>`${x.logged_on} ${x.title} ${x.content}`)])].join('\n')}
window.copyReport=async kind=>{try{await navigator.clipboard.writeText(reportText(reportState[kind]));alert('已复制已保存的报表内容')}catch(e){alert('复制失败，请检查浏览器权限')}};
window.exportReport=async(kind,format)=>{try{const r=await fetch('/api/report-export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,period:reportState[kind].period,format})});if(!r.ok)throw Error('导出失败');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`${reportState[kind].period}-工作报告.${format}`;a.click();URL.revokeObjectURL(url)}catch(e){alert(e.message)}};
$('#backupSettings').onclick=()=>$('#backupDialog').showModal();$('#aiSettings').onclick=async()=>{const data=await api('/api/ai-settings');$('#aiKey').value='';$('#aiModel').value=data.model;$('#aiStatus').textContent=data.configured?'已配置密钥':'尚未配置密钥';$('#aiDialog').showModal()};
$('#aiForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/ai-settings',{method:'PUT',body:JSON.stringify({api_key:$('#aiKey').value,model:$('#aiModel').value})});$('#aiDialog').close()}catch(err){alert(err.message)}};
$('#restoreBackup').onclick=async()=>{const file=$('#backupFile').files[0];if(!file){alert('请选择备份文件');return}if(!confirm('恢复将替换当前数据。系统会先备份当前数据，确认继续？'))return;const form=new FormData();form.append('backup',file);try{const r=await fetch('/api/restore',{method:'POST',body:form});if(!r.ok)throw Error('恢复失败，请确认备份文件有效');alert('恢复完成');location.reload()}catch(e){alert(e.message)}};
document.querySelectorAll('.nav[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.nav,.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#'+b.dataset.view).classList.add('active');if(['month','year'].includes(b.dataset.view))report(b.dataset.view)});
document.querySelectorAll('#logKeyword,#logFrom,#logTo,#logType,#logProject').forEach(x=>x.oninput=logs);
document.querySelectorAll('#todoKeyword,#todoStatus,#todoFrom,#todoTo,#todoProject,#includeUndated').forEach(x=>x.oninput=todos);
$('#resetLogs').onclick=()=>{resetLogs();logs()};$('#resetTodos').onclick=()=>{resetTodos();todos()};
$('#monthPicker').onchange=()=>report('month');$('#yearPicker').onchange=()=>report('year');
document.querySelectorAll('#logDialog button[value="cancel"],#todoDialog button[value="cancel"]').forEach(b=>{b.type='button';b.onclick=()=>b.closest('dialog').close()});
$('#monthPicker').value=localDate().slice(0,7);$('#yearPicker').value=currentYear();resetLogs();resetTodos();loadProjects().then(logs);todos();
