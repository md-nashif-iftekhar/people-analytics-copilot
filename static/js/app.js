/* ── CONFIG ─────────────────────────────────────────────────── */
const BASE = 'http://localhost:8000';
const charts = {};

/* ── UTILS ──────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const set = (id, html) => $(id).innerHTML = html;
const spin = id => set(id, `<div class="loading"><div class="spinner"></div>Running analysis…</div>`);
const oops = (id, e) => set(id, `<div class="err-box">⚠ Cannot reach API — make sure backend is running:<br><code>uvicorn main:app --reload --port 8000</code><br><br>${e.message||e}</div>`);
const fmt = n => typeof n === 'number' ? n.toLocaleString() : n;
const pct = v => `${(v*100).toFixed(1)}%`;
const rc = v => v>=0.6?'var(--red)':v>=0.35?'var(--amber)':'var(--green)';
const badge = (txt, cls) => `<span class="badge badge-${cls}">${txt}</span>`;

async function api(path, opts) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function mkChart(id, type, labels, datasets, opts = {}) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  const ctx = $(id); if (!ctx) return;
  const gridColor = 'rgba(255,255,255,0.04)';
  const tickColor = '#6b7280';
  charts[id] = new Chart(ctx, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: tickColor, font: { family: "'IBM Plex Mono'" } }, grid: { color: gridColor } },
        y: { ticks: { color: tickColor, font: { family: "'IBM Plex Mono'" } }, grid: { color: gridColor } },
        ...opts.scales
      },
      ...opts
    }
  });
}

/* ── NAVIGATION ─────────────────────────────────────────────── */
const pageLoaders = {
  upload:      () => loadDatasets(),
  dashboard:   () => loadDashboard(),
  copilot:     () => loadCopilot(),
  risk:        () => loadRisk(),
  workforce:   () => wfLoad('full'),
  recruitment: () => recLoad(),
  recommender: () => empInit(),
  social:      () => loadSocial(),
  compare:     () => loadCompare(),
  performance: () => perfLoad('pred'),
  wellbeing:   () => wbLoad('deep'),
  turnover:    () => tvLoad('compare'),
};

function nav(btn, page) {
  document.querySelectorAll('.nav-item').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  $(`page-${page}`).classList.add('active');
  if (pageLoaders[page]) pageLoaders[page]();
}

/* ── API STATUS ─────────────────────────────────────────────── */
async function checkApi() {
  const b = $('apiBadge'), label = $('apiLabel');
  try {
    await api('/api/health');
    b.className = 'api-badge online';
    label.textContent = 'API Online';
  } catch {
    b.className = 'api-badge offline';
    label.textContent = 'API Offline';
  }
}

function _appendChat(role, text) {
  const pane = $('copilotChat');
  if (!pane) return;
  const bubble = document.createElement('div');
  bubble.className = `chat-message ${role}`;
  bubble.style.padding = '12px 14px';
  bubble.style.borderRadius = '14px';
  bubble.style.maxWidth = '100%';
  bubble.style.whiteSpace = 'pre-wrap';
  bubble.style.wordBreak = 'break-word';
  bubble.style.background = role === 'user' ? 'rgba(56,189,248,0.12)' : 'rgba(255,255,255,0.08)';
  bubble.style.color = '#f8fafc';
  bubble.innerHTML = `<strong>${role === 'user' ? 'You' : 'Copilot'}</strong>: ${text}`;
  pane.appendChild(bubble);
  pane.scrollTop = pane.scrollHeight;
}

function loadCopilot() {
  const pane = $('copilotChat');
  if (!pane) return;
  pane.innerHTML = '<div class="chat-message bot"><strong>Copilot</strong>: Ask me for turnover insights, burnout risks, department work-life balance, or staffing projections.</div>';
  const query = $('copilotQuery');
  if (query) query.value = '';
}

