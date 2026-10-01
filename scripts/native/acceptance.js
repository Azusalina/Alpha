// Test-only instrumentation copied into a temporary frontend, never src/.
(async () => {
  const report = async (value) => fetch(ALPHA_NATIVE_URL + '/report', {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(value)
  });
  const wait = async (fn, label, timeout = 60000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) { if (await fn()) return; await new Promise(r => setTimeout(r, 100)); }
    throw Error('timeout: ' + label);
  };
  const q = (id, parent = document) => parent.querySelector(`[data-testid="${id}"]`);
  const click = async (id, parent = document) => {
    await wait(() => q(id,parent) && !q(id,parent).disabled, id);
    q(id,parent).click();
  };
  const fill = (element, text) => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(element,text);
    element.dispatchEvent(new Event('input',{bubbles:true}));
  };
  let seq = 0;
  const api = async (method, params = {}) => {
    const response = await window.__TAURI_INTERNALS__.invoke('brain_call', {
      request: {schema_version:1,id:'native-'+ ++seq,method,params}
    });
    if (!response.ok) throw Error(method + ': ' + JSON.stringify(response.error));
    return response.result;
  };
  const assert = (value, label) => { if (!value) throw Error(label); };
  const checks = [];
  try {
    await wait(() => window.__alpha?.state === 'home', 'native startup');
    window.__alpha.navigate('human');
    await wait(() => window.__alpha.state === 'human', 'human');
    if (ALPHA_NATIVE_CASE.startsWith('fault-')) {
      await wait(() => q('backend-retry'), 'failed health exposes retry');
      await click('backend-retry');
      await wait(() => window.__alpha.backend.mode() === 'remote', 'explicit reconnect');
      checks.push('startup failure and explicit UI reconnect');
      fill(q('human-input'), '合成故障。我重视自由。');
      await click('entry-immediate');
      await click('entry-submit');
      await wait(() => q('entry-error'), 'ambiguous write error', 45000);
      assert(q('entry-error').textContent.includes('MODEL_UNAVAILABLE'), 'transport error visible');
      await new Promise(r => setTimeout(r,1500));
      const list = await api('input_list');
      assert(list.length === 1, 'committed ambiguous submit read back exactly once');
      checks.push('ambiguous write visible; explicit read reconciles committed source');
    } else {
      await wait(() => window.__alpha.backend.mode() === 'remote', 'real native backend');
      assert(window.__TAURI_INTERNALS__, 'real Tauri IPC');
      await click('brain-open');
      await wait(() => q('records-panel'), 'records panel');
      if (ALPHA_NATIVE_CASE === 'persistence') {
        await wait(() => window.__alpha.inputs.list().length === 50, 'persisted page');
        const list = await api('input_list', {limit:100});
        const saved = list.find(x => x.excerpt.includes('合成保留'));
        assert(saved && saved.status === 'agreed', 'persisted agreed source');
        assert((await api('input_get',{source_id:saved.source_id})).text === '合成保留。我重视成长。', 'persisted original text');
        assert((await api('state',{partition:'rational'}))['value.growth'].observed, 'persisted actual state');
        checks.push('native process restart: text, consent, actual model state');
      } else {
        const rows = () => document.querySelectorAll('[data-testid="record-row"]');
        await wait(() => rows().length === 50, 'first 50');
        await click('records-more'); await wait(() => rows().length === 100,'next 100');
        await click('records-more'); await wait(() => rows().length === 137,'last 137');
        assert(!q('records-more'), 'paging terminates');
        assert(new Set([...rows()].map(r => r.dataset.id)).size === 137,'paging unique');
        checks.push('native UI paging 50 → 100 → 137');
        const id = rows()[0].dataset.id;
        const row = () => [...rows()].find(r => r.dataset.id === id);
        await click('record-head',row());
        await click('act-confirm-false',row());
        await wait(() => row()?.dataset.status === 'disagreed','reject');
        await click('act-edit',row());
        await wait(() => q('editor-text',row()),'editor');
        fill(q('editor-text',row()),'取消的合成修改');
        await click('editor-cancel',row());
        assert(!(await api('input_get',{source_id:id})).text.includes('取消'), 'edit cancel no mutation');
        await click('act-delete',row()); await click('act-delete-cancel',row());
        assert((await api('input_get',{source_id:id})).source_id === id,'delete cancel no mutation');
        checks.push('F6 edit/delete cancellation');
        await click('act-edit',row());
        await wait(() => q('editor-text',row()),'editor again');
        fill(q('editor-text',row()),'合成修改。我重视成长。');
        if (!q('editor-immediate',row()).checked) await click('editor-immediate',row());
        await click('editor-save',row());
        await wait(() => row()?.dataset.status === 'pending','edited pending');
        assert(row().dataset.confirm === 'null','edit clears consent');
        assert((await api('input_get',{source_id:id})).text === '合成修改。我重视成长。','edit actual text');
        await click('act-confirm-true',row());
        await wait(() => row()?.dataset.status === 'agreed','review edited');
        assert((await api('state',{partition:'rational'}))['value.growth'].observed,'actual fit');
        await click('tab-state');
        await wait(() => document.querySelector('[data-testid="state-param"][data-parameter="value.growth"][data-partition="rational"]')?.dataset.observed === 'true','UI actual state');
        await click('tab-records');
        await click('act-revoke',row());
        await wait(() => row()?.dataset.status === 'revoked','revoke');
        assert(!(await api('state',{partition:'rational'}))['value.growth'].observed,'actual revoked state');
        await click('act-reagree',row());
        await wait(() => row()?.dataset.status === 'agreed','reagree');
        await click('act-delete',row()); await click('act-delete-confirm',row());
        await wait(() => !row(),'agreed delete');
        assert(!(await api('state',{partition:'rational'}))['value.growth'].observed,'delete withdraws actual state');
        const missing = await window.__TAURI_INTERNALS__.invoke('brain_call',{request:{schema_version:1,id:'missing',method:'input_get',params:{source_id:id}}});
        assert(missing.error?.code === 'NOT_FOUND','deleted source absent');
        checks.push('F6 edit clears consent; fit/revoke/reagree/delete actual state');
        // Persist one source for the second native process. Explicit fixture setup,
        // through real Rust IPC, not an assertion about the entry form.
        await api('submit',{partition:'rational',kind:'philosophy',text:'合成保留。我重视成长。',immediate:true,exclamation:true});
      }
    }
    await report({passed:true,case:ALPHA_NATIVE_CASE,checks,userAgent:navigator.userAgent,renderer:'Xvfb software; no physical GPU acceptance'});
  } catch (error) {
    await report({passed:false,case:ALPHA_NATIVE_CASE,checks,error:String(error),body:document.body.innerText.slice(-4000)});
  }
})();
