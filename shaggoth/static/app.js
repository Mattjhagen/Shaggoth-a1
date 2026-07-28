// Register the service worker, and check for a new one on every load.
//
// Without the explicit update() an updated worker can sit "waiting" until
// every tab is closed, which on a PWA can be days. The worker calls
// skipWaiting(), so a reload after it activates picks up the new build.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').then((reg) => {
    reg.update().catch(() => {});
    // A controller change means a new worker took over mid-session; reload
    // once so the page and its assets come from the same build.
    let reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloading) return;
      reloading = true;
      location.reload();
    });
  }).catch(() => {});
}

// PWA install prompt and mobile features
let deferredPrompt = null;

function detectDevice() {
  const ua = navigator.userAgent.toLowerCase();
  return {
    isIOS: /iphone|ipad|ipod/.test(ua),
    isAndroid: /android/.test(ua),
    isMobile: /iphone|ipad|ipod|android/.test(ua),
  };
}

function showInstallPrompt() {
  const device = detectDevice();
  const promptShown = localStorage.getItem('shaggoth_install_prompted');

  if (promptShown) return;

  if (device.isAndroid && deferredPrompt) {
    // Android: show the native install banner
    const installContainer = document.getElementById('installPrompt');
    if (installContainer) {
      installContainer.style.display = 'flex';
      document.getElementById('installBtn').addEventListener('click', () => {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {
          deferredPrompt = null;
          installContainer.style.display = 'none';
          localStorage.setItem('shaggoth_install_prompted', 'true');
          showFirstTimeTutorial();
        });
      });
      document.getElementById('dismissInstallBtn').addEventListener('click', () => {
        installContainer.style.display = 'none';
        localStorage.setItem('shaggoth_install_prompted', 'true');
      });
    }
  } else if (device.isIOS) {
    // iOS: show manual install instructions
    const installContainer = document.getElementById('installPrompt');
    if (installContainer) {
      const content = installContainer.querySelector('.install-content');
      if (content) {
        content.innerHTML = `
          <div class="install-header">Add to Home Screen</div>
          <p>Tap the share icon and select "Add to Home Screen" to use Shaggoth as an app!</p>
          <div class="install-steps">
            <div class="install-step">
              <span class="step-number">1</span>
              <span class="step-text">Tap the share button (up arrow in a box)</span>
            </div>
            <div class="install-step">
              <span class="step-number">2</span>
              <span class="step-text">Select "Add to Home Screen"</span>
            </div>
            <div class="install-step">
              <span class="step-number">3</span>
              <span class="step-text">Tap "Add" to confirm</span>
            </div>
          </div>
        `;
        installContainer.style.display = 'flex';
        document.getElementById('dismissInstallBtn').addEventListener('click', () => {
          installContainer.style.display = 'none';
          localStorage.setItem('shaggoth_install_prompted', 'true');
        });
      }
    }
  }
}