async function sendCopilotQuery() {
  const queryEl = $('copilotQuery');
  if (!queryEl) return;
  const query = queryEl.value.trim();
  if (!query) return;
  _appendChat('user', query);
  queryEl.value = '';
  const bubble = document.createElement('div');
  bubble.className = 'chat-message bot';
  bubble.style.padding = '12px 14px';
  bubble.style.borderRadius = '14px';
  bubble.style.maxWidth = '100%';
  bubble.style.whiteSpace = 'pre-wrap';
  bubble.style.wordBreak = 'break-word';
  bubble.style.background = 'rgba(255,255,255,0.08)';
  bubble.style.color = '#f8fafc';
  bubble.innerHTML = '<span class="loading"><div class="spinner"></div>Thinking…</span>';
  $('copilotChat').appendChild(bubble);
  $('copilotChat').scrollTop = $('copilotChat').scrollHeight;
  try {
    const res = await api('/api/assistant/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: query }),
    });
    bubble.remove();
    _appendChat('bot', res.answer || 'I could not generate an answer.');
  } catch (e) {
    bubble.remove();
    _appendChat('bot', `⚠ ${e.message}`);
  }
}

function sendCopilotQuick(prompt) {
  const queryEl = $('copilotQuery');
  if (!queryEl) return;
  queryEl.value = prompt;
  sendCopilotQuery();
}

async function loadCompare() {
  spin('compareDepartments');
  spin('compareTeams');
  spin('compareManagers');
  spin('compareInsights');
  try {
    const data = await api('/api/compare/overview');
    const deptRows = data.departments.map(d => `
      <div class="row"><strong>${d.department}</strong> · Turnover ${d.turnover_rate_pct ?? 'N/A'}% · Perf ${d.avg_performance_rating ?? 'N/A'} · Engagement ${d.avg_engagement ?? 'N/A'} · Overtime ${d.overtime_pct ?? 'N/A'}%</div>
      <div class="row" style="font-size:0.95rem;color:var(--text-dim)">Insights: ${d.insights.length ? d.insights.join(', ') : 'No major flags'}. ${d.notes}</div>
    `).join('');

    const teamRows = data.teams.map(t => `
      <div class="row"><strong>${t.team}</strong> · Members ${t.member_count} · Cohesion ${t.team_cohesion} · Hobbies ${t.avg_hobby_count} · Sports ${t.avg_sports_count}</div>
      <div class="row" style="font-size:0.95rem;color:var(--text-dim)">Insights: ${t.insights.join(', ')} · Top hobbies: ${t.top_hobbies.join(', ') || 'n/a'}</div>
    `).join('');

    const managerHtml = data.managers.available === false ? `<div class="row">${data.managers.message}</div>` : data.managers.managers.map(m => `
      <div class="row"><strong>${m.manager}</strong> · Records ${m.record_count}</div>
      <div class="row" style="font-size:0.95rem;color:var(--text-dim)">${m.notes}</div>
    `).join('');

    set('compareDepartments', deptRows || '<div class="row">No department comparison available.</div>');
    set('compareTeams', teamRows || '<div class="row">No team comparison available.</div>');
    set('compareManagers', managerHtml || '<div class="row">No manager comparison available.</div>');
    set('compareInsights', data.insights.length ? `<ol>${data.insights.map(i => `<li>${i}</li>`).join('')}</ol>` : '<div class="row">No additional insights generated.</div>');
  } catch(e) {
    oops('compareDepartments', e);
    set('compareTeams', '');
    set('compareManagers', '');
    set('compareInsights', '');
  }
}

/* ── UPLOAD ─────────────────────────────────────────────────── */
async function uploadFiles(files) {
  const msg = $('uploadMsg');
  for (const f of files) {
    msg.innerHTML = `<div class="alert alert-blue"><span>⬆</span><div class="body">Uploading ${f.name}…</div></div>`;
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await fetch(`${BASE}/api/upload`, { method: 'POST', body: fd });
      const d = await r.json();
      msg.innerHTML = `<div class="alert alert-green"><span>✓</span><div class="body">${f.name} uploaded · ${d.columns?.length} columns</div></div>`;
    } catch(e) { msg.innerHTML = `<div class="err-box">Upload failed: ${e.message}</div>`; }
  }
  loadDatasets();
}

const dz = document.getElementById('dropZone');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag'); uploadFiles(e.dataTransfer.files); });

async function loadDatasets() {
  try {
    const data = await api('/api/datasets');
    const MAP = { medical_staff:'Workforce', recruitment:'Recruitment', recommender:'Recommender', performance:'Performance', wellbeing:'Well-Being', turnover:'Turnover' };
    const CLS = { Workforce:'green', Recruitment:'blue', Recommender:'blue', Performance:'amber', 'Well-Being':'green', Turnover:'amber' };
    set('datasetList', data.map(d => {
      const key = Object.keys(MAP).find(k => d.filename.toLowerCase().includes(k)) || 'data';
      const label = MAP[key] || 'Dataset'; const cls = CLS[label] || 'dim';
      return `<div class="ds-row">
        <div><div class="ds-name">${d.filename}</div><div class="ds-meta">${(d.rows||0).toLocaleString()} rows · ${d.columns} columns</div></div>
        <span class="badge badge-${cls}">${label}</span>
      </div>`;
    }).join(''));
  } catch(e) { oops('datasetList', e); }
}

