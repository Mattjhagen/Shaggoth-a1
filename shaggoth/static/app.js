// Register service worker for PWA
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})
}

function detectApi() {
  const saved = localStorage.getItem('shaggoth_api');
  if (saved) return saved.replace(/\/+$/, '');
  if (location.hostname === 'ai.vibecodes.space' || location.hostname.endsWith('.workers.dev'))
    return location.origin + '/api';
  return window.location.origin;
}

function getApiKey() { return localStorage.getItem('shaggoth_key') || ''; }

const API = detectApi();
let sessionId = 'web-' + Math.random().toString(36).slice(2, 10);

function h() { return { 'Content-Type': 'application/json', ...(getApiKey() ? { 'Authorization': 'Bearer ' + getApiKey() } : {}) }; }

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

// Navigation
document.querySelectorAll('.drawer-nav a').forEach(a => {
  a.addEventListener('click', () => {
    document.querySelectorAll('.drawer-nav a').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    a.classList.add('active');
    document.getElementById('view-' + a.dataset.view).classList.add('active');
    if (window.innerWidth <= 768) document.getElementById('drawer').classList.remove('open');
    const v = a.dataset.view;
    if (v === 'memory') loadMemory();
    if (v === 'guardrails') loadGuardrails();
    if (v === 'learn') loadLearnStatus();
    if (v === 'personality') loadPersonality();
    if (v === 'knowledge') loadKnowledgeList();
  });
});
window.switchView = (v) => document.querySelector(`.drawer-nav a[data-view="${v}"]`).click();

// Settings
document.getElementById('apiUrl').value = API;
const savedKey = localStorage.getItem('shaggoth_key');
if (savedKey) document.getElementById('apiKey').value = savedKey;

function saveSettings() {
  localStorage.setItem('shaggoth_api', document.getElementById('apiUrl').value.replace(/\/+$/, ''));
  localStorage.setItem('shaggoth_key', document.getElementById('apiKey').value);
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

inputBar.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  appendMsg('user', text);
  chatInput.value = '';
  sendBtn.disabled = true;
  try {
    const r = await fetch(API + '/chat', {
      method: 'POST', headers: h(),
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    const d = await r.json();
    appendMsg('assistant', d.reply, d.source, d.flag);
    if (d.flag && d.flag !== 'green') flagBadge.textContent = d.flag.toUpperCase();
    else flagBadge.textContent = '';
  } catch (err) {
    appendMsg('assistant', 'Error: ' + err.message, 'error');
  }
  sendBtn.disabled = false;
  chatInput.focus();
});

function appendMsg(role, text, source, flag) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  let html = '<div class="msg-content">' + esc(text) + '</div>';
  const tags = [];
  if (source && source !== 'pattern') tags.push(source);
  if (flag && flag !== 'green') tags.push(flag.toUpperCase());
  if (tags.length) html += '<div class="msg-source">' + tags.join(' · ') + '</div>';
  div.innerHTML = html;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
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
    document.getElementById('statModel').textContent = d.model_exists ? 'Yes' : 'No';
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
    const rules = d.rules || [];
    document.getElementById('guardrailsList').innerHTML = rules.length
      ? rules.map(r => {
          const en = r.enabled !== false;
          return `<div class="rule-card"><div class="rule-info"><h4>${esc(r.id)}</h4><p>${esc(r.message || r.type)}</p></div><span class="rule-type ${en ? 'rule-enabled' : 'rule-disabled'}">${r.type} ${en ? '✓' : '✗'}</span></div>`;
        }).join('')
      : '<p style="color:var(--text-dim)">No guardrail rules.</p>';
  } catch {}
}
