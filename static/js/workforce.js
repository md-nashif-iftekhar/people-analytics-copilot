async function wfLoad(view) {
  window._wfView = view;
  spin('wfContent');
  const sl = $('wfSL').value || 4;
  const bud = $('wfBudget').value || 300;
  try {
    if (view === 'full') {
      const d = await api(`/api/workforce/?service_level=${sl}`);
      const shifts = d.shift_summary || [], rows = d.per_time_window || [], costs = d.cost_summary || {};
      const peakN = Math.max(...shifts.map(s => s.recommended_staff));
      set('wfContent', `
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Daily Cost (Peak)</div><div class="stat-value red">€${costs.total_daily_cost_peak_staffing_eur}</div></div>
          <div class="stat"><div class="stat-label">Optimized Cost</div><div class="stat-value green">€${costs.total_daily_cost_optimized_eur}</div></div>
          <div class="stat"><div class="stat-label">Daily Savings</div><div class="stat-value blue">€${costs.total_potential_savings_eur}</div></div>
          <div class="stat"><div class="stat-label">Monthly Savings</div><div class="stat-value purple">€${costs.monthly_savings_if_optimized_eur}</div></div>
        </div>
        <div class="shift-grid">${shifts.map(s => {
          const isPeak = s.recommended_staff === peakN;
          const icons = {'Morning (06–14)':'🌅','Afternoon (14–22)':'☀️','Night (22–06)':'🌙'};
          const colors = {'Morning (06–14)':'var(--amber)','Afternoon (14–22)':'var(--blue)','Night (22–06)':'var(--purple)'};
          const label = s.label||s.shift;
          const col = colors[label]||'var(--green)';
          return `<div class="shift-card ${isPeak?'peak':''}">
            <div class="shift-accent" style="background:${col}"></div>
            <div class="shift-body">
              <div class="shift-header">
                <div>
                  <div class="shift-tag">${label}</div>
                </div>
                <div class="shift-icon">${icons[label]||'⏱'}</div>
              </div>
              <div class="shift-staff">
                <div class="shift-num" style="color:${col}">${s.recommended_staff}</div>
                <div class="shift-unit">staff<br>recommended</div>
              </div>
              <div class="shift-metrics">
                <div class="shift-metric">
                  <span class="shift-metric-label">Avg pts/hr</span>
                  <span class="shift-metric-val" style="color:var(--text)">${s.avg_patients_per_hour}</span>
                </div>
                <div class="shift-metric">
                  <span class="shift-metric-label">Wage/shift</span>
                  <span class="shift-metric-val" style="color:var(--green)">€${s.wage_per_shift_eur}</span>
                </div>
                ${isPeak?`<div class="shift-metric"><span class="shift-metric-label" style="color:var(--green)">Peak shift</span><span style="color:var(--green);font-size:10px">★</span></div>`:''}
              </div>
            </div>
          </div>`;
        }).join('')}
        </div>
        <div class="grid-2">
          <div class="card"><div class="card-title">Demand Curve</div><div class="chart-box" style="height:200px"><canvas id="wfDemChart"></canvas></div></div>
          <div class="card"><div class="card-title">Demand vs Capacity</div><div class="chart-box" style="height:200px"><canvas id="wfCapChart"></canvas></div></div>
        </div>
        <div class="card"><div class="card-title">Per Time Window</div>
          <div class="tbl-wrap"><table>
            <thead><tr><th>Time</th><th>Shift</th><th>Avg Pts/hr</th><th>Staff</th><th>Utilization</th><th>Status</th></tr></thead>
            <tbody>${rows.map(r=>`<tr>
              <td class="val" style="font-size:11px">${r.time_window}</td>
              <td>${r.shift||'—'}</td>
              <td class="val">${r.avg_patients}</td>
              <td class="hi">${r.required_staff}</td>
              <td><div style="display:flex;align-items:center;gap:8px">
                <div style="flex:1;height:5px;background:var(--raised);border-radius:3px;overflow:hidden;min-width:60px">
                  <div style="height:100%;width:${r.utilization_pct}%;background:${r.utilization_pct>85?'var(--amber)':'var(--green)'};border-radius:3px"></div>
                </div>
                <span style="font-family:var(--mono);font-size:10px;color:var(--muted)">${r.utilization_pct}%</span>
              </div></td>
              <td>${r.zero_demand?'<span class="badge badge-dim">No demand</span>':r.understaffed?'<span class="badge badge-red">Alert</span>':'<span class="badge badge-green">OK</span>'}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>`);
      setTimeout(() => {
        const L = rows.map(r=>r.time_window.split(/[-–]/)[0].trim());
        const P = rows.map(r=>r.avg_patients), S = rows.map(r=>r.required_staff*parseInt(sl));
        mkChart('wfDemChart','line',L,[{data:P,borderColor:'#00e5a0',backgroundColor:'rgba(0,229,160,.07)',fill:true,tension:.4,pointRadius:3,pointBackgroundColor:'#00e5a0'}],{plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#6b7280',maxRotation:45,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{beginAtZero:true,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
        mkChart('wfCapChart','bar',L,[
          {label:'Demand',data:P,backgroundColor:'rgba(56,189,248,.55)',borderRadius:3},
          {label:'Capacity',data:S,backgroundColor:'rgba(0,229,160,.35)',borderRadius:3}
        ],{plugins:{legend:{display:true,position:'top',labels:{color:'#9ca3af',boxWidth:10,font:{family:"'IBM Plex Mono'",size:10}}}},scales:{x:{ticks:{color:'#6b7280',maxRotation:45,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
      },60);

    } else if (view === 'heatmap') {
      const d = await api(`/api/workforce/heatmap?service_level=${sl}`);
      const curve = d.demand_curve || [];
      const maxP = Math.max(...curve.map(r=>r.patients), 1);
      const colorFor = (pts, shift) => {
        const i = pts/maxP;
        if (shift==='Shift 1') return `rgba(0,229,160,${0.15+i*0.7})`;
        if (shift==='Shift 2') return `rgba(56,189,248,${0.15+i*0.7})`;
        return `rgba(167,139,250,${0.15+i*0.7})`;
      };
      set('wfContent', `
        <div class="card">
          <div class="card-title-row">
            <div class="card-title">Patient Demand Heatmap — Hour by Hour</div>
            <div style="display:flex;gap:12px;font-size:11px">
              <span style="color:var(--green)">■ Shift 1</span>
              <span style="color:var(--blue)">■ Shift 2</span>
              <span style="color:var(--purple)">■ Shift 3</span>
            </div>
          </div>
          ${curve.map(r=>`<div class="hm-row">
            <div class="hm-label">${r.time.split(/[-–]/)[0].trim()}</div>
            <div class="hm-bar"><div class="hm-fill" style="width:${r.patients/maxP*100}%;background:${colorFor(r.patients,r.shift)}"></div></div>
            <div class="hm-val">${r.patients} pts · ${r.staff} staff</div>
          </div>`).join('')}
        </div>
        <div class="card"><div class="card-title">Demand Curve</div><div class="chart-box" style="height:200px"><canvas id="wfHmLine"></canvas></div></div>
      `);
      setTimeout(()=>{const L=curve.map(r=>r.time.split(/[-–]/)[0].trim());const P=curve.map(r=>r.patients);mkChart('wfHmLine','line',L,[{data:P,borderColor:'#00e5a0',fill:true,backgroundColor:'rgba(0,229,160,.07)',tension:.4,pointRadius:3,pointBackgroundColor:'#00e5a0'}],{plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#6b7280',maxRotation:45,font:{size:9,family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{beginAtZero:true,ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});},50);

    } else if (view === 'alerts') {
      const d = await api(`/api/workforce/alerts?service_level=${sl}`);
      const under = d.understaffing_alerts||[], over = d.overstaffing_alerts||[], zero = d.zero_demand_windows||[];
      const mkList = (list, type, empty) => !list.length
        ? `<div class="alert alert-green"><span>✓</span><div class="body">${empty}</div></div>`
        : list.map(a=>`<div class="alert alert-${a.severity==='HIGH'?'red':'amber'}">
            <span>${a.severity==='HIGH'?'🔴':'🟡'}</span>
            <div class="body"><strong>${a.time} · ${a.shift||''}</strong><br>${a.action||a.message||''}${a.wasted_cost_eur?`<br>Wasted: €${a.wasted_cost_eur}/hr`:''}
            </div></div>`).join('');
      set('wfContent', `
        <div class="grid-4">
          <div class="stat"><div class="stat-label">Total Alerts</div><div class="stat-value ${d.total_alerts>0?'amber':'green'}">${d.total_alerts}</div></div>
          <div class="stat"><div class="stat-label">Understaffing</div><div class="stat-value red">${under.length}</div></div>
          <div class="stat"><div class="stat-label">Overstaffing</div><div class="stat-value amber">${over.length}</div></div>
          <div class="stat"><div class="stat-label">Zero Demand</div><div class="stat-value blue">${zero.length}</div></div>
        </div>
        <div class="card"><div class="card-title">⚠ Understaffing Alerts</div>${mkList(under,'under','No understaffing detected — coverage is adequate.')}</div>
        <div class="card"><div class="card-title">💸 Overstaffing Alerts</div>${mkList(over,'over','No overstaffing detected.')}</div>
        ${zero.length?`<div class="card"><div class="card-title">○ Zero Demand Windows</div>${zero.map(z=>`<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;color:var(--muted)">${z.time} · ${z.shift}</div>`).join('')}</div>`:''}`);

    } else if (view === 'optimize') {
      const d = await api(`/api/workforce/optimize?service_level=${sl}&budget_eur=${bud}`);
      const scen = d.scenarios || {};
      set('wfContent', `
        <div class="alert alert-blue"><span>⚡</span><div class="body">Three staffing scenarios per shift — minimum cost, full recommended coverage, and budget-constrained (€${bud}/day).</div></div>
        ${Object.entries(scen).map(([shift, s])=>`
          <div class="card">
            <div class="card-title">${s.label}</div>
            <div class="grid-3">
              <div style="text-align:center;padding:14px;background:var(--raised);border-radius:var(--r2)">
                <div style="font-family:var(--mono);font-size:32px;font-weight:600;color:var(--muted)">${s.minimum_coverage}</div>
                <div style="font-size:11px;color:var(--muted);margin-top:4px">Min coverage<br>€${s.minimum_cost_eur}/shift</div>
              </div>
              <div style="text-align:center;padding:14px;background:rgba(0,229,160,.07);border:1px solid rgba(0,229,160,.2);border-radius:var(--r2)">
                <div style="font-family:var(--mono);font-size:32px;font-weight:600;color:var(--green)">${s.recommended}</div>
                <div style="font-size:11px;color:var(--muted);margin-top:4px">Recommended<br>€${s.full_coverage_cost_eur}/shift</div>
              </div>
              <div style="text-align:center;padding:14px;background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.2);border-radius:var(--r2)">
                <div style="font-family:var(--mono);font-size:32px;font-weight:600;color:var(--amber)">${s.budget_constrained_staff}</div>
                <div style="font-size:11px;color:var(--muted);margin-top:4px">Budget (€${bud})<br>€${s.budget_cost_eur}/shift</div>
              </div>
            </div>
            <div style="margin-top:12px;font-size:12px;color:var(--muted)">${s.recommendation_reason}</div>
          </div>`).join('')}`);
    }
  } catch(e) { oops('wfContent', e); }
}
