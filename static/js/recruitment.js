async function recLoad() {
  spin('recContent');
  try {
    const target = $('recTarget').value, supp = $('recSupp').value, conf = $('recConf').value;
    const rules = await api(`/api/recruitment/?min_support=${supp}&min_confidence=${conf}&target_col=${target}&top_n=10`);
    const topRules = (rules.top_rules||[]).slice(0,8);
    const exp = rules.first_rule_explanation||{};
    set('recContent', `
      <div class="grid-2">
        <div class="stat"><div class="stat-label">Total Applicants</div><div class="stat-value blue">${(rules.dataset_info?.rows||0).toLocaleString()}</div></div>
        <div class="stat"><div class="stat-label">Rules Found</div><div class="stat-value green">${rules.total_rules_found}</div></div>
      </div>
      <div class="card">
        <div class="card-title">Top Association Rules → ${target.replace(/_/g,' ')}</div>
        ${topRules.map(r=>`
          <div style="padding:12px 0;border-bottom:1px solid var(--border)">
            <div style="font-size:12px;margin-bottom:6px">
              <span style="color:var(--blue)">${r.antecedents.join(' + ')}</span>
              <span style="color:var(--dim);margin:0 8px">→</span>
              <span style="color:var(--green)">${r.consequents.join(' + ')}</span>
            </div>
            <div style="display:flex;gap:14px">
              <span style="font-size:11px;color:var(--muted)">Support <strong style="color:var(--text);font-family:var(--mono)">${r.support}</strong></span>
              <span style="font-size:11px;color:var(--muted)">Confidence <strong style="color:var(--text);font-family:var(--mono)">${r.confidence}</strong></span>
              <span style="font-size:11px;color:var(--muted)">Lift <strong style="color:var(--green);font-family:var(--mono)">${r.lift}</strong></span>
            </div>
          </div>`).join('')||'<div style="color:var(--muted);font-size:12px">No rules found. Try lowering min support.</div>'}
      </div>
      ${exp.rule?`<div class="card">
        <div class="card-title">First Rule Explained</div>
        ${['support_meaning','confidence_meaning','lift_meaning'].filter(k=>exp[k]).map(k=>`
          <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">
            <span style="color:var(--green);font-family:var(--mono);min-width:90px">${k.split('_')[0]}</span>
            <span style="color:var(--muted)">${exp[k]}</span>
          </div>`).join('')}
      </div>`:''}
    `);
  } catch(e) { oops('recContent', e); }
}

async function recLoadBias() {
  spin('recContent');
  try {
    const target = $('recTarget').value;
    const [sum, bias] = await Promise.all([api('/api/recruitment/summary'), api(`/api/recruitment/bias?target_col=${target}`)]);
    const gb = bias.bias_by_group||{};
    set('recContent', `
      <div class="grid-4">
        <div class="stat"><div class="stat-label">Overall Hire Rate</div><div class="stat-value blue">${bias.overall_hire_rate_pct}%</div></div>
        ${sum.hire_rate_pct!==undefined?`<div class="stat"><div class="stat-label">General Hire Rate</div><div class="stat-value green">${sum.hire_rate_pct}%</div></div>`:''}
        ${sum.hire_rate_by_gender?Object.entries(sum.hire_rate_by_gender).map(([g,v])=>`<div class="stat"><div class="stat-label">Hired (${g})</div><div class="stat-value ${v<20?'red':'amber'}">${v}%</div></div>`).join(''):''}
      </div>
      ${Object.entries(gb).map(([grp,vals])=>{
        const entries=Object.entries(vals).filter(([k])=>!k.startsWith('_'));
        return `<div class="card">
          <div class="card-title">${grp} · ${vals._flag||''}</div>
          ${entries.map(([k,v])=>`<div class="bar-row">
            <div class="bar-label">${k}</div>
            <div class="bar-track"><div class="bar-fill ${v>20?'red':'green'}" style="width:${Math.min(v,100)}%"></div></div>
            <div class="bar-val">${v}%</div>
          </div>`).join('')}
        </div>`;
      }).join('')}`);
  } catch(e) { oops('recContent', e); }
}