function showFirstTimeTutorial() {
  const tutorialShown = localStorage.getItem('shaggoth_tutorial_shown');

  if (tutorialShown) return;

  const tutorialContainer = document.getElementById('firstTimeTutorial');
  if (!tutorialContainer) return;

  tutorialContainer.style.display = 'flex';

  // Step 1: Notifications
  function showNotificationStep() {
    const content = tutorialContainer.querySelector('.tutorial-content');
    if (content) {
      content.innerHTML = `
        <div class="tutorial-header">Enable Notifications</div>
        <p>Get instant updates when Shaggoth finds new information:</p>
        <button class="tutorial-btn primary" id="enableNotifications">Enable Notifications</button>
        <button class="tutorial-btn" id="skipNotifications">Skip for now</button>
      `;
      document.getElementById('enableNotifications').addEventListener('click', requestNotificationPermission);
      document.getElementById('skipNotifications').addEventListener('click', showFeaturesStep);
    }
  }

  function requestNotificationPermission() {
    if ('Notification' in window) {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          toast('Notifications enabled!');
          showFeaturesStep();
        } else {
          showFeaturesStep();
        }
      });
    }
  }

  function showFeaturesStep() {
    const content = tutorialContainer.querySelector('.tutorial-content');
    if (content) {
      content.innerHTML = `
        <div class="tutorial-header">Shaggoth Features</div>
        <ul class="tutorial-features">
          <li><strong>Chat:</strong> Ask questions and have conversations</li>
          <li><strong>Knowledge:</strong> Browse and manage learned information</li>
          <li><strong>Memory:</strong> Review what Shaggoth remembers about you</li>
          <li><strong>Learn:</strong> Train on new content</li>
          <li><strong>Settings:</strong> Customize your experience</li>
        </ul>
        <button class="tutorial-btn primary" id="closeTutorial">Get Started!</button>
      `;
      document.getElementById('closeTutorial').addEventListener('click', closeTutorial);
    }
  }

  function closeTutorial() {
    tutorialContainer.style.display = 'none';
    localStorage.setItem('shaggoth_tutorial_shown', 'true');
  }

  showNotificationStep();
}

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  showInstallPrompt();
});

window.addEventListener('appinstalled', () => {
  deferredPrompt = null;
  localStorage.setItem('shaggoth_installed', 'true');
  showFirstTimeTutorial();
});

// Check if running as installed app
if (window.matchMedia('(display-mode: standalone)').matches) {
  localStorage.setItem('shaggoth_installed', 'true');
}

// Show install prompt on first visit
window.addEventListener('load', () => {
  if (!localStorage.getItem('shaggoth_first_visit')) {
    localStorage.setItem('shaggoth_first_visit', 'true');
    setTimeout(() => showInstallPrompt(), 1000);
  }
});

function detectApi() {
  const saved = localStorage.getItem('shaggoth_api');
  if (saved) return saved.replace(/\/+$/, '');
  if (location.hostname === 'ai.vibecodes.space' || location.hostname.endsWith('.workers.dev'))
    return location.origin + '/api';
  return window.location.origin;
}

function getApiKey() { return localStorage.getItem('shaggoth_key') || ''; }

const API = detectApi();
/* One conversation per browser, not per page load.
 *
 * This was regenerated on every load, so /history?session_id= always returned
 * only what had been said since the last refresh -- the Memory tab looked
 * empty and Shaggoth could never recall an earlier conversation with you.
 * Persisted now, with a "new chat" escape hatch. */
const SESSION_KEY = 'shaggoth_session';
let sessionId = localStorage.getItem(SESSION_KEY);
if (!sessionId) {
  sessionId = 'web-' + Math.random().toString(36).slice(2, 10);
  localStorage.setItem(SESSION_KEY, sessionId);
}

function newSession() {
  localStorage.removeItem(SESSION_KEY);
  location.reload();
}

function h() { return { 'Content-Type': 'application/json', ...(getApiKey() ? { 'Authorization': 'Bearer ' + getApiKey() } : {}) }; }

// Answer mode: "no_drift" (grounded) or "drift" (free-associating).
function getMode() { return localStorage.getItem('shaggoth_mode') || 'no_drift'; }

/* Parse a response body as JSON, or throw something a human can act on.
 *
 * Calling r.json() directly surfaces the raw parser error, which is how the
 * chat window ended up showing `Unexpected token '<', "<!DOCTYPE"... is not
 * valid JSON` (and, on iOS Safari, the same failure worded as `The string did
 * not match the expected pattern.`). Both meant the server had returned an
 * HTML error page. Neither told anyone that. */
async function readJson(r) {
  const body = await r.text();
  try {
    return JSON.parse(body);
  } catch {
    const looksLikeHtml = /^\s*<(?:!doctype|html)/i.test(body);
    if (looksLikeHtml) {
      throw new Error(
        `the server returned an error page instead of an answer (HTTP ${r.status}). ` +
        `Check the Shaggoth logs: journalctl -u shaggoth -n 50`
      );
    }
    if (!r.ok) throw new Error(`server error (HTTP ${r.status})`);
    throw new Error('the server sent a reply I could not read');
  }
}

