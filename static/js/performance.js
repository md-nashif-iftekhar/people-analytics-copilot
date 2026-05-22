async function perfLoad(view) {
  spin('perfContent');
  try {
    if (view === 'pred') {
      const d = await api('/api/performance/predictions?top_n=20');
      const sc = d.segment_counts||{}, rs = d.role_summary||{}, sd = d.score_distributions||{}, ins = d.auto_insights||[];
      const hp = d.top_high_performers||[], br = d.top_burnout_risk||[], cr = d.critical_employees||[];
      const meth = d.score_methodology||{};
      const sBar = (v, col) => `<div style="display:flex;align-items:center;gap:8px"><div style="flex:1;height:5px;border-radius:3px;background:var(--raised);overflow:hidden"><div style="height:100%;width:${v}%;background:${col};border-radius:3px"></div></div><span style="font-family:var(--mono);font-size:10px;color:var(--muted);min-width:24px">${v}</span></div>`;
      const tagFor = t => { const m={'⭐ High Performer':'green','🔥 Burnout Risk':'amber','⚡ High Productivity':'blue','⚠ Critical — Act Now':'red','✓ Stable':'dim'}; return badge(t, m[t]||'dim'); };
      set('perfContent', `
        <div class="grid-5">
          <div class="stat"><div class="stat-label">Employees</div><div class="stat-value blue">${sc.total_employees}</div></div>
          <div class="stat"><div class="stat-label">High Performers</div><div class="stat-value green">${sc.high_performers}</div><div class="stat-sub">${(sc.high_performers/sc.total_employees*100).toFixed(1)}% of workforce</div></div>
          <div class="stat"><div class="stat-label">Burnout Risk</div><div class="stat-value red">${sc.burnout_risk}</div><div class="stat-sub">score ≥ 60</div></div>
          <div class="stat"><div class="stat-label">High Productivity</div><div class="stat-value purple">${sc.high_productivity}</div><div class="stat-sub">score ≥ 70</div></div>
          <div class="stat"><div class="stat-label">Critical Cases</div><div class="stat-value amber">${sc.critical_cases}</div><div class="stat-sub">high burn + low prod</div></div>
        </div>
        <div class="card"><div class="card-title">Auto Insights</div>${ins.map(i=>`<div class="alert alert-green" style="margin-bottom:6px"><span>◈</span><div class="body">${i}</div></div>`).join('')}</div>
        <div class="grid-3">
          <div class="card"><div class="card-title">Productivity Distribution</div><div class="chart-box" style="height:160px"><canvas id="pfProdDist"></canvas></div></div>
          <div class="card"><div class="card-title">Burnout Distribution</div><div class="chart-box" style="height:160px"><canvas id="pfBurnDist"></canvas></div></div>
          <div class="card"><div class="card-title">High Performer Distribution</div><div class="chart-box" style="height:160px"><canvas id="pfHpDist"></canvas></div></div>
        </div>
        <div class="card">
          <div class="card-title">Scores by Job Role</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Role</th><th>Avg Productivity</th><th>Avg Burnout</th><th>Avg HP Score</th><th>Burnout %</th><th>N</th></tr></thead>
            <tbody>${Object.entries(rs).map(([role,v])=>`<tr>
              <td class="val" style="font-size:11px">${role}</td>
              <td style="min-width:120px">${sBar(v.avg_productivity,'var(--green)')}</td>
              <td style="min-width:120px">${sBar(v.avg_burnout,v.avg_burnout>=50?'var(--red)':'var(--amber)')}</td>
              <td style="min-width:120px">${sBar(v.avg_high_performer,'var(--blue)')}</td>
              <td class="${v.burnout_risk_pct>=20?'warn':'val'}">${v.burnout_risk_pct}%</td>
              <td class="val">${v.count}</td>
            </tr>`).join('')}</tbody>
          </table></div>
          <div class="chart-box" style="height:200px;margin-top:16px"><canvas id="pfRoleChart"></canvas></div>
        </div>
        <div class="card ${cr.length?'':''}` + (cr.length?'" style="border-color:rgba(248,113,113,.3)':'"') + `>
          <div class="card-title" ${cr.length?'style="color:var(--red)"':''}>⭐ High Performers (top 15)</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Employee</th><th>Role</th><th>HP Score</th><th>Productivity</th><th>Burnout Risk</th><th>Tags</th></tr></thead>
            <tbody>${hp.slice(0,15).map(e=>`<tr>
              <td class="val">${e.emp_id}</td><td style="font-size:11px">${e.job_role}</td>
              <td class="hi">${e.high_performer_score}</td>
              <td class="val">${e.productivity_score}</td>
              <td class="${e.burnout_score>=60?'warn':'val'}">${e.burnout_score}</td>
              <td>${e.tags.map(tagFor).join(' ')}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>
        ${br.length?`<div class="card" style="border-color:rgba(245,158,11,.25)">
          <div class="card-title" style="color:var(--amber)">🔥 Burnout Risk Employees (top 15)</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Employee</th><th>Role</th><th>Burnout</th><th>Productivity</th><th>HP Score</th><th>Tags</th></tr></thead>
            <tbody>${br.slice(0,15).map(e=>`<tr>
              <td class="val">${e.emp_id}</td><td style="font-size:11px">${e.job_role}</td>
              <td class="warn">${e.burnout_score}</td>
              <td class="val">${e.productivity_score}</td>
              <td class="val">${e.high_performer_score}</td>
              <td>${e.tags.map(tagFor).join(' ')}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>`:''}
        ${cr.length?`<div class="card" style="border-color:rgba(248,113,113,.35)">
          <div class="card-title" style="color:var(--red)">⚠ Critical Cases — Immediate Attention</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Employee</th><th>Role</th><th>Burnout</th><th>Productivity</th></tr></thead>
            <tbody>${cr.map(e=>`<tr><td class="val">${e.emp_id}</td><td style="font-size:11px">${e.job_role}</td><td class="danger">${e.burnout_score}</td><td class="danger">${e.productivity_score}</td></tr>`).join('')}</tbody>
          </table></div>
        </div>`:''}
        <div class="card"><div class="card-title">Score Methodology</div>
          ${Object.entries(meth).map(([k,v])=>`<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px"><span style="color:var(--green);font-family:var(--mono);min-width:160px">${k.replace(/_/g,' ')}</span><span style="color:var(--muted)">${v}</span></div>`).join('')}
        </div>`);
      setTimeout(()=>{
        const mkDist=(id,dist,col)=>{const L=Object.keys(dist),V=Object.values(dist);mkChart(id,'bar',L,[{data:V,backgroundColor:col,borderRadius:3}],{scales:{x:{ticks:{color:'#6b7280',maxRotation:45,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});};
        mkDist('pfProdDist',sd.productivity||{},'rgba(0,229,160,.6)');
        mkDist('pfBurnDist',sd.burnout||{},'rgba(248,113,113,.6)');
        mkDist('pfHpDist',sd.high_performer||{},'rgba(56,189,248,.6)');
        const roles=Object.keys(rs);
        mkChart('pfRoleChart','bar',roles,[
          {label:'Productivity',data:roles.map(r=>rs[r].avg_productivity),backgroundColor:'rgba(0,229,160,.6)',borderRadius:3},
          {label:'Burnout Risk',data:roles.map(r=>rs[r].avg_burnout),backgroundColor:'rgba(248,113,113,.55)',borderRadius:3},
          {label:'HP Score',data:roles.map(r=>rs[r].avg_high_performer),backgroundColor:'rgba(56,189,248,.55)',borderRadius:3},
        ],{plugins:{legend:{display:true,position:'top',labels:{color:'#9ca3af',boxWidth:10,font:{family:"'IBM Plex Mono'",size:10}}}},scales:{x:{ticks:{color:'#6b7280',font:{size:9,family:"'IBM Plex Mono'"},maxRotation:30},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },60);

    } else if (view === 'eda') {
      const d = await api('/api/performance/eda');
      const rolePref = d.role_based_performance||{}, dist = d.target_distribution||{};
      set('perfContent', `
        <div class="grid-3">
          <div class="stat"><div class="stat-label">Records</div><div class="stat-value blue">${d.dataset_info?.rows}</div></div>
          <div class="stat"><div class="stat-label">Features</div><div class="stat-value green">${d.dataset_info?.columns?.length}</div></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Performance by Job Role</div>
            <div class="tbl-wrap"><table><thead><tr><th>Role</th><th>Avg Rating</th><th>Count</th><th>Std Dev</th></tr></thead>
            <tbody>${Object.entries(rolePref).map(([role,s])=>`<tr><td class="val">${role}</td><td class="hi">${s.mean}</td><td class="val">${s.count}</td><td class="val">${s.std}</td></tr>`).join('')}</tbody></table></div>
          </div>
          <div class="card"><div class="card-title">Rating Distribution</div><div class="chart-box" style="height:200px"><canvas id="pfEdaDist"></canvas></div></div>
        </div>`);
      setTimeout(()=>{mkChart('pfEdaDist','bar',Object.keys(dist).map(k=>`Rating ${k}`),[{data:Object.values(dist),backgroundColor:['rgba(56,189,248,.7)','rgba(0,229,160,.7)','rgba(167,139,250,.7)'],borderRadius:4}]);},50);

    } else if (view === 'corr') {
      const d = await api('/api/performance/correlation');
      const pos = d.top_positive_correlates||{}, neg = d.top_negative_correlates||{};
      const all = [...Object.entries(pos).map(([k,v])=>({k,v,dir:'pos'})),...Object.entries(neg).map(([k,v])=>({k,v,dir:'neg'}))].sort((a,b)=>Math.abs(b.v)-Math.abs(a.v));
      set('perfContent', `<div class="card"><div class="card-title">Correlation with PerformanceRating</div>
        <div class="alert alert-blue" style="margin-bottom:16px"><span>◎</span><div class="body">Green = positive. Red = negative. Longer bar = stronger relationship.</div></div>
        ${all.map(c=>`<div class="bar-row"><div class="bar-label">${c.k}</div><div class="bar-track"><div class="bar-fill ${c.dir==='pos'?'green':'red'}" style="width:${Math.abs(c.v)*100}%"></div></div><div class="bar-val" style="color:${c.dir==='pos'?'var(--green)':'var(--red)'}">${c.v}</div></div>`).join('')}
      </div>`);

    } else if (view === 'train') {
      const model = $('perfModel').value, split = $('perfSplit').value;
      const d = await api(`/api/performance/train?model_type=${model}&test_size=${split}`);
      const m = d.metrics, fi = Object.entries(d.feature_importance||{}).slice(0,8), samp = d.sample_predictions||[];
      set('perfContent', `
        <div class="alert alert-green"><span>▲</span><div class="body">${d.interpretation?.accuracy} Top driver: <strong>${d.interpretation?.top_driver}</strong></div></div>
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Accuracy</div><div class="stat-value green">${(m.accuracy*100).toFixed(1)}%</div></div>
          <div class="stat"><div class="stat-label">Precision</div><div class="stat-value blue">${(m.precision*100).toFixed(1)}%</div></div>
          <div class="stat"><div class="stat-label">Recall</div><div class="stat-value purple">${(m.recall*100).toFixed(1)}%</div></div>
          <div class="stat"><div class="stat-label">F1 Score</div><div class="stat-value amber">${(m.f1_score*100).toFixed(1)}%</div></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Feature Importance</div>${fi.map(([n,v])=>`<div class="bar-row"><div class="bar-label">${n}</div><div class="bar-track"><div class="bar-fill blue" style="width:${v/fi[0][1]*100}%"></div></div><div class="bar-val">${v}</div></div>`).join('')}</div>
          <div class="card"><div class="card-title">Sample Predictions</div>
            <div class="tbl-wrap"><table><thead><tr><th>#</th><th>Actual</th><th>Predicted</th><th>✓</th></tr></thead>
            <tbody>${samp.map((p,i)=>`<tr><td>${i+1}</td><td class="val">${p.actual}</td><td class="${p.correct?'hi':'danger'}">${p.predicted}</td><td style="color:${p.correct?'var(--green)':'var(--red)'}">${p.correct?'✓':'✗'}</td></tr>`).join('')}</tbody></table></div>
          </div>
        </div>`);
    }
  } catch(e) { oops('perfContent', e); }
}
