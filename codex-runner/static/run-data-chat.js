/* Data discussion has no route to robot task submission or visitor chat. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), panel = $('runDataChat');
  if (!panel) return;
  let config = {}, history = [], revision = 0, scopeKey = '', busy = false;
  const form = $('runDataChatForm'), input = $('runDataChatQuestion'), status = $('runDataChatStatus');
  function scope() { return window.yamReplayHistory?.dataScope?.($('runDataChatScope').value) || null; }
  function describe(s) {
    if (!s) return 'Waiting for the run library…';
    return `${s.kind === 'all' ? 'All public runs · Library context: ' : ''}${s.robot_name || s.robot_id} · ${s.kind === 'box' ? `${s.episode_ids.length} runs in selected box` : s.kind === 'run' ? 'Opened replay' : s.library_context?.episode_ids ? `${s.library_context.episode_ids.length} runs in selected box` : 'Current filters'} · ${s.label_source === 'auto' ? 'Auto-labeled' : 'Human-labeled'}${s.models.length ? ' · '+s.models.join(', ') : ' · All models'}${s.query ? ' · Search: '+s.query : ''}${s.opened_episode_id ? ' · Replay: '+s.opened_episode_id : ''}`;
  }
  function sync() {
    const s = scope(), key = JSON.stringify(s);
    $('runDataChatScopeText').textContent = describe(s);
    $('runDataChatScope').options[2].disabled = !window.yamReplayHistory?.dataScope?.('run');
    if (key !== scopeKey) {
      scopeKey = key;
      status.textContent = $('runDataChatMessages').children.length ? 'Library context updated. The conversation continues; earlier answers retain their original data scope.' : '';
    }
    input.disabled = !config.available || !s;
    $('runDataChatSend').disabled = busy || input.disabled;
    $('runDataChatCancel').hidden = !busy;
    $('runDataChatModel').textContent = config.available ? `${config.model} · Text metadata and saved annotations; no video supplied.` : 'Data chat is unavailable on this server. You can still browse runs and replays.';
  }
  function message(role, text, label) {
    const article = document.createElement('article'), title = document.createElement('strong'), body = document.createElement('p');
    article.className = 'runDataChatMessage'; article.dataset.role = role;
    title.textContent = role === 'user' ? 'You' : 'Data chat'; body.textContent = text;
    article.append(title, body);
    if (label) { const context = document.createElement('small'); context.textContent = label; article.append(context); }
    panel.classList.add('hasConversation');
    $('runDataChatMessages').append(article); article.scrollIntoView?.({block:'nearest'}); return article;
  }
  function open(value) {
    panel.hidden = !value; $('runDiscussionLayout').dataset.chatOpen = String(value);
    $('openRunDataChat').setAttribute('aria-expanded', String(value));
    if (value) { sync(); input.focus({preventScroll:true}); if (matchMedia('(max-width: 800px)').matches) panel.scrollIntoView({block:'nearest'}); }
    else $('openRunDataChat').focus({preventScroll:true});
  }
  async function ask(event) {
    event.preventDefault(); sync();
    const question = input.value.trim(), s = scope();
    if (!question || busy || !config.available || !s) return;
    const current = ++revision; busy = true; $('runDataChatSend').disabled = true; $('runDataChatCancel').hidden = false;
    status.textContent = 'Reading matching run metadata and asking OpenAI. This can take up to a minute; no videos are being watched.';
    const previous = history.slice(-12); message('user', question, describe(s));
    try {
      const data = await config.send({question, scope:s, history:previous});
      if (current !== revision) return;
      const c = data.scope.counts, denominator = c.denominator;
      const basis = `${data.scope.counts.total} ${data.scope.kind === 'all' ? 'runs across all public robots' : 'runs in focused scope'} · ${c.Success} Success, ${c.Failure} Failure, ${c.Uncertain} Uncertain, ${c.Unscored} unlabeled/excluded · ${denominator ? `${(c.Success/denominator*100).toFixed(1)}% of ${denominator} Success/Failure labels` : 'No Success/Failure denominator'} · ${data.scope.evidence_count} example records supplied${data.scope.stale ? ' · Saved archive snapshot (temporarily stale)' : ''}\nCurrent library context: ${data.scope.library_context?.counts.total ?? 'unknown'} runs · ${data.scope.library_context?.counts.denominator ?? 0} Success/Failure labels.`;
      const article = message('assistant', data.answer, `${describe(s)}\n${basis}`);
      if (data.citations?.length) {
        const list = document.createElement('ul'); list.className = 'runDataChatEvidence';
        for (const citation of data.citations) {
          const li = document.createElement('li'), link = document.createElement('a'), note = document.createElement('span');
          link.href = citation.url; link.textContent = `${citation.label}: ${citation.prompt}`;
          link.addEventListener('click', event => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || !window.yamReplayReview?.openEpisode || window.yamReplayHistory?.dataScope?.('filtered')?.robot_id !== citation.robot_id) return;
            event.preventDefault(); window.yamReplayReview?.openEpisode(citation.episode_id, {robot_id:citation.robot_id});
          });
          note.textContent = citation.note; li.append(link, note); list.append(li);
        }
        article.append(list);
      }
      const model = document.createElement('small');
      model.textContent = data.resolved_model ? `OpenAI · requested ${data.requested_model} · returned ${data.resolved_model} · low reasoning` : 'No model call needed for an empty scope.'; article.append(model);
      history = [...previous, {role:'user',content:question}, {role:'assistant',content:data.answer}].slice(-12);
      input.value = ''; status.textContent = 'Ask a follow-up, or open a supporting replay to inspect it.';
    } catch (error) {
      if (current === revision) status.textContent = error.message || 'The answer could not be loaded. Your question is kept; try again.';
    } finally {
      if (current === revision) {busy = false; sync(); input.focus({preventScroll:true});}
    }
  }
  window.yamRunDataChat = {
    configure(value) { config = value || {}; sync(); },
    scopeChanged() { if (!panel.hidden) sync(); },
    reset() { revision++; history=[]; busy=false; $('runDataChatMessages').replaceChildren(); panel.classList.remove('hasConversation'); status.textContent=''; sync(); }
  };
  $('openRunDataChat').addEventListener('click', () => open(panel.hidden));
  $('closeRunDataChat').addEventListener('click', () => open(false));
  $('runDataChatNew').addEventListener('click', () => window.yamRunDataChat.reset());
  $('runDataChatScope').addEventListener('change', sync);
  $('runDataChatCancel').addEventListener('click', () => {revision++; busy=false;status.textContent='Stopped waiting for this answer. Your question is kept. The server request may finish in the background.';sync();});
  panel.addEventListener('keydown', event => { if(event.key === 'Escape') {event.stopPropagation();open(false);} });
  for (const button of panel.querySelectorAll('[data-question]')) button.addEventListener('click', () => {input.value=button.dataset.question;input.focus();});
  form.addEventListener('submit', ask);
  window.addEventListener('blupe-robot-selected', () => {revision++; config={};busy=false;sync();});
})();