/* Track the *visual* viewport so the on-screen keyboard cannot cover the
 * input. vh units do not change when the keyboard opens; visualViewport is
 * the only thing that reports it. */
(function trackViewport() {
  const vv = window.visualViewport;
  if (!vv) return;
  const sync = () => {
    document.documentElement.style.setProperty('--app-h', vv.height + 'px');
  };
  vv.addEventListener('resize', sync);
  vv.addEventListener('scroll', sync);
  sync();
})();

// Auth check
(async () => {
  try {
    const r = await fetch(API + '/health');
    if (r.ok) return;
  } catch {}
  const key = getApiKey();
  if (!key) return;
})()

// Drawer
function toggleDrawer() { document.getElementById('drawer').classList.toggle('open'); }

/* Navigation, driven by the URL hash.
 *
 * The nav entries are real anchors with href="#view", so the tab survives a
 * reload, works with the back button, and can be linked to directly. The
 * hashchange handler is the single place a view is activated -- clicking a
 * link only changes the hash. */
const VIEWS = ['chat', 'personality', 'knowledge', 'learn', 'memory', 'guardrails', 'settings'];
const VIEW_LOADERS = {
  settings: () => refreshNotifyUi(),
  memory: () => loadMemory(),
  guardrails: () => loadGuardrails(),
  learn: () => loadLearnStatus(),
  personality: () => loadPersonality(),
  knowledge: () => loadKnowledgeList(),
};

function applyRoute(view) {
  if (!VIEWS.includes(view)) view = 'chat';
  document.querySelectorAll('.drawer-nav a').forEach(x =>
    x.classList.toggle('active', x.dataset.view === view));
  document.querySelectorAll('.view').forEach(v =>
    v.classList.toggle('active', v.id === 'view-' + view));
  if (window.innerWidth <= 768) document.getElementById('drawer').classList.remove('open');
  const load = VIEW_LOADERS[view];
  if (load) load();
}

/* Read the view out of the URL hash.
 *
 * Accepts #learn, #/learn, and #/learn/ alike. People type and share the
 * router-style "#/learn" form by habit, and only "#learn" used to resolve --
 * everything else silently fell back to the chat view. */
function currentRoute() {
  return (location.hash || '')
    .replace(/^#/, '')
    .replace(/^\/+/, '')
    .replace(/\/+$/, '')
    .split(/[/?]/)[0]
    .toLowerCase() || 'chat';
}

window.addEventListener('hashchange', () => applyRoute(currentRoute()));
applyRoute(currentRoute());

window.switchView = (v) => { location.hash = v; applyRoute(v); };

// Settings
document.getElementById('apiUrl').value = API;
const savedKey = localStorage.getItem('shaggoth_key');
if (savedKey) document.getElementById('apiKey').value = savedKey;

const modeSelect = document.getElementById('driftMode');
if (modeSelect) modeSelect.value = getMode();

function saveSettings() {
  localStorage.setItem('shaggoth_api', document.getElementById('apiUrl').value.replace(/\/+$/, ''));
  localStorage.setItem('shaggoth_key', document.getElementById('apiKey').value);
  if (modeSelect) localStorage.setItem('shaggoth_mode', modeSelect.value);
  toast('Settings saved. Reloading...');
  setTimeout(() => location.reload(), 600);
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// Health
async function checkHealth() {
  try {
    const r = await fetch(API + '/health');
    const d = await r.json();
    document.getElementById('statusDot').classList.add('connected');
    document.getElementById('statusText').textContent = `Connected (${d.version})`;
  } catch {
    document.getElementById('statusDot').classList.remove('connected');
    document.getElementById('statusText').textContent = 'Disconnected';
  }
}
checkHealth();
setInterval(checkHealth, 15000);

// Chat
const messagesEl = document.getElementById('messages');
const inputBar = document.getElementById('inputBar');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const flagBadge = document.getElementById('flagBadge');

/* Replace the fallback opening line with a fresh one from the server.
 *
 * GET /greeting composes a line that cites the current knowledge count and
 * the most recent thing it read, so the first message is different every
 * load and is actually about what it has been doing. */
async function loadGreeting() {
  const el = document.getElementById('greetingMsg');
  if (!el) return;
  try {
    const r = await fetch(API + '/greeting', { headers: h() });
    if (!r.ok) return;
    const d = await readJson(r);
    const line = (d.greeting || d.text || d.reply || '').trim();
    if (line) el.querySelector('.msg-content').textContent = line;
  } catch {
    // Keep the markup's fallback line. A missing greeting is cosmetic.
  }
}
loadGreeting();

inputBar.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  appendMsg('user', text);
  chatInput.value = '';
  sendBtn.disabled = true;
  const thinking = appendThinking();
  try {
    const r = await fetch(API + '/chat', {
      method: 'POST', headers: h(),
      body: JSON.stringify({ message: text, session_id: sessionId, mode: getMode() }),
    });
    const d = await readJson(r);
    thinking.remove();
    appendMsg('assistant', d.reply, d.source, d.flag, d);
    flagBadge.textContent = (d.flag && d.flag !== 'green') ? d.flag.toUpperCase() : '';
  } catch (err) {
    thinking.remove();
    appendMsg('assistant', 'Error: ' + err.message, 'error');
  }
  sendBtn.disabled = false;
  chatInput.focus();
});

