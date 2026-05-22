async function wbLoad(view) {
  spin('wbContent');
  try {
    if (view === 'deep') {
      const d = await api('/api/wellbeing/deep-analysis');
      const ts = d.target_stats||{}, ins = d.auto_insights||[], sg = d.stress_by_gender_pct||{};
      const ws = d.wlb_by_stress_level||{}, wh = d.wlb_by_hobby_time||{};
      const wsl = d.wlb_by_sleep_hours||{}, wm = d.wlb_by_meditation||{}, wi = d.wlb_by_income||{};
      const gc = d.gender_comparison||{}, wc = d.wlb_correlation_with_features||{}, wd = d.wlb_distribution_histogram||{};
      const genders = Object.keys(sg), stressLevels = [...new Set(genders.flatMap(g=>Object.keys(sg[g]||{})))].sort();
      set('wbContent', `
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Records</div><div class="stat-value blue">${(d.dataset_info?.rows||0).toLocaleString()}</div></div>
          <div class="stat"><div class="stat-label">Avg WLB Score</div><div class="stat-value green">${ts.mean}</div><div class="stat-sub">${ts.min}–${ts.max}</div></div>
          <div class="stat"><div class="stat-label">Female Avg Stress</div><div class="stat-value red">${gc.DAILY_STRESS?.Female||'—'}</div><div class="stat-sub">vs ${gc.DAILY_STRESS?.Male||'—'} male</div></div>
          <div class="stat"><div class="stat-label">Top WLB Driver</div><div class="stat-value purple">Achievement</div><div class="stat-sub">r = ${wc.ACHIEVEMENT||'—'}</div></div>
        </div>
        <div class="card"><div class="card-title">Auto Insights</div>${ins.map(i=>`<div class="alert alert-green" style="margin-bottom:6px"><span>◇</span><div class="body">${i}</div></div>`).join('')}</div>
        <div class="grid-2">
          <div class="card"><div class="card-title">WLB Score by Stress Level</div><div class="chart-box" style="height:200px"><canvas id="wbStressLine"></canvas></div></div>
          <div class="card"><div class="card-title">Stress Distribution</div><div class="chart-box" style="height:200px"><canvas id="wbStressDist"></canvas></div></div>
        </div>
        <div class="card">
          <div class="card-title">Stress Distribution by Gender (%)</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Stress Level</th>${genders.map(g=>`<th>${g}</th>`).join('')}</tr></thead>
            <tbody>${stressLevels.map(lvl=>`<tr><td class="val">Level ${lvl}</td>${genders.map(g=>`<td class="val">${sg[g]&&sg[g][lvl]?sg[g][lvl]+'%':'—'}</td>`).join('')}</tr>`).join('')}</tbody>
          </table></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">WLB by Hobby Time</div><div class="chart-box" style="height:180px"><canvas id="wbHobby"></canvas></div></div>
          <div class="card"><div class="card-title">WLB by Sleep Hours</div><div class="chart-box" style="height:180px"><canvas id="wbSleep"></canvas></div></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">WLB by Weekly Meditation</div><div class="chart-box" style="height:180px"><canvas id="wbMed"></canvas></div></div>
          <div class="card"><div class="card-title">WLB by Income Sufficiency</div><div class="chart-box" style="height:180px"><canvas id="wbInc"></canvas></div></div>
        </div>
        <div class="card"><div class="card-title">WLB Score Distribution</div><div class="chart-box" style="height:180px"><canvas id="wbDist"></canvas></div></div>
        <div class="card"><div class="card-title">Feature Correlation with WLB Score</div>
          <div class="alert alert-blue" style="margin-bottom:14px"><span>◎</span><div class="body">Green = positive WLB impact. Red = negative. Sorted by strength.</div></div>
          ${Object.entries(wc).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).map(([k,v])=>`<div class="bar-row"><div class="bar-label">${k}</div><div class="bar-track"><div class="bar-fill ${v>0?'green':'red'}" style="width:${Math.abs(v)*100}%"></div></div><div class="bar-val" style="color:${v>0?'var(--green)':'var(--red)'}">${v}</div></div>`).join('')}
        </div>`);
      setTimeout(()=>{
        const wsL=Object.keys(ws).map(k=>`Level ${k}`),wsV=Object.values(ws);
        mkChart('wbStressLine','line',wsL,[{data:wsV,borderColor:'var(--red)',fill:true,backgroundColor:'rgba(248,113,113,.07)',tension:.3,pointRadius:5,pointBackgroundColor:'var(--red)'}],{plugins:{legend:{display:false}},scales:{y:{min:Math.min(...wsV)-10,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
        const sd=d.stress_distribution||{};mkChart('wbStressDist','bar',Object.keys(sd).map(k=>`L${k}`),[{data:Object.values(sd),backgroundColor:Object.values(sd).map((_,i)=>['rgba(0,229,160,.7)','rgba(0,229,160,.65)','rgba(245,158,11,.55)','rgba(248,113,113,.6)','rgba(248,113,113,.7)','rgba(248,113,113,.8)'][Math.min(i,5)]),borderRadius:4}]);
        const mkBar=(id,obj,col)=>{const av=Object.values(obj);mkChart(id,'bar',Object.keys(obj),[{data:av,backgroundColor:col,borderRadius:4}],{scales:{y:{min:Math.min(...av)-20,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});};
        mkBar('wbHobby',wh,'rgba(0,229,160,.6)');mkBar('wbSleep',wsl,'rgba(56,189,248,.6)');mkBar('wbMed',wm,'rgba(167,139,250,.6)');
        mkBar('wbInc',wi,Object.keys(wi).map((_,i)=>['rgba(248,113,113,.65)','rgba(0,229,160,.65)'][i]||'rgba(56,189,248,.65)'));
        mkChart('wbDist','bar',Object.keys(wd),[{data:Object.values(wd),backgroundColor:'rgba(56,189,248,.5)',borderRadius:2}],{scales:{x:{ticks:{color:'#6b7280',maxRotation:45,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },60);

    } else if (view === 'corr') {
      const d = await api('/api/wellbeing/correlation');
      const pos = d.top_positive_correlates_with_WLB||{}, neg = d.top_negative_correlates_with_WLB||{};
      const all = [...Object.entries(pos).map(([k,v])=>({k,v,dir:'pos'})),...Object.entries(neg).map(([k,v])=>({k,v,dir:'neg'}))].sort((a,b)=>Math.abs(b.v)-Math.abs(a.v));
      set('wbContent', `<div class="card"><div class="card-title">Correlation with WORK_LIFE_BALANCE_SCORE</div>
        <div class="alert alert-blue" style="margin-bottom:14px"><span>◎</span><div class="body">Green improves WLB. Red reduces it.</div></div>
        ${all.map(c=>`<div class="bar-row"><div class="bar-label">${c.k}</div><div class="bar-track"><div class="bar-fill ${c.dir==='pos'?'green':'red'}" style="width:${Math.abs(c.v)*100}%"></div></div><div class="bar-val" style="color:${c.dir==='pos'?'var(--green)':'var(--red)'}">${c.v}</div></div>`).join('')}
      </div>`);

    } else if (view === 'train') {
      const d = await api('/api/wellbeing/train');
      const m = d.metrics, coefs = Object.entries(d.coefficients||{}).slice(0,8), hyp = d.hypothetical_prediction||{};
      const samp = (d.actual_vs_predicted_sample||[]).slice(0,8);
      set('wbContent', `
        <div class="alert alert-green"><span>◇</span><div class="body">${m.r2_interpretation}</div></div>
        <div class="grid-4">
          <div class="stat"><div class="stat-label">R² Score</div><div class="stat-value green">${m.r2_score}</div></div>
          <div class="stat"><div class="stat-label">MAE</div><div class="stat-value blue">${m.mae}</div></div>
          <div class="stat"><div class="stat-label">RMSE</div><div class="stat-value amber">${m.rmse}</div></div>
          <div class="stat"><div class="stat-label">Train / Test</div><div class="stat-value purple" style="font-size:18px">${m.train_size} / ${m.test_size}</div></div>
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Model Coefficients</div>${coefs.map(([n,v])=>`<div class="bar-row"><div class="bar-label">${n}</div><div class="bar-track"><div class="bar-fill ${v>0?'green':'red'}" style="width:${Math.abs(v)/Math.abs(coefs[0][1])*100}%"></div></div><div class="bar-val" style="color:${v>0?'var(--green)':'var(--red)'}">${v}</div></div>`).join('')}</div>
          <div class="card"><div class="card-title">Actual vs Predicted</div>
            <div class="tbl-wrap"><table><thead><tr><th>#</th><th>Actual</th><th>Predicted</th><th>Error</th></tr></thead>
            <tbody>${samp.map((r,i)=>`<tr><td>${i+1}</td><td class="val">${r.actual}</td><td class="hi">${r.predicted}</td><td class="${Math.abs(r.error)<20?'val':'warn'}">${r.error}</td></tr>`).join('')}</tbody></table></div>
          </div>
        </div>
        <div class="card"><div class="card-title">Hypothetical Prediction</div>
          <div class="alert alert-green"><span>◇</span><div class="body">${hyp.note}<br><strong>Predicted WLB Score: ${hyp.predicted_wlb_score}</strong></div></div>
        </div>
        <div class="card"><div class="card-title">Recommendations</div>${(d.recommendations||[]).map(r=>`<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;color:var(--muted)">→ ${r}</div>`).join('')}</div>`);
    }
  } catch(e) { oops('wbContent', e); }
}
