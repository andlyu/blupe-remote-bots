/* Meeting shell. The shared playground owns every run, queue and chat action. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const workspace = document.querySelector('.watchLayout');
  const header = document.querySelector('.playgroundHeader');
  if (!workspace || !header || !$('composerSend')) return;

  const paths = {
    presentation: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="m8 21 4-4 4 4M12 8v5m-3-3 3-3 3 3"/>',
    pin: '<path d="M8 3h8l-1 6 3 4H6l3-4-1-6Zm4 10v8"/>',
    cameras: '<rect x="3" y="4" width="18" height="11" rx="2"/><rect x="3" y="18" width="4" height="3" rx=".7"/><rect x="10" y="18" width="4" height="3" rx=".7"/><rect x="17" y="18" width="4" height="3" rx=".7"/>',
    settings: '<path d="M4 7h7m4 0h5M4 17h3m4 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    notes: '<path d="M4 4h16v13H9l-5 4V4Z"/><path d="M8 8h8m-8 5h5"/>',
    people: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m3 9v-2a6 6 0 0 0-2-4"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    sound: '<path d="m11 4-6 5H2v6h3l6 5V4Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    muted: '<path d="m11 4-6 5H2v6h3l6 5V4Z"/><path d="m16 9 6 6m0-6-6 6"/>',
    reaction: '<circle cx="12" cy="12" r="9"/><path d="M8 14a4 4 0 0 0 8 0M8 9h.01M16 9h.01"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
  };
  const icon = name => `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
  function button(id, label, symbol, extraClass = '') {
    const node = document.createElement('button');
    node.id = id; node.type = 'button'; node.className = 'meetingControl ' + extraClass;
    node.title = label; node.setAttribute('aria-label', label);
    node.innerHTML = icon(symbol) + `<span class="meetingControlLabel">${label}</span>`;
    return node;
  }

  document.body.classList.add('meetingConsole');
  const room = document.createElement('section');
  room.className = 'meetingRoom'; room.setAttribute('aria-label', 'Robot meeting');
  header.before(room); room.append(header);
  header.querySelector('h1').textContent = 'BluPe';
  const roomContext = document.createElement('span');
  roomContext.className = 'meetingRoomContext'; roomContext.textContent = 'Robot room';
  header.querySelector('.intro').append(roomContext);
  const presenting = document.createElement('div'); presenting.className = 'meetingPresenting';
  presenting.innerHTML = icon('presentation') + '<span id="meetingPresentationName">Connecting to camera…</span><span class="meetingPinned">' + icon('pin') + 'Pinned view</span>';
  room.append(presenting, workspace); workspace.id = 'meetingWorkspace';
  const simulation = $('simulationNotice');
  if (simulation) {
    simulation.classList.remove('eyebrow'); simulation.classList.add('meetingSimulationNotice');
    workspace.before(simulation);
  }

  const panel = document.querySelector('.watchInteraction');
  panel.id = 'meetingTaskPanel'; panel.setAttribute('aria-label', 'Task and notes');
  const closePanel = button('meetingClosePanel', 'Close task and notes', 'close');
  document.querySelector('.taskChatHeading').append(closePanel);
  const dock = document.createElement('section');
  dock.className = 'meetingPromptDock'; dock.setAttribute('aria-labelledby', 'meetingPromptTitle');
  dock.innerHTML = '<div class="meetingPromptHeading"><h2 id="meetingPromptTitle">Prompt the arms</h2><p id="meetingSuggestionStatus" role="status" aria-live="polite">Loading suggestions…</p></div><div id="meetingSuggestions" class="meetingSuggestions" role="group" aria-label="Suggested tasks and discovery"></div>';
  dock.querySelector('.meetingPromptHeading').after(document.querySelector('.runSetup'));
  room.append(dock);
  $('prompt').placeholder = 'What should the arms do?';
  const settings = $('composerSettings');
  function decorateSettings() {
    if (settings.querySelector('svg')) return;
    const label = $('composerOptions') ? settings.textContent : '';
    settings.innerHTML = icon('settings');
    if (label) {
      const text = document.createElement('span'); text.className = 'meetingModelLabel'; text.textContent = label;
      settings.append(text);
    }
  }
  decorateSettings();
  new MutationObserver(decorateSettings).observe(settings, {childList:true,subtree:true});
  const discover = document.createElement('button');
  discover.id = 'meetingExplore'; discover.type = 'button'; discover.className = 'meetingExplore';
  discover.innerHTML = 'What have people run?' + icon('down');
  discover.setAttribute('aria-controls', 'pastRunsCloud');
  $('meetingSuggestions').append(discover);
  discover.addEventListener('click', () => {
    const cloud = $('pastRunsCloud'), toggle = $('pastRunsCloudView');
    if (!cloud || !toggle) return;
    if (toggle.getAttribute('aria-pressed') !== 'true') toggle.click();
    cloud.scrollIntoView({block:'start', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    $('taskCloudCanvas')?.focus({preventScroll:true});
  });
  const dockSize = new ResizeObserver(() => {
    room.style.setProperty('--meeting-dock-height', dock.offsetHeight + 'px');
  });
  dockSize.observe(dock);
  const bar = document.createElement('div');
  bar.className = 'meetingBar'; bar.setAttribute('aria-label', 'Meeting controls');
  const views = button('meetingCameraViews', 'Camera views', 'cameras');
  views.setAttribute('aria-pressed', 'true'); views.setAttribute('aria-controls', 'liveViewer');
  const stop = button('meetingStop', 'Stop run', 'stop', 'meetingStopAction'); stop.disabled = true;
  const visitors = $('openVisitorChat'); visitors.classList.add('meetingControl');
  visitors.title = 'Visitor chat'; visitors.setAttribute('aria-label', 'Visitor chat');
  visitors.innerHTML = icon('people') + '<span class="meetingControlLabel">Visitors</span>';
  const notes = button('meetingNotes', 'Activity', 'notes');
  notes.querySelector('span').textContent = 'Chat';
  notes.setAttribute('aria-controls', panel.id); notes.setAttribute('aria-expanded', 'false');
  const social = document.querySelector('.cameraSocialControls');
  const reactions = document.createElement('details'); reactions.className = 'meetingReactions';
  const reactionToggle = document.createElement('summary');
  reactionToggle.className = 'meetingMoreSummary'; reactionToggle.setAttribute('aria-label', 'Send a reaction');
  reactionToggle.innerHTML = icon('reaction');
  const reactionDock = $('reactionDock');
  reactions.append(reactionToggle);
  if (social && reactionDock) {
    // Effects and live errors remain visible even while the picker is closed.
    social.append($('reactionStage'), $('reactionStatus'));
    social.classList.add('meetingSocialOverlay'); room.append(social);
    reactions.append(reactionDock);
    reactionDock.addEventListener('click', event => {
      if (!event.target.closest('[data-reaction]')) return;
      reactions.open = false; reactionToggle.focus({preventScroll:true});
    });
  }
  reactions.hidden = !reactionDock;
  reactions.addEventListener('toggle', () => {
    reactionToggle.setAttribute('aria-expanded', String(reactions.open));
  });
  const audio = $('robotAudioToggle');
  if (audio) {
    audio.classList.add('meetingControl');
    function decorateAudio() {
      const label = audio.textContent;
      const symbol = /^Mute$/.test(label) ? 'sound' : 'muted';
      if (audio.dataset.meetingSymbol === symbol && audio.querySelector('svg')) return;
      audio.dataset.meetingSymbol = symbol;
      const roomLabel = ({Mute:'Mute robot-room audio', Unmute:'Unmute robot-room audio',
        'Enable audio':'Enable robot-room audio', 'Retry audio':'Retry robot-room audio'})[label] || 'Robot-room audio';
      audio.setAttribute('aria-label', roomLabel); audio.title = roomLabel;
      audio.setAttribute('aria-describedby', 'robotAudioStatus');
      audio.innerHTML = icon(symbol);
      const text = document.createElement('span'); text.className = 'meetingControlLabel'; text.textContent = label;
      audio.append(text);
    }
    decorateAudio(); new MutationObserver(decorateAudio).observe(audio, {childList:true});
  }
  const roomInfo = document.createElement('div'); roomInfo.className = 'meetingInfo';
  roomInfo.innerHTML = '<time id="meetingClock"></time><span class="meetingInfoDivider"></span><span id="meetingRoomName"></span>';
  const callControls = document.createElement('div'); callControls.className = 'meetingCallControls';
  callControls.append(views);
  if (audio) callControls.append(audio);
  callControls.append(notes, reactions, stop);
  const peopleControls = document.createElement('div'); peopleControls.className = 'meetingPeopleControls';
  peopleControls.append(visitors);
  bar.append(roomInfo, callControls, peopleControls); room.append(bar);
  const mobile = window.matchMedia('(max-width:600px), (max-width:1000px) and (max-height:500px)');
  function arrangeControls() {
    if (mobile.matches) callControls.insertBefore(visitors, stop);
    else { callControls.prepend(views); peopleControls.append(visitors); }
    peopleControls.hidden = mobile.matches;
  }
  arrangeControls(); mobile.addEventListener('change', arrangeControls);
  document.addEventListener('click', event => {
    if (!reactions.contains(event.target)) reactions.open = false;
  });

  const below = document.createElement('a'); below.className = 'meetingBelow';
  below.href = '#past-runs'; below.innerHTML = 'Run library ' + icon('down');
  room.after(below);
  const extraDetails = document.querySelector('.watchBelow');
  if (extraDetails) { extraDetails.classList.add('meetingRunDetails'); below.after(extraDetails); }

  const integratedChat = Boolean($('chatPaneTitle'));
  function setPanel(open, restoreFocus = true, focusPanel = true, keepVisitor = false) {
    if (!keepVisitor && !$('visitorChatPanel').hidden) $('closeVisitorChat').click();
    room.classList.toggle('meetingPanelOpen', open);
    panel.inert = !open;
    notes.setAttribute('aria-expanded', String(open));
    if (open && focusPanel) closePanel.focus({preventScroll:true});
    else if (restoreFocus) notes.focus({preventScroll:true});
  }
  // Keep the closed panel out of keyboard navigation as well as the visual view.
  panel.inert = true;
  notes.addEventListener('click', () => setPanel(!$('visitorChatPanel').hidden || !room.classList.contains('meetingPanelOpen')));
  closePanel.addEventListener('click', () => setPanel(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && reactions.open) { reactions.open = false; reactionToggle.focus({preventScroll:true}); return; }
    if (event.key === 'Escape' && room.classList.contains('meetingPanelOpen') && !document.querySelector('dialog[open]') && $('visitorChatPanel').hidden) setPanel(false);
  });
  visitors.addEventListener('click', () => {
    if (!$('visitorChatPanel').hidden) setPanel(integratedChat, false, false, true);
  });
  document.addEventListener('blupe-compose-task', () => {
    room.scrollIntoView({block:'start',behavior:'instant'}); $('prompt').focus({preventScroll:true});
  });
  stop.addEventListener('click', () => { if (!$('stop').disabled) $('stop').click(); });
  views.addEventListener('click', () => {
    const hidden = room.classList.toggle('meetingCamerasHidden');
    views.setAttribute('aria-pressed', String(!hidden));
  });
  function updateControls() {
    stop.disabled = $('stop').disabled;
    const name = $('robotSelector').selectedOptions[0]?.textContent || 'Robot room';
    if ($('meetingRoomName').textContent !== name) $('meetingRoomName').textContent = name;
    room.classList.toggle('meetingCanStop', !stop.disabled);
    const active = $('runForm').classList.contains('runActive');
    dock.classList.toggle('meetingPromptActive', active);
    for (const suggestion of $('meetingSuggestions').children) if (suggestion !== discover) suggestion.disabled = $('prompt').disabled || $('prompt').readOnly;
    if (!$('robotSelector').disabled && suggestionRobot !== $('robotSelector').value) void refreshSuggestions();
  }
  const lifecycle = new MutationObserver(updateControls);
  lifecycle.observe($('runForm'), {subtree:true,childList:true,attributes:true,attributeFilter:['disabled','class','readonly']});
  lifecycle.observe($('liveRunControls'), {subtree:true,attributes:true,attributeFilter:['disabled','hidden']});
  lifecycle.observe($('robotSelector'), {childList:true,subtree:true,attributes:true});
  $('robotSelector').addEventListener('change', updateControls);

  let suggestionRequest = 0, suggestionRobot = null, suggestionSignature = '', suggestionController = null;
  async function refreshSuggestions(force = false) {
    if (document.hidden || $('robotSelector').disabled || (suggestionController && !force)) return;
    suggestionController?.abort();
    const controller = new AbortController(); suggestionController = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    const robot = $('robotSelector').value;
    const request = ++suggestionRequest;
    if (suggestionRobot !== robot) {
      suggestionRobot = robot; suggestionSignature = '';
      $('meetingSuggestions').replaceChildren(discover);
      $('meetingSuggestionStatus').textContent = 'Loading suggestions…';
    }
    try {
      const response = await fetch('/api/task-suggestions?robot_id=' + encodeURIComponent(robot), {credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('Suggestions unavailable');
      const data = await response.json();
      if (request !== suggestionRequest || robot !== $('robotSelector').value) return;
      if (data.robot_id !== robot || !Array.isArray(data.suggestions) || data.suggestions.some(value => typeof value !== 'string')) throw new Error('Invalid suggestions');
      const signature = JSON.stringify(data.suggestions);
      if (signature !== suggestionSignature) {
        $('meetingSuggestions').replaceChildren(...data.suggestions.map(text => {
          const choice = document.createElement('button');
          choice.type = 'button'; choice.textContent = text; choice.title = text;
          choice.addEventListener('click', () => {
            if ($('prompt').disabled || $('prompt').readOnly) return;
            $('prompt').value = text;
            $('prompt').dispatchEvent(new Event('input', {bubbles:true}));
            $('prompt').focus({preventScroll:true});
          });
          return choice;
        }), discover);
        suggestionSignature = signature;
      }
      $('meetingSuggestionStatus').textContent = '';
      updateControls();
    } catch {
      if (request === suggestionRequest && robot === $('robotSelector').value) $('meetingSuggestionStatus').textContent = 'Suggestions unavailable. You can write your own task; retrying…';
    } finally {
      clearTimeout(timeout);
      if (suggestionController === controller) suggestionController = null;
      if (robot !== $('robotSelector').value) void refreshSuggestions();
    }
  }
  window.addEventListener('blupe-robot-selected', () => {
    suggestionRobot = null;
    $('meetingSuggestions').replaceChildren(discover); suggestionSignature = '';
    $('meetingSuggestionStatus').textContent = 'Loading suggestions…';
    void refreshSuggestions(true);
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refreshSuggestions(); });
  setInterval(refreshSuggestions, 5000); void refreshSuggestions();

  function updateCameras() {
    const figures = [...$('liveViewer').querySelectorAll('figure[data-camera-role]')];
    const main = figures.find(node => node.dataset.cameraRole === 'observer') || figures.find(node => node.dataset.cameraRole === 'top') || figures[0];
    for (const figure of figures) figure.toggleAttribute('data-meeting-main', figure === main);
    const role = main?.dataset.cameraRole;
    $('meetingPresentationName').textContent = role ? role.charAt(0).toUpperCase() + role.slice(1) + ' camera is presenting' : $('armsDisconnected') ? 'Camera unavailable' : 'Connecting to camera…';
    $('liveViewer').style.setProperty('--meeting-side-count', Math.max(1, figures.length - 1));
    $('liveViewer').dataset.meetingCount = String(figures.length);
    views.disabled = figures.length < 2;
  }
  new MutationObserver(updateCameras).observe($('liveViewer'), {childList:true});
  function viewport() {
    const height = Math.min(window.innerHeight, window.visualViewport?.height || window.innerHeight);
    room.style.setProperty('--meeting-viewport-height', height + 'px');
    room.classList.toggle('meetingKeyboardOpen', window.innerHeight - height > 120);
  }
  window.visualViewport?.addEventListener('resize', viewport);
  window.addEventListener('resize', viewport); viewport();
  function updateQuietStatus() {
    const emptyQueue = /^Queue\s*·\s*0 waiting(?:\s*·\s*Your place:\s*[—–-])?$/.test($('queueSummary').textContent.trim())
      && $('leaveQueue').hidden && $('position').closest('.queuePlace').hidden;
    $('yourQueue').classList.toggle('meetingQueueEmpty', emptyQueue);
    const timer = $('runTimer'), stopwatch = timer?.closest('.liveStopwatch');
    if (stopwatch) stopwatch.hidden = !$('liveTaskTitle')?.textContent.trim()
      && (!timer.textContent.trim() || /^[—–\-:]+$/.test(timer.textContent.trim()));
  }
  new MutationObserver(updateQuietStatus).observe($('yourQueue'), {childList:true,characterData:true,subtree:true,attributes:true,attributeFilter:['hidden']});
  new MutationObserver(updateQuietStatus).observe($('liveViewer'), {childList:true,characterData:true,subtree:true});
  function clock() { $('meetingClock').textContent = new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}); }
  clock(); setInterval(clock, 30000);
  updateControls(); updateCameras(); updateQuietStatus();
  setPanel(!mobile.matches, false, false);
})();