function appendThinking() {
  const div = document.createElement('div');
  div.className = 'msg assistant thinking';
  div.innerHTML =
    '<div class="msg-content"><span class="thinking-dots">' +
    '<span></span><span></span><span></span></span>' +
    '<span>thinking</span></div>';
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function appendMsg(role, text, source, flag, meta) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  let html = '<div class="msg-content">' + esc(text || '') + '</div>';
  const tags = [];
  if (source && source !== 'pattern') tags.push(source);
  if (flag && flag !== 'green') tags.push(flag.toUpperCase());
  if (tags.length) html += '<div class="msg-source">' + tags.join(' · ') + '</div>';

  const detail = replyDetail(meta);
  if (detail) {
    html += '<details class="msg-detail"><summary>how it got that</summary>' +
            '<div class="msg-detail-body">' + esc(detail) + '</div></details>';
  }
  // Judgement on an answer is the most valuable signal this system gets, and
  // until now it was thrown away. entries_used makes it actionable: marking a
  // reply bad implicates the specific knowledge entry behind it.
  if (role === 'assistant' && source && source !== 'error') {
    html += '<div class="msg-rate">' +
      '<button class="rate-btn" data-v="good" title="Good answer">&#128077;</button>' +
      '<button class="rate-btn" data-v="bad" title="Wrong or unhelpful">&#128078;</button>' +
      '</div>';
  }
  div.innerHTML = html;
  div.querySelectorAll('.rate-btn').forEach((b) => {
    b.addEventListener('click', () => openNote(div, b.dataset.v, meta, text));
  });
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

/* Explain where a reply came from, using only what the API already returns.
 * Collapsed by default -- available when an answer looks wrong, invisible
 * when it does not. */
const SOURCE_EXPLANATION = {
  knowledge: 'Answered from a stored knowledge entry.',
  pattern:   'Canned conversational reply, no retrieval involved.',
  model:     'Generated by the language model. Least reliable path.',
  reasoning: 'Combined several knowledge entries; the steps are listed below.',
  fallback:  "Didn't know this one. Curiosity research has been triggered.",
  plugin:    'Handled by a built-in command rather than the dialogue engine.',
  guardrail: 'Blocked by a guardrail rule before generation.',
  error:     'The request failed before an answer was produced.',
};

function replyDetail(meta) {
  if (!meta) return '';
  const lines = [];
  if (meta.source) {
    lines.push('source: ' + meta.source);
    if (SOURCE_EXPLANATION[meta.source]) lines.push('  ' + SOURCE_EXPLANATION[meta.source]);
  }
  if (meta.mode) {
    lines.push('mode: ' + meta.mode +
      (meta.mode === 'no_drift' ? '  (grounded — no improvising)' : '  (drift — allowed to wander)'));
  }
  if (meta.reasoning && meta.reasoning.length) {
    lines.push('steps:');
    for (const step of meta.reasoning) lines.push('  ' + step);
  }
  if (meta.entries_used && meta.entries_used.length)
    lines.push('entries: ' + meta.entries_used.join(', '));
  if (meta.rule_id) lines.push('rule: ' + meta.rule_id);
  if (meta.output_rules_applied && meta.output_rules_applied.length)
    lines.push('output filters: ' + meta.output_rules_applied.join(', '));
  if (meta.memory_triggers && meta.memory_triggers.length)
    lines.push('recalled: ' + meta.memory_triggers.join(', '));
  if (meta.new_facts && Object.keys(meta.new_facts).length)
    lines.push('learned: ' + Object.entries(meta.new_facts).map(([k, v]) => k + '=' + v).join(', '));
  return lines.join('\n');
}

function esc(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

// Personality
async function loadPersonality() {
  try {
    const r = await fetch(API + '/personality', { headers: h() });
    const d = await r.json();
    const el = document.getElementById('personalityDisplay');
    el.innerHTML = `
      <div class="personality-section"><h3>Backstory</h3><p>${esc(d.backstory || '')}</p></div>
      <div class="personality-section"><h3>Traits</h3><div class="trait-tags">${(d.traits||[]).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>
      <div class="personality-section"><h3>Style</h3><p>${esc(d.speaking_style || '')}</p></div>
      <div class="personality-section"><h3>Interests</h3><div class="trait-tags">${(d.interests||[]).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>
      <div class="personality-section"><h3>Values</h3><div class="trait-tags">${(d.values||[]).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>
    `;
  } catch {}
}

// Knowledge
async function loadKnowledgeList() {
  try {
    const r = await fetch(API + '/knowledge', { headers: h() });
    const d = await r.json();
    const el = document.getElementById('knowledgeList');
    const entries = d.entries || [];
    el.innerHTML = entries.length ? entries.map(e =>
      `<div class="knowledge-entry"><div class="knowledge-topic">${esc(e.topic)}</div><div class="knowledge-meta">${e.word_count} words</div></div>`
    ).join('') : '<p style="color:var(--text-dim)">No entries yet.</p>';
  } catch {}
}

async function searchKnowledge() {
  const q = document.getElementById('knowledgeSearch').value.trim();
  if (!q) return;
  try {
    const r = await fetch(API + '/knowledge/query?q=' + encodeURIComponent(q), { headers: h() });
    const d = await r.json();
    const el = document.getElementById('knowledgeList');
    const results = d.results || [];
    el.innerHTML = results.length ? results.map(r =>
      `<div class="knowledge-entry"><div class="knowledge-topic">${esc(r.topic)} <span class="knowledge-score">${r.score}</span></div><div class="knowledge-content">${esc(r.content.slice(0,300))}</div></div>`
    ).join('') : '<p style="color:var(--text-dim)">No relevant knowledge.</p>';
  } catch {}
}

async function addKnowledge() {
  const topic = document.getElementById('knowledgeTopic').value.trim();
  const content = document.getElementById('knowledgeContent').value.trim();
  if (!topic || !content) { toast('Topic and content required'); return; }
  try {
    await fetch(API + '/knowledge/add', { method: 'POST', headers: h(), body: JSON.stringify({topic,content}) });
    document.getElementById('knowledgeTopic').value = '';
    document.getElementById('knowledgeContent').value = '';
    loadKnowledgeList();
    toast('Added knowledge entry');
  } catch {}
}

// Learn
async function loadLearnStatus() {
  try {
    const r = await fetch(API + '/learn/status', { headers: h() });
    const d = await r.json();
    document.getElementById('statPages').textContent = d.scraper_stats?.pages_stored || 0;
    document.getElementById('statWords').textContent = fmt(d.scraper_stats?.total_words || 0);
    // Name the model rather than just Yes/No: "markov" vs "tinygpt" is the
    // difference between canned-ish output and a real generative model.
    document.getElementById('statModel').textContent =
      d.model_exists ? (d.model_kind || 'yes') : 'none';
    document.getElementById('statSessions').textContent = d.total_sessions || 0;
    const btn = document.getElementById('learnBtn');
    btn.disabled = !!d.current_session;
    btn.textContent = d.current_session ? 'Learning...' : 'Start Learning';
    const lr = await fetch(API + '/learn/history', { headers: h() });
    const ld = await lr.json();
    const logEl = document.getElementById('learnLogEntries');
    if (!ld.sessions || !ld.sessions.length) { logEl.innerHTML = 'No sessions yet.'; return; }
    logEl.innerHTML = ld.sessions.reverse().map(s =>
      `<div class="log-entry"><span class="${s.status === 'completed' ? 'ok' : s.status === 'failed' ? 'err' : ''}">[${s.status}]</span> ${s.pages_scraped}p ${fmt(s.words_learned)}w</div>`
    ).join('');
  } catch {}
}

async function startLearning() {
  const urls = document.getElementById('seedUrls').value.split('\n').map(u => u.trim()).filter(Boolean);
  const body = { urls, crawl_depth: parseInt(document.getElementById('crawlDepth').value)||1, max_pages: parseInt(document.getElementById('maxPages').value)||20, training_steps: parseInt(document.getElementById('trainSteps').value)||1000 };
  document.getElementById('learnBtn').disabled = true;
  document.getElementById('learnBtn').textContent = 'Learning...';
  try {
    await fetch(API + '/learn/start', { method: 'POST', headers: h(), body: JSON.stringify(body) });
    pollLearn();
  } catch {}
}

function pollLearn() {
  const iv = setInterval(async () => {
    try {
      const r = await fetch(API + '/learn/status', { headers: h() });
      const d = await r.json();
      if (!d.is_learning) { clearInterval(iv); loadLearnStatus(); }
    } catch {}
  }, 3000);
}

function fmt(n) {
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return String(n);
}

// Memory
async function loadMemory() {
  try {
    const [fr, hr] = await Promise.all([
      fetch(API + '/facts', { headers: h() }),
      fetch(API + '/history?session_id=' + sessionId, { headers: h() }),
    ]);
    const fd = await fr.json();
    const hd = await hr.json();
    const facts = fd.facts || {};
    document.getElementById('factsList').innerHTML = Object.keys(facts).length
      ? Object.entries(facts).map(([k,v]) => `<div class="fact-row"><span class="fact-key">${esc(k)}</span><span class="fact-val">${esc(v)}</span></div>`).join('')
      : '<p style="color:var(--text-dim)">No facts yet.</p>';
    const msgs = hd.messages || [];
    document.getElementById('historyList').innerHTML = msgs.length
      ? msgs.slice(-20).map(m => `<div class="history-entry"><div class="history-role ${m.role}">${m.role}</div><div>${esc(m.content)}</div></div>`).join('')
      : '<p style="color:var(--text-dim)">No messages yet.</p>';
  } catch {}
}

// Guardrails
async function loadGuardrails() {
  try {
    const r = await fetch(API + '/guardrails', { headers: h() });
    const d = await r.json();
    // /guardrails returns the whole config -- {version, enabled, input_rules,
    // output_rules} -- and never a flat "rules" key, so this tab reported
    // "No guardrail rules" while five rules were active and blocking
    // credentials on the live endpoint. A guardrails page that under-reports
    // is worse than no page at all.
    const rules = [...(d.input_rules || []), ...(d.output_rules || [])];
    document.getElementById('guardrailsList').innerHTML = rules.length
      ? rules.map(r => {
          const en = r.enabled !== false;
          return `<div class="rule-card"><div class="rule-info"><h4>${esc(r.id)}</h4><p>${esc(r.message || r.type)}</p></div><span class="rule-type ${en ? 'rule-enabled' : 'rule-disabled'}">${r.type} ${en ? '✓' : '✗'}</span></div>`;
        }).join('')
      : '<p style="color:var(--text-dim)">No guardrail rules.</p>';
    const master = document.getElementById('guardrailsState');
    if (master) {
      master.textContent = d.enabled === false
        ? 'Guardrails are switched OFF entirely — no rule below is being applied.'
        : `Guardrails active: ${(d.input_rules || []).length} input, ${(d.output_rules || []).length} output.`;
    }
  } catch {}
}


/* ================================================================ push
 *
 * Opt-in only, and only on a click: browsers reject a permission prompt that
 * was not triggered by a user gesture, and silently deny it forever if you
 * ask at load time.
 */

function urlBase64ToUint8Array(base64) {
  // VAPID keys are base64url without padding; the Push API wants raw bytes.
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function pushStatus() {
  try {
    return await readJson(await fetch(API + '/push/status', { headers: h() }));
  } catch {
    return { available: false };
  }
}

async function enableNotifications() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    toast('This browser cannot do web push.');
    return;
  }
  const status = await pushStatus();
  if (!status.available || !status.public_key) {
    toast('Push is not configured on the server.');
    return;
  }

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    toast('Notifications denied. Nothing will be sent.');
    return;
  }

  try {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    const sub = existing || (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(status.public_key),
    }));
    const r = await fetch(API + '/push/subscribe', {
      method: 'POST', headers: h(),
      body: JSON.stringify({ subscription: sub.toJSON(), session_id: sessionId }),
    });
    await readJson(r);
    toast("Subscribed. It'll tell you when it learns something.");
    refreshNotifyUi();
  } catch (err) {
    toast('Could not subscribe: ' + err.message);
  }
}