/* ── DASHBOARD ──────────────────────────────────────────────── */
async function loadDashboard() {
  spin('dashContent');
  try {
    const [tv, wb, pf] = await Promise.all([api('/api/turnover/eda'), api('/api/wellbeing/eda'), api('/api/performance/train?model_type=random_forest')]);
    const tr = tv.overall_turnover_rate_pct, wlb = wb.target_stats.mean, acc = pf.metrics.accuracy;
    set('dashContent', `
      <div class="grid-4">
        <div class="stat"><div class="stat-label">Turnover Rate</div><div class="stat-value ${tr>20?'red':'amber'}">${tr}%</div><div class="stat-sub">of 12,739 employees</div></div>
        <div class="stat"><div class="stat-label">Avg WLB Score</div><div class="stat-value green">${wlb}</div><div class="stat-sub">out of ~800</div></div>
        <div class="stat"><div class="stat-label">Perf Model Acc</div><div class="stat-value blue">${(acc*100).toFixed(1)}%</div><div class="stat-sub">Random Forest</div></div>
        <div class="stat"><div class="stat-label">Satisfaction (left)</div><div class="stat-value red">${tv.avg_satisfaction_who_left}</div><div class="stat-sub">vs ${tv.avg_satisfaction_who_stayed} who stayed</div></div>
      </div>
      <div class="grid-2">
        <div class="card"><div class="card-title">Turnover by Salary</div><div class="chart-box" style="height:200px"><canvas id="dashTvChart"></canvas></div></div>
        <div class="card"><div class="card-title">WLB Score by Age Group</div><div class="chart-box" style="height:200px"><canvas id="dashWbChart"></canvas></div></div>
      </div>
      <div class="card"><div class="card-title">Performance Rating Distribution</div><div class="chart-box" style="height:180px"><canvas id="dashPfChart"></canvas></div></div>
    `);
    setTimeout(() => {
      const sal = tv.turnover_rate_by_salary_pct || {};
      const wlbA = wb.wlb_by_age_group || {};
      const cls = pf.per_class_metrics || {};
      mkChart('dashTvChart','bar',Object.keys(sal),[{data:Object.values(sal),backgroundColor:Object.values(sal).map(v=>rc(v/100)+'99'),borderRadius:4}],{scales:{y:{ticks:{callback:v=>v+'%',color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      const av = Object.values(wlbA);
      mkChart('dashWbChart','bar',Object.keys(wlbA),[{data:av,backgroundColor:'rgba(0,229,160,0.6)',borderRadius:4}],{scales:{y:{min:Math.min(...av)-15,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      mkChart('dashPfChart','bar',Object.keys(cls).map(k=>`Rating ${k}`),[{data:Object.keys(cls).map(k=>cls[k].support||0),backgroundColor:['rgba(56,189,248,0.7)','rgba(0,229,160,0.7)','rgba(167,139,250,0.7)'],borderRadius:4}]);
    },60);
  } catch(e) { oops('dashContent', e); }
}

/* ── MANUAL ENTRY FORM ──────────────────────────────────────── */
const FORM_SCHEMAS = {
  turnover: {
    fields: [
      { name:'satisfaction_level',    label:'Satisfaction Level (0–1)', type:'number', min:0, max:1, step:0.01, placeholder:'0.45' },
      { name:'last_evaluation',       label:'Last Evaluation (0–1)',    type:'number', min:0, max:1, step:0.01, placeholder:'0.57' },
      { name:'number_patients',       label:'Number of Patients',       type:'number', min:0, placeholder:'2' },
      { name:'average_montly_hours',  label:'Avg Monthly Hours',        type:'number', min:0, placeholder:'134' },
      { name:'time_spend_clinic',     label:'Years at Clinic',          type:'number', min:0, placeholder:'3' },
      { name:'Work_accident',         label:'Work Accident',            type:'select', options:[['0','No'],['1','Yes']] },
      { name:'left',                  label:'Left Clinic',              type:'select', options:[['0','No'],['1','Yes']] },
      { name:'promotion_last_5years', label:'Promoted (last 5 yrs)',    type:'select', options:[['0','No'],['1','Yes']] },
      { name:'job_role',              label:'Job Role',                 type:'select', options:[['family_nursing','Family Nursing'],['critical_care_nursing','Critical Care'],['occupational_health_nursing','Occupational Health'],['gerontological_nursing','Gerontological']] },
      { name:'salary',                label:'Salary Band',              type:'select', options:[['low','Low'],['medium','Medium'],['high','High']] },
    ]
  },
  wellbeing: {
    fields: [
      { name:'GENDER',                  label:'Gender',                    type:'select', options:[['Female','Female'],['Male','Male']] },
      { name:'AGE',                     label:'Age Range',                 type:'select', options:[['less than 20','Under 20'],['20 to 35','20–35'],['36 to 50','36–50'],['51 or more','51+']] },
      { name:'DAILY_STRESS',            label:'Daily Stress (1–5)',        type:'number', min:1, max:5, placeholder:'2' },
      { name:'SOCIAL_NETWORK',          label:'Social Network (1–10)',     type:'number', min:1, max:10, placeholder:'5' },
      { name:'ACHIEVEMENT',             label:'Achievement (1–10)',        type:'number', min:1, max:10, placeholder:'5' },
      { name:'BMI_RANGE',               label:'BMI Range (1–4)',           type:'number', min:1, max:4, placeholder:'2' },
      { name:'TODO_COMPLETED',          label:'Todos Completed (1–10)',    type:'number', min:1, max:10, placeholder:'6' },
      { name:'DAILY_STEPS',             label:'Daily Steps (1–10)',        type:'number', min:1, max:10, placeholder:'5' },
      { name:'SLEEP_HOURS',             label:'Sleep Hours',               type:'number', min:4, max:12, placeholder:'7' },
      { name:'SUFFICIENT_INCOME',       label:'Sufficient Income',         type:'select', options:[['1','Yes'],['0','No']] },
      { name:'PERSONAL_AWARDS',         label:'Personal Awards (0–10)',    type:'number', min:0, max:10, placeholder:'4' },
      { name:'TIME_FOR_HOBBY',          label:'Hobby Time (0–10)',         type:'number', min:0, max:10, placeholder:'3' },
      { name:'WEEKLY_MEDITATION',       label:'Weekly Meditation (0–10)', type:'number', min:0, max:10, placeholder:'5' },
      { name:'WORK_LIFE_BALANCE_SCORE', label:'WLB Score (optional)',      type:'number', min:0, max:1000, placeholder:'600' },
    ]
  },
  recruitment: {
    fields: [
      { name:'gender',    label:'Gender',           type:'select', options:[['m','Male'],['f','Female']] },
      { name:'location',  label:'Location',         type:'text',   placeholder:'de_south' },
      { name:'experience',label:'Experience (yrs)', type:'number', min:0, placeholder:'7' },
      { name:'education', label:'Education',        type:'select', options:[['bachelor','Bachelor'],['master','Master'],['phd','PhD']] },
      { name:'field',     label:'Field',            type:'text',   placeholder:'family nurse practitioner' },
      { section: 'Skills' },
      { name:'communication',      label:'Communication',    type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'empathy',            label:'Empathy',          type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'confidence',         label:'Confidence',       type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'professional',       label:'Professional',     type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'patience',           label:'Patience',         type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'management',         label:'Management',       type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'commitment',         label:'Commitment',       type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'critical thinking',  label:'Critical Thinking',type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'support',            label:'Support',          type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { section: 'Outcome' },
      { name:'hired',                         label:'Hired',               type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'family_nurse',                  label:'Family Nurse',        type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'occupational_health_nursing',   label:'Occupational Health', type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'critical_care_nursing',         label:'Critical Care',       type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
      { name:'gerontological_nursing',        label:'Gerontological',      type:'select', options:[['TRUE','Yes'],['FALSE','No']] },
    ]
  }
};

let _activeFormTab = 'turnover';

function switchFormTab(tab) {
  _activeFormTab = tab;
  document.querySelectorAll('.form-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  renderForm();
}

function renderForm() {
  const fields = FORM_SCHEMAS[_activeFormTab].fields;
  const rows = fields.map(f => {
    if (f.section) return `<div class="form-section">${f.section}</div>`;
    const id = `ff_${f.name.replace(/\s+/g,'_')}`;
    const input = f.type === 'select'
      ? `<select id="${id}">${f.options.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select>`
      : `<input type="${f.type}" id="${id}"${f.min!=null?` min="${f.min}"`:''}${f.max!=null?` max="${f.max}"`:''}${f.step?` step="${f.step}"`:''}${f.placeholder?` placeholder="${f.placeholder}"`:''}${f.type==='text'?` style="width:100%"`:''}> `;
    return `<div class="form-field"><label class="form-label">${f.label}</label>${input}</div>`;
  });
  rows.push(`<div class="form-actions">
    <button class="btn btn-primary btn-sm" onclick="submitManualEntry()">Add Row</button>
    <button class="btn btn-sm btn-ghost" onclick="renderForm()">Reset</button>
    <span class="form-status" id="formStatus"></span>
  </div>`);
  set('manualFormBody', `<div class="form-grid">${rows.join('')}</div>`);
}

async function submitManualEntry() {
  const fields = FORM_SCHEMAS[_activeFormTab].fields;
  const row = { _dataset: _activeFormTab };
  for (const f of fields) {
    if (f.section) continue;
    const el = document.getElementById(`ff_${f.name.replace(/\s+/g,'_')}`);
    if (!el || el.value === '') continue;
    row[f.name] = f.type === 'number' ? Number(el.value) : el.value;
  }
  const status = $('formStatus');
  status.style.color = 'var(--muted)';
  status.textContent = 'Saving…';
  try {
    const res = await api('/api/manual-entry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(row)
    });
    status.style.color = 'var(--green)';
    status.textContent = `✓ Added — ${res.total_rows} rows total`;
    loadDatasets();
  } catch(e) {
    status.style.color = 'var(--red)';
    status.textContent = `✗ ${e.message}`;
  }
}

/* ── INIT ───────────────────────────────────────────────────── */
checkApi();
setInterval(checkApi, 15000);
loadDatasets();
loadDashboard();
renderForm();

/* ── REPORTS UI ────────────────────────────────────────────── */
async function generateReport() {
  const msg = $('reportsMsg'); msg.textContent = 'Generating report…';
  try {
    const res = await api('/api/reports/generate', { method: 'POST' });
    msg.textContent = `Saved ${res.filename}`;
    refreshReports();
  } catch(e) { msg.textContent = `Error: ${e.message}`; }
}

async function loadSocial() {
  set('isolatedList', `<div class="loading"><div class="spinner"></div>Loading…</div>`);
  set('influencerList', `<div class="loading"><div class="spinner"></div>Loading…</div>`);
  try {
    const res = await api('/api/social/analysis');
    // isolated
    const iso = res.isolated || [];
    set('isolatedList', iso.length ? `<ul>${iso.map(i=>`<li>${i}</li>`).join('')}</ul>` : '<div>No isolated employees found</div>');
    // influencers by degree
    const inf = res.top_by_degree || [];
    set('influencerList', inf.length ? `<ol>${inf.map(i=>`<li>${i.id} — ${(i.score).toFixed(3)}</li>`).join('')}</ol>` : '<div>No influencers detected</div>');
    // refresh image with cache-bust
    const img = $('socialGraphImg'); img.src = `/api/social/graph.png?ts=${Date.now()}`;
  } catch(e) {
    set('isolatedList', `<div class="err-box">${e.message}</div>`);
    set('influencerList', `<div class="err-box">${e.message}</div>`);
  }
}

async function refreshReports() {
  const sel = $('reportsList'); sel.innerHTML = '';
  try {
    const res = await api('/api/reports/list');
    const reps = res.reports || [];
    if (!reps.length) { $('reportsMsg').textContent = 'No saved reports found'; return; }
    reps.forEach(r => {
      const opt = document.createElement('option'); opt.value = r.filename; opt.textContent = `${r.filename} (${(r.size/1024).toFixed(1)} KB)`; sel.appendChild(opt);
    });
    $('reportsMsg').textContent = `Found ${reps.length} reports`;
  } catch(e) { $('reportsMsg').textContent = `Error: ${e.message}`; }
}

function downloadSelected() {
  const sel = $('reportsList'); if (!sel.value) { $('reportsMsg').textContent = 'Select a report first'; return; }
  const url = `${BASE}/api/reports/download?filename=${encodeURIComponent(sel.value)}`;
  window.open(url, '_blank');
}

async function downloadLatest() {
  try {
    const res = await api('/api/reports/list');
    const first = res.reports && res.reports.length ? res.reports[0].filename : null;
    if (!first) { $('reportsMsg').textContent = 'No reports to download'; return; }
    window.open(`${BASE}/api/reports/download?filename=${encodeURIComponent(first)}`, '_blank');
  } catch(e) { $('reportsMsg').textContent = `Error: ${e.message}`; }
}

// Refresh reports list on load
refreshReports();

/* ── RISK DASHBOARD ───────────────────────────────────────── */
async function loadRisk() {
  const ids = ['riskBurnout','riskQuiet','riskTurnover','riskProd','riskToxic','riskOverworked'];
  ids.forEach(id=>set(id,'<div class="loading"><div class="spinner"></div>Loading…</div>'));
  try {
    const res = await api('/api/risk/overview');
    // Burnout
    const b = res.burnout || {};
    set('riskBurnout', `<div>Estimated flags: <strong>${b.count||0}</strong></div>${b.by_gender?'<div>By gender: '+Object.entries(b.by_gender).map(([k,v])=>`${k}: ${v}`).join(', ')+'</div>':''}${b.by_age?'<div>By age: '+Object.entries(b.by_age).map(([k,v])=>`${k}: ${v}`).join(', ')+'</div>':''}`);
    // Quiet quitting
    const q = res.quiet_quitting || {};
    set('riskQuiet', `<div>Estimated count: <strong>${q.count||0}</strong></div><div>${q.examples && q.examples.length?'<em>Examples:</em> '+q.examples.map(e=>e.EmpNumber).join(', '):''}</div>`);
    // Turnover
    const t = res.turnover_risk || {};
    set('riskTurnover', `<div>Model sample score: <strong>${t.model_score_sample? (t.model_score_sample.toFixed(3)) : 'n/a'}</strong></div><div>${t.top_roles_by_risk?Object.entries(t.top_roles_by_risk).map(([k,v])=>`<div>${k}: ${(v*100).toFixed(1)}%</div>`).join(''):''}</div>`);
    // Productivity
    const p = res.productivity_decline || {};
    set('riskProd', `<div>Count: <strong>${p.count||0}</strong></div><div>${p.examples?'<em>Examples:</em> '+p.examples.map(e=>e.EmpNumber).join(', '):''}</div>`);
    // Toxic
    const tox = res.toxic_teams || {};
    set('riskToxic', `<div>High-turnover roles: ${Object.keys(tox.roles_high_turnover||{}).length?Object.entries(tox.roles_high_turnover).map(([k,v])=>`<div>${k}: ${v}%</div>`).join(''):'n/a'}</div><div>${tox.toxic_candidates?Object.entries(tox.toxic_candidates).map(([k,v])=>`<div>${k}: ${v}%</div>`).join(''):''}</div>`);
    // Overworked
    const o = res.overworked || {};
    set('riskOverworked', `<div>Overall avg hours: <strong>${o.overall_avg_hours||'n/a'}</strong></div>${o.overworked_roles?Object.entries(o.overworked_roles).map(([k,v])=>`<div>${k}: ${v} avg hrs</div>`).join(''):''}`);
  } catch(e) {
    ids.forEach(id=>set(id, `<div class="err-box">${e.message}</div>`));
  }
}

async function employeeRisk() {
  const emp = $('empIdInput').value.trim();
  const out = $('empRiskResult');
  if (!emp) { out.textContent = 'Enter an EmpNumber to lookup'; return; }
  out.innerHTML = `<div class="loading"><div class="spinner"></div>Lookup ${emp}…</div>`;
  try {
    const res = await api('/api/risk/employee?emp='+encodeURIComponent(emp));
    const prof = res.profile || {};
    out.innerHTML = `<div><strong>${emp}</strong> — QuietQuittingRisk: ${prof.quiet_quitting_risk?'<span class="badge badge-red">HIGH</span>':'<span class="badge badge-green">LOW</span>'} TurnoverProb: ${prof.turnover_probability||'n/a'}</div><pre style="white-space:pre-wrap;margin-top:8px">${JSON.stringify(prof, null, 2)}</pre>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

/* ── PREDICTION UI HELPERS ─────────────────────────────────── */
async function uiPredictRetention() {
  const emp = $('predEmpNumber').value.trim();
  const out = $('predEmpResult'); out.innerHTML = `<div class="loading"><div class="spinner"></div>Predicting…</div>`;
  try {
    const res = await api('/api/predict/retention', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ EmpNumber: emp }) });
    out.innerHTML = `<div>Retention: <strong>${(res.retention_probability*100).toFixed(1)}%</strong> · Leave: ${(res.leave_probability*100).toFixed(1)}%</div><pre style="white-space:pre-wrap">${JSON.stringify(res, null, 2)}</pre>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

async function uiPredictPerformance() {
  const emp = $('predEmpNumber').value.trim();
  const out = $('predEmpResult'); out.innerHTML = `<div class="loading"><div class="spinner"></div>Predicting…</div>`;
  try {
    const res = await api('/api/predict/performance', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ EmpNumber: emp }) });
    out.innerHTML = `<div>High performance probability: <strong>${(res.high_performance_probability*100).toFixed(1)}%</strong></div><pre style="white-space:pre-wrap">${JSON.stringify(res, null, 2)}</pre>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

async function uiCandidateFit() {
  const team = $('candTeam').value.trim();
  const exp = $('candExp').value.trim();
  const hobbies = $('candHobbies').value.trim();
  const skills = ($('candSkills').value||'').split(',').map(s=>s.trim()).filter(Boolean);
  const out = $('predCandResult'); out.innerHTML = `<div class="loading"><div class="spinner"></div>Calculating…</div>`;
  try {
    const res = await api('/api/predict/candidate-fit', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ target_team: team, previous_experience: exp, hobbies: hobbies, skills: skills }) });
    out.innerHTML = `<div>Fit Score: <strong>${(res.fit_score*100).toFixed(1)}%</strong></div><pre style="white-space:pre-wrap">${JSON.stringify(res, null, 2)}</pre>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

async function uiCultureFit() {
  const team = $('candTeam').value.trim();
  const hobbies = $('candHobbies').value.trim();
  const out = $('predCandResult'); out.innerHTML = `<div class="loading"><div class="spinner"></div>Calculating…</div>`;
  try {
    const res = await api('/api/predict/culture-fit', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ target_team: team, hobbies: hobbies }) });
    out.innerHTML = `<div>Culture Fit: <strong>${(res.culture_fit_score*100).toFixed(1)}%</strong></div><pre style="white-space:pre-wrap">${JSON.stringify(res, null, 2)}</pre>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

async function trainPersistModels() {
  const msg = $('predEmpResult'); msg.innerHTML = `<div class="loading"><div class="spinner"></div>Training & saving models…</div>`;
  try {
    const res = await api('/api/predict/models/train', { method: 'POST' });
    msg.innerHTML = `<div>Training complete: <pre style="white-space:pre-wrap">${JSON.stringify(res,null,2)}</pre></div>`;
  } catch(e) { msg.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

async function uiScenarioPredict() {
  const salary = Number($('scenarioSalary').value) || 0;
  const overtime = Number($('scenarioOvertime').value) || 0;
  const remote = $('scenarioRemote').value;
  const out = $('scenarioResult'); out.innerHTML = `<div class="loading"><div class="spinner"></div>Simulating scenario…</div>`;
  try {
    const res = await api('/api/predict/scenario', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ salary_increase_pct: salary, overtime_reduction_pct: overtime, remote_work_policy: remote }),
    });
    const p = res.predictions;
    out.innerHTML = `<div class="scenario-summary">
      <div><strong>Turnover predicted:</strong> ${p.turnover_rate_pct}% (${p.turnover_reduction_pct}% reduction)</div>
      <div><strong>WLB predicted:</strong> ${p.wlb_mean} (+${p.wlb_improvement_pct}%)</div>
      <div><strong>Hiring needs:</strong> ${p.predicted_hiring_needs} employees (${p.hiring_need_change_pct}% change)</div>
      <div><strong>Performance impact:</strong> ${p.performance_rating_mean} mean rating (+${p.performance_impact_pct}%)</div>
      <pre style="white-space:pre-wrap;margin-top:8px">${JSON.stringify(res, null, 2)}</pre>
    </div>`;
  } catch(e) { out.innerHTML = `<div class="err-box">${e.message}</div>`; }
}

function resetScenarioInputs() {
  $('scenarioSalary').value = 0;
  $('scenarioOvertime').value = 0;
  $('scenarioRemote').value = 'none';
  $('scenarioResult').textContent = 'No scenario run yet.';
}
