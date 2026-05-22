async function empInit() {
  try {
    const d = await api('/api/recommender/employees');
    const ids = d.employee_ids||[];
    $('empId').innerHTML = ids.map(id=>`<option value="${id}">${id}</option>`).join('');
    $('empId').value = ids.find(i=>i==='emp_050')||ids[ids.length-1];
    await empRec('onboarding_buddy');
  } catch(e) { oops('empContent', e); }
}

async function empRec(mode) {
  spin('empContent');
  try {
    const empId = $('empId').value, topN = $('topN').value;
    const d = await api(`/api/recommender/?employee_id=${empId}&mode=${mode}&top_n=${topN}`);
    const recs = d.recommendations||[], target = d.target_employee||{};
    const modeInfo = { onboarding_buddy:{icon:'🤝',color:'var(--green)',label:'Onboarding Buddy'}, mentor:{icon:'⭐',color:'var(--amber)',label:'Mentor'}, teammate:{icon:'👥',color:'var(--blue)',label:'Teammate'} };
    const mi = modeInfo[mode]||modeInfo.onboarding_buddy;
    const profileTags = Object.values(target.profile||{}).flatMap(v=>v.split(',').map(t=>`<span class="tag">${t.trim()}</span>`)).join('');
    set('empContent', `
      <div class="alert alert-green"><span>${mi.icon}</span><div class="body">${d.mode_explanation}</div></div>
      <div class="card card-sm"><div class="card-title">Target — ${target.id}</div><div class="tags">${profileTags}</div></div>
      <div class="section-label">${mi.icon} Top ${recs.length} ${mi.label} Matches</div>
      ${recs.map((r,i)=>{
        const pct = Math.min(Math.round(r.score),100);
        const shared = Object.values(r.shared_attributes||{}).flat();
        const profTags = Object.values(r.profile||{}).flatMap(v=>v.split(',').map(t=>`<span class="tag">${t.trim()}</span>`)).join('');
        const sharedTags = shared.map(t=>`<span class="tag hi">${t}</span>`).join('');
        return `<div class="rec-card">
          <div class="rec-rank">${i+1}</div>
          <div class="rec-body">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <div class="rec-id">${r.employee_id}</div>
              ${r.same_team?badge('Same team','green'):''}
              ${badge(r.experience_level.replace('.',''),'dim')}
              ${badge(`${pct}% match`,'blue')}
            </div>
            <div class="rec-meta" style="margin-top:4px">Score: ${r.score} · Cosine: ${r.cosine_similarity}</div>
            <div class="rec-sim"><div class="rec-sim-fill" style="width:${pct}%;background:${mi.color}"></div></div>
            <div class="tags">${profTags}</div>
            ${sharedTags?`<div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px">Shared with ${target.id}:</div><div class="tags">${sharedTags}</div>`:''}
          </div>
        </div>`;
      }).join('')}
      <div class="card"><div class="card-title">Score Comparison</div><div class="chart-box" style="height:${recs.length*50+60}px"><canvas id="empBarChart"></canvas></div></div>`);
    setTimeout(()=>{
      const col = mi.color.includes('green')?'rgba(0,229,160,.7)':mi.color.includes('amber')?'rgba(245,158,11,.7)':'rgba(56,189,248,.7)';
      mkChart('empBarChart','bar',recs.map(r=>r.employee_id),[{data:recs.map(r=>r.score),backgroundColor:col,borderRadius:4}],{indexAxis:'y',scales:{x:{min:0,max:100,ticks:{callback:v=>v+'%',color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
    },50);
  } catch(e) { oops('empContent', e); }
}

async function empRecTeams() {
  spin('empContent');
  try {
    const d = await api('/api/recommender/team-clusters');
    const teams = d.teams||{}, best = d.recommended_team_for_new_hire||'';
    set('empContent', `
      <div class="alert alert-green"><span>◈</span><div class="body">${d.rationale} Recommended: <strong>${best}</strong></div></div>
      <div class="card"><div class="card-title">Team Cohesion</div><div class="chart-box" style="height:200px"><canvas id="teamCohChart"></canvas></div></div>
      ${Object.entries(teams).map(([team,info])=>`
        <div class="card ${team===best?'':''}` + (team===best?'" style="border-color:rgba(0,229,160,.35)':'"') + `>
          <div class="card-title-row">
            <div class="card-title" style="margin:0">${team.toUpperCase()} ${team===best?'⭐':''}</div>
            <div style="display:flex;gap:8px">
              ${badge(`${Math.round(info.intra_team_avg_similarity*100)}% cohesion`, info.intra_team_avg_similarity>0.3?'green':'amber')}
              ${badge(`${info.count} members`,'dim')}
            </div>
          </div>
          <div style="display:flex;gap:24px;margin-bottom:12px">
            <div><div style="font-size:10px;color:var(--muted)">BRIDGE EMPLOYEE</div><div style="font-family:var(--mono);font-size:13px;color:var(--purple);margin-top:2px">${info.bridge_employee}</div></div>
            <div><div style="font-size:10px;color:var(--muted)">EXPERIENCE MIX</div><div class="tags" style="margin-top:4px">${Object.entries(info.experience_mix).map(([k,v])=>`<span class="tag">${k.replace('.','')}: ${v}</span>`).join('')}</div></div>
          </div>
          <div class="tags">${info.members.map(m=>`<span class="tag">${m}</span>`).join('')}</div>
        </div>`).join('')}`);
    setTimeout(()=>{
      const cohData = Object.entries(teams).map(([t,i])=>({t,v:Math.round(i.intra_team_avg_similarity*100)}));
      mkChart('teamCohChart','bar',cohData.map(d=>d.t),[{data:cohData.map(d=>d.v),backgroundColor:cohData.map(d=>d.t===best?'rgba(0,229,160,.75)':'rgba(56,189,248,.55)'),borderRadius:4}],{scales:{y:{min:0,max:100,ticks:{callback:v=>v+'%',color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}},x:{ticks:{color:'#6b7280',font:{family:"'IBM Plex Mono'"}},grid:{color:'rgba(255,255,255,0.04)'}}}});
    },50);
  } catch(e) { oops('empContent', e); }
}

async function empRecMatrix() {
  spin('empContent');
  try {
    const d = await api('/api/recommender/similarity-matrix');
    const ids = d.employee_ids||[], sim = d.similarity_matrix||[];
    const N = ids.length, slice = 20;
    const subIds = ids.slice(0,slice), subSim = sim.slice(0,slice).map(r=>r.slice(0,slice));
    const cellPx = Math.floor(Math.min(540, window.innerWidth-300) / slice);
    const flatOff = sim.flatMap((r,i)=>r.filter((_,j)=>j!==i));
    const avgS = (flatOff.reduce((a,b)=>a+b,0)/flatOff.length*100).toFixed(1);
    const maxS = (Math.max(...flatOff)*100).toFixed(1);
    const rows = subSim.map((row,i)=>
      `<div style="display:flex;align-items:center">
        <div style="width:58px;font-size:9px;color:var(--muted);text-align:right;padding-right:6px;overflow:hidden;white-space:nowrap;font-family:var(--mono)">${subIds[i]}</div>
        ${row.map((v,j)=>{
          const a=Math.round(v*100);
          const bg=v>0.6?`rgba(0,229,160,${v})`:(v>0.3?`rgba(56,189,248,${v})`:`rgba(61,66,81,${v+0.2})`);
          return `<div title="${subIds[i]} ↔ ${subIds[j]}: ${v}" style="width:${cellPx}px;height:${cellPx}px;background:${bg};display:inline-flex;align-items:center;justify-content:center;font-size:${Math.max(6,cellPx-5)}px;color:rgba(255,255,255,0.6)">${a>15&&cellPx>14?a:''}</div>`;
        }).join('')}
      </div>`
    ).join('');
    set('empContent', `
      <div class="grid-3">
        <div class="stat"><div class="stat-label">Employees</div><div class="stat-value blue">${N}</div></div>
        <div class="stat"><div class="stat-label">Avg Similarity</div><div class="stat-value green">${avgS}%</div></div>
        <div class="stat"><div class="stat-label">Max Similarity</div><div class="stat-value purple">${maxS}%</div></div>
      </div>
      <div class="card">
        <div class="card-title-row">
          <div class="card-title" style="margin:0">Cosine Similarity Matrix (first ${slice} × ${slice})</div>
          <div style="display:flex;gap:10px;font-size:11px">
            <span style="color:var(--green)">■ High</span>
            <span style="color:var(--blue)">■ Medium</span>
            <span style="color:var(--dim)">■ Low</span>
          </div>
        </div>
        <div style="overflow-x:auto;margin-top:4px">${rows}</div>
        <div style="font-size:10px;color:var(--dim);margin-top:10px;font-family:var(--mono)">Showing ${slice}×${slice} of ${N}×${N}</div>
      </div>`);
  } catch(e) { oops('empContent', e); }
}