async function disableNotifications() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await fetch(API + '/push/unsubscribe', {
        method: 'POST', headers: h(),
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
      await sub.unsubscribe();
    }
    toast('Unsubscribed.');
    refreshNotifyUi();
  } catch (err) {
    toast('Could not unsubscribe: ' + err.message);
  }
}

async function testNotification() {
  try {
    const r = await fetch(API + '/push/test', {
      method: 'POST', headers: h(),
      body: JSON.stringify({ body: 'This is what it will look like.' }),
    });
    const d = await readJson(r);
    toast(d.sent ? `Sent to ${d.sent} device(s).` : 'Nothing subscribed yet.');
  } catch (err) {
    toast('Test failed: ' + err.message);
  }
}

async function refreshNotifyUi() {
  const el = document.getElementById('notifyState');
  if (!el) return;
  const status = await pushStatus();
  if (!status.available) {
    el.textContent = 'Push is not configured on the server.';
    return;
  }
  let subscribed = false;
  try {
    const reg = await navigator.serviceWorker.ready;
    subscribed = !!(await reg.pushManager.getSubscription());
  } catch {}
  el.textContent = subscribed
    ? `Subscribed. ${status.subscriptions} device(s) registered; at most one notification an hour.`
    : `Not subscribed. ${status.subscriptions} other device(s) registered.`;
}

