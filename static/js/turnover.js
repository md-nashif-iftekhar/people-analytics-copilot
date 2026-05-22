async function tvLoad(view) {
  spin('tvContent');
  try {
    if (view === 'compare') {
      const d = await api('/api/turnover/compare-models');
      const models = d.models||{}, best = d.best_model||'';
      const mNames = {random_forest:'Random Forest',logistic_regression:'Logistic Regression',xgboost:'XGBoost (GBM)'};
      const mCols  = {random_forest:'var(--green)',logistic_regression:'var(--blue)',xgboost:'var(--amber)'};
      set('tvContent', `
        <div class="alert alert-green"><span>⚡</span><div class="body">${d.recommendation}</div></div>
        <div class="grid-3">${Object.entries(models).map(([name,m])=>`
          <div class="model-card ${name===best?'best':''}">
            <div class="model-name" style="color:${mCols[name]}">${name===best?'⭐ ':''} ${mNames[name]||name}</div>
            <div class="model-metrics">
              <div class="mm"><div class="mm-val" style="color:${mCols[name]}">${(m.accuracy*100).toFixed(1)}%</div><div class="mm-label">Accuracy</div></div>
              <div class="mm"><div class="mm-val" style="color:${mCols[name]}">${m.roc_auc}</div><div class="mm-label">AUC</div></div>
              <div class="mm"><div class="mm-val" style="color:${mCols[name]}">${(m.f1_score*100).toFixed(1)}%</div><div class="mm-label">F1</div></div>
              <div class="mm"><div class="mm-val" style="color:${mCols[name]}">${m.cv5_auc}</div><div class="mm-label">CV-5</div></div>
            </div>
            <div style="margin-top:10px;font-size:11px;color:var(--muted)">Top feature: <strong style="color:var(--text);font-family:var(--mono)">${m.top_feature}</strong></div>
          </div>`).join('')}
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">ROC AUC Comparison</div><div class="chart-box" style="height:180px"><canvas id="tvAucChart"></canvas></div></div>
          <div class="card"><div class="card-title">Accuracy Comparison</div><div class="chart-box" style="height:180px"><canvas id="tvAccChart"></canvas></div></div>
        </div>`);
      setTimeout(()=>{
        const names=Object.keys(models).map(k=>mNames[k]), cols=Object.keys(models).map(k=>mCols[k].replace('var(--green)','rgba(0,229,160,.7)').replace('var(--blue)','rgba(56,189,248,.7)').replace('var(--amber)','rgba(245,158,11,.7)'));
        mkChart('tvAucChart','bar',names,[{data:Object.values(models).map(m=>m.roc_auc),backgroundColor:cols,borderRadius:4}],{scales:{y:{min:0.7,max:1,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
        mkChart('tvAccChart','bar',names,[{data:Object.values(models).map(m=>(m.accuracy*100).toFixed(1)),backgroundColor:cols,borderRadius:4}],{scales:{y:{min:70,ticks:{callback:v=>v+'%',color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },50);

    } else if (view === 'train') {
      const model = $('tvModel').value;
      const d = await api(`/api/turnover/train?model_type=${model}&top_n_employees=20`);
      const m = d.metrics, fi = Object.entries(d.feature_importance||{}).slice(0,8);
      const cm = d.confusion_matrix||{}, seg = d.risk_segments||{};
      const emp = d.top_risk_employees||[], ins = d.auto_insights||[];
      const dist = d.attrition_prob_distribution||{};
      const rCol = p => p>=0.75?'var(--red)':p>=0.5?'var(--amber)':p>=0.25?'var(--blue)':'var(--green)';
      set('tvContent', `
        ${ins.map(i=>`<div class="alert alert-green" style="margin-bottom:6px"><span>↺</span><div class="body">${i}</div></div>`).join('')}
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Accuracy</div><div class="stat-value green">${(m.accuracy*100).toFixed(1)}%</div></div>
          <div class="stat"><div class="stat-label">ROC AUC</div><div class="stat-value blue">${m.roc_auc}</div></div>
          <div class="stat"><div class="stat-label">F1 Score</div><div class="stat-value purple">${(m.f1_score*100).toFixed(1)}%</div></div>
          <div class="stat"><div class="stat-label">CV-5 AUC</div><div class="stat-value amber">${m.cv5_auc}</div></div>
        </div>
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Critical Risk ≥75%</div><div class="stat-value red">${seg.critical||0}</div></div>
          <div class="stat"><div class="stat-label">High Risk 50–75%</div><div class="stat-value amber">${seg.high||0}</div></div>
          <div class="stat"><div class="stat-label">Medium Risk 25–50%</div><div class="stat-value blue">${seg.medium||0}</div></div>
          <div class="stat"><div class="stat-label">Low Risk &lt;25%</div><div class="stat-value green">${seg.low||0}</div></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Feature Importance</div>${fi.map(([n,v])=>`<div class="bar-row"><div class="bar-label">${n}</div><div class="bar-track"><div class="bar-fill blue" style="width:${v/fi[0][1]*100}%"></div></div><div class="bar-val">${v}</div></div>`).join('')}</div>
          <div class="card"><div class="card-title">Confusion Matrix</div>
            <div class="cm-grid">
              <div class="cm-cell" style="background:rgba(0,229,160,.08);border-color:rgba(0,229,160,.2)"><div class="cm-val" style="color:var(--green)">${cm.true_negatives}</div><div class="cm-label">True Negatives<br>Correctly stayed</div></div>
              <div class="cm-cell" style="background:rgba(248,113,113,.07);border-color:rgba(248,113,113,.2)"><div class="cm-val" style="color:var(--red)">${cm.false_positives}</div><div class="cm-label">False Positives<br>Predicted left, stayed</div></div>
              <div class="cm-cell" style="background:rgba(245,158,11,.07);border-color:rgba(245,158,11,.2)"><div class="cm-val" style="color:var(--amber)">${cm.false_negatives}</div><div class="cm-label">False Negatives<br>Missed leavers</div></div>
              <div class="cm-cell" style="background:rgba(56,189,248,.07);border-color:rgba(56,189,248,.2)"><div class="cm-val" style="color:var(--blue)">${cm.true_positives}</div><div class="cm-label">True Positives<br>Correctly predicted left</div></div>
            </div>
          </div>
        </div>
        <div class="card"><div class="card-title">Attrition Probability Distribution</div><div class="chart-box" style="height:180px"><canvas id="tvDistChart"></canvas></div></div>
        <div class="card">
          <div class="card-title">🔥 Highest Risk Employees</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>ID</th><th>Role</th><th>Salary</th><th>Satisfaction</th><th>Hrs/month</th><th>Attrition Prob</th><th>Risk</th><th>Actual</th></tr></thead>
            <tbody>${emp.slice(0,15).map(e=>`<tr>
              <td class="val">${e.index}</td>
              <td style="font-size:11px">${e.job_role}</td>
              <td>${badge(e.salary, e.salary==='low'?'red':e.salary==='medium'?'amber':'green')}</td>
              <td class="${e.satisfaction_level<0.4?'danger':'val'}">${e.satisfaction_level}</td>
              <td class="${e.average_montly_hours>250?'warn':'val'}">${e.average_montly_hours}</td>
              <td style="font-weight:600;color:${rCol(e.attrition_probability)};font-family:var(--mono)">${(e.attrition_probability*100).toFixed(1)}%</td>
              <td>${badge(e.risk_label, e.risk_label==='Critical'?'red':e.risk_label==='High'?'amber':'blue')}</td>
              <td style="color:${e.actual_left?'var(--red)':'var(--green)'}">${e.actual_left?'Left':'Stayed'}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>
        <div class="card"><div class="card-title">Retention Recommendations</div>${(d.retention_recommendations||[]).map(r=>`<div style="padding:9px 0;border-bottom:1px solid var(--border);font-size:12px;color:var(--muted)">→ ${r}</div>`).join('')}</div>`);
      setTimeout(()=>{
        const L=Object.keys(dist),V=Object.values(dist);
        mkChart('tvDistChart','bar',L,[{data:V,backgroundColor:L.map((_,i)=>i<4?'rgba(0,229,160,.6)':i<7?'rgba(245,158,11,.6)':'rgba(248,113,113,.7)'),borderRadius:3}],{scales:{x:{ticks:{color:'#6b7280',maxRotation:30,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },50);

    } else if (view === 'eda') {
      const d = await api('/api/turnover/eda');
      const byRole = d.turnover_rate_by_role_pct||{}, bySal = d.turnover_rate_by_salary_pct||{}, satRole = d.satisfaction_by_role||{};
      set('tvContent', `
        <div class="grid-3">
          <div class="stat"><div class="stat-label">Overall Turnover</div><div class="stat-value red">${d.overall_turnover_rate_pct}%</div></div>
          <div class="stat"><div class="stat-label">Satisfaction (left)</div><div class="stat-value amber">${d.avg_satisfaction_who_left}</div><div class="stat-sub">vs ${d.avg_satisfaction_who_stayed} who stayed</div></div>
          <div class="stat"><div class="stat-label">Avg Tenure (left)</div><div class="stat-value blue">${d.avg_tenure_years_who_left} yrs</div></div>
        </div>
        <div class="alert alert-amber"><span>↺</span><div class="body">${d.insight}</div></div>
        <div class="card"><div class="card-title">Turnover Rate by Role</div>
          ${Object.entries(byRole).sort((a,b)=>b[1]-a[1]).map(([role,pct])=>`<div class="risk-row">
            <div class="risk-name">${role.replace(/_/g,' ')}</div>
            <div class="risk-track"><div class="risk-fill" style="width:${pct}%;background:${rc(pct/100)}"></div></div>
            <div class="risk-pct" style="color:${rc(pct/100)}">${pct}%</div>
          </div>`).join('')}
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Turnover by Salary</div><div class="chart-box" style="height:200px"><canvas id="tvEdaSal"></canvas></div></div>
          <div class="card"><div class="card-title">Satisfaction by Role</div><div class="chart-box" style="height:200px"><canvas id="tvEdaSat"></canvas></div></div>
        </div>`);
      setTimeout(()=>{
        const sv=Object.values(bySal);
        mkChart('tvEdaSal','bar',Object.keys(bySal),[{data:sv,backgroundColor:sv.map(v=>rc(v/100)+'bb'),borderRadius:4}],{scales:{y:{ticks:{callback:v=>v+'%',color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
        mkChart('tvEdaSat','bar',Object.keys(satRole).map(k=>k.replace(/_/g,' ')),[{data:Object.values(satRole),backgroundColor:'rgba(167,139,250,.65)',borderRadius:4}],{indexAxis:'y',scales:{x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{size:10,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },50);

    } else if (view === 'risk') {
      const d = await api('/api/turnover/risk-profile');
      const segs = d.turnover_risk_by_segment||{};
      set('tvContent', `
        <div class="stat" style="width:fit-content"><div class="stat-label">Overall Turnover</div><div class="stat-value red">${d.overall_turnover_pct}%</div></div>
        ${Object.entries(segs).map(([grp,vals])=>`<div class="card">
          <div class="card-title">Turnover by ${grp.replace(/_/g,' ')}</div>
          ${Object.entries(vals).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="risk-row">
            <div class="risk-name">${k}</div>
            <div class="risk-track"><div class="risk-fill" style="width:${Math.min(v,100)}%;background:${rc(v/100)}"></div></div>
            <div class="risk-pct" style="color:${rc(v/100)}">${v}%</div>
          </div>`).join('')}
        </div>`).join('')}`);
    }
  } catch(e) { oops('tvContent', e); }
}