/* ------------------------------------------------------- deferred answers
 *
 * Questions it could not answer at the time. Once curiosity has researched
 * the topic the answer is waiting here, so it turns up even if the push was
 * missed or never enabled.
 */
async function checkDeferred() {
  try {
    const r = await fetch(
      API + '/deferred?undelivered=1&session_id=' + encodeURIComponent(sessionId),
      { headers: h() }
    );
    const d = await readJson(r);
    for (const item of d.answered || []) {
      appendMsg('assistant',
        `You asked me "${item.question}" earlier and I didn't know. I do now:\n\n${item.answer}`,
        'deferred');
    }
  } catch {
    // Silent: this is a background nicety, not part of any request.
  }
}
setTimeout(checkDeferred, 2500);
setInterval(checkDeferred, 120000);

/* ---------------------------------------------------- proactive messages
 *
 * Shaggoth may send unprompted messages while you're away. They're stored
 * as assistant turns in memory. We poll for new ones since the last ID we
 * saw and inject them into the chat so they feel like live messages.
 */
let _lastProactiveId = 0;

async function checkProactive() {
  try {
    const r = await fetch(
      API + '/proactive/messages?session_id=' + encodeURIComponent(sessionId) +
        '&since_id=' + _lastProactiveId,
      { headers: h() }
    );
    const d = await readJson(r);
    for (const msg of d.messages || []) {
      // Skip messages from before the page loaded (they're already in history).
      if (_lastProactiveId === 0) {
        _lastProactiveId = msg.id;
        continue;
      }
      appendMsg('assistant', msg.text, 'proactive');
      _lastProactiveId = msg.id;
    }
    // After first pass just advance the watermark without showing old messages.
    if (_lastProactiveId === 0 && (d.messages || []).length) {
      _lastProactiveId = d.messages[d.messages.length - 1].id;
    }
  } catch {
    // Background nicety — never block anything.
  }
}
// First call initialises the watermark; subsequent calls surface new messages.
setTimeout(checkProactive, 1500);
setInterval(checkProactive, 30000);


/* Send a judgement about an answer. A thumbs-down names the knowledge entries
 * the reply was built from, which is what turns it into a repair job rather
 * than an opinion. */
/* Open an inline note field. A browser prompt() blocks the page, is trivially
 * dismissed, and was only offered on a thumbs-down -- so "this was good
 * BECAUSE it cited the right entry" had nowhere to go. Remarks are the part
 * of the signal that says *why*, and why is what makes a repair targeted
 * rather than a blind re-fetch. */
function openNote(el, verdict, meta, answer) {
  const bar = el.querySelector('.msg-rate');
  if (!bar || bar.querySelector('.rate-note')) return;

  const wrap = document.createElement('div');
  wrap.className = 'rate-note';
  wrap.innerHTML =
    '<textarea rows="2" placeholder="' +
    (verdict === 'bad'
      ? 'What was wrong? Which part, and what did you expect?'
      : 'What made this a good answer? (optional)') +
    '"></textarea>' +
    '<div class="rate-note-actions">' +
    '<button class="btn rate-send">Send</button>' +
    '<button class="btn rate-skip">Just the rating</button>' +
    '</div>';
  bar.appendChild(wrap);

  const box = wrap.querySelector('textarea');
  box.focus();
  const submit = (note) => sendFeedback(el, verdict, meta, answer, note);
  wrap.querySelector('.rate-send').addEventListener('click', () => submit(box.value));
  wrap.querySelector('.rate-skip').addEventListener('click', () => submit(''));
  box.addEventListener('keydown', (e) => {
    // Enter sends, Shift+Enter for a second line.
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(box.value); }
    if (e.key === 'Escape') wrap.remove();
  });
}

async function sendFeedback(el, verdict, meta, answer, note) {
  const asked = [...messagesEl.querySelectorAll('.msg.user .msg-content')].pop();
  note = note || '';
  try {
    await fetch(API + '/feedback', {
      method: 'POST', headers: h(),
      body: JSON.stringify({
        question: asked ? asked.textContent : '',
        verdict, note, answer,
        source: (meta && meta.source) || '',
        entries_used: (meta && meta.entries_used) || [],
        reasoning: (meta && meta.reasoning) || [],
        session_id: sessionId,
      }),
    });
    const entries = (meta && meta.entries_used) || [];
    el.querySelector('.msg-rate').textContent =
      verdict === 'good'
        ? (note ? 'noted, with your remark' : 'noted')
        : entries.length
          ? `noted — queued to re-read ${entries.join(', ')}`
          : 'noted';
  } catch (err) {
    toast('Could not send feedback: ' + err.message);
  }
}
