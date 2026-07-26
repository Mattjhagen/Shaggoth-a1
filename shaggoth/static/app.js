// Shaggoth AI Dashboard — app.js
// Auto-detect: if on Cloudflare (ai.vibecodes.space), use /api/ proxy.
// Otherwise default to localhost:8420.
function detectApi() {
    const saved = localStorage.getItem('shaggoth_api');
    if (saved) return saved;
    if (location.hostname === 'ai.vibecodes.space' || location.hostname.endsWith('.workers.dev')) {
        return location.origin + '/api';
    }
    return 'http://127.0.0.1:8420';
}
const API = detectApi();
let sessionId = 'web-' + Math.random().toString(36).slice(2, 10);

// --- Navigation ---
document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        li.classList.add('active');
        document.getElementById('view-' + li.dataset.view).classList.add('active');
        if (li.dataset.view === 'memory') loadMemory();
        if (li.dataset.view === 'guardrails') loadGuardrails();
        if (li.dataset.view === 'learn') loadLearnStatus();
    });
});

// --- Settings ---
document.getElementById('apiUrl').value = API;
function saveSettings() {
    const url = document.getElementById('apiUrl').value.replace(/\/+$/, '');
    localStorage.setItem('shaggoth_api', url);
    location.reload();
}

// --- Health check ---
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

// --- Chat ---
const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage('user', text);
    chatInput.value = '';
    sendBtn.disabled = true;

    try {
        const r = await fetch(API + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: sessionId }),
        });
        const d = await r.json();
        appendMessage('assistant', d.reply, d.source);
        document.getElementById('chatSource').textContent = d.source || '--';
    } catch (err) {
        appendMessage('assistant', `Error: ${err.message}`, 'error');
    } finally {
        sendBtn.disabled = false;
        chatInput.focus();
    }
});

function appendMessage(role, text, source) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    let html = `<div class="message-content">${escapeHtml(text)}</div>`;
    if (source) html += `<div class="message-source">${escapeHtml(source)}</div>`;
    div.innerHTML = html;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearChat() {
    sessionId = 'web-' + Math.random().toString(36).slice(2, 10);
    chatMessages.innerHTML = '';
    appendMessage('assistant', 'New session started. Hello again!');
}

function escapeHtml(t) {
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

// --- Self-Learn ---
async function loadLearnStatus() {
    try {
        const r = await fetch(API + '/learn/status');
        const d = await r.json();
        document.getElementById('statPages').textContent = d.scraper_stats?.pages_stored || 0;
        document.getElementById('statWords').textContent = formatNum(d.scraper_stats?.total_words || 0);
        document.getElementById('statModel').textContent = d.model_exists ? 'Yes' : 'No';
        document.getElementById('statSessions').textContent = d.total_sessions || 0;

        if (d.current_session) {
            document.getElementById('learnBtn').disabled = true;
            document.getElementById('learnBtn').textContent = 'Learning...';
        } else {
            document.getElementById('learnBtn').disabled = false;
            document.getElementById('learnBtn').textContent = 'Start Learning';
        }

        // Load history
        const lr = await fetch(API + '/learn/history');
        const ld = await lr.json();
        const logEl = document.getElementById('learnLogEntries');
        if (!ld.sessions || ld.sessions.length === 0) {
            logEl.innerHTML = 'No learning sessions yet.';
        } else {
            logEl.innerHTML = ld.sessions.reverse().map(s => {
                const cls = s.status === 'completed' ? 'ok' : s.status === 'failed' ? 'err' : '';
                const dur = s.ended_at ? Math.round(s.ended_at - s.started_at) : '?';
                return `<div class="log-entry"><span class="${cls}">[${s.status}]</span> ${s.session_id} — ${s.pages_scraped} pages, ${formatNum(s.words_learned)} words, ${dur}s</div>`;
            }).join('');
        }
    } catch {
        // API not reachable
    }
}

async function startLearning() {
    const urls = document.getElementById('seedUrls').value.split('\n').map(u => u.trim()).filter(Boolean);
    const depth = parseInt(document.getElementById('crawlDepth').value) || 1;
    const maxPages = parseInt(document.getElementById('maxPages').value) || 20;
    const steps = parseInt(document.getElementById('trainSteps').value) || 1000;

    document.getElementById('learnBtn').disabled = true;
    document.getElementById('learnBtn').textContent = 'Learning...';

    try {
        await fetch(API + '/learn/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls, crawl_depth: depth, max_pages: maxPages, training_steps: steps }),
        });
        // Poll for completion
        pollLearnStatus();
    } catch (err) {
        alert('Failed to start learning: ' + err.message);
        document.getElementById('learnBtn').disabled = false;
        document.getElementById('learnBtn').textContent = 'Start Learning';
    }
}

function pollLearnStatus() {
    const iv = setInterval(async () => {
        try {
            const r = await fetch(API + '/learn/status');
            const d = await r.json();
            if (!d.is_learning) {
                clearInterval(iv);
                document.getElementById('learnBtn').disabled = false;
                document.getElementById('learnBtn').textContent = 'Start Learning';
                loadLearnStatus();
            }
        } catch { /* retry */ }
    }, 3000);
}

function formatNum(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
}

// --- Memory ---
async function loadMemory() {
    try {
        const [fr, hr] = await Promise.all([
            fetch(API + '/facts'),
            fetch(API + '/history?session_id=' + sessionId),
        ]);
        const fd = await fr.json();
        const hd = await hr.json();

        const factsEl = document.getElementById('factsList');
        const facts = fd.facts || {};
        if (Object.keys(facts).length === 0) {
            factsEl.innerHTML = '<p style="color:var(--text-dim)">No facts stored yet. Tell me things like "my name is Matt" in chat.</p>';
        } else {
            factsEl.innerHTML = Object.entries(facts).map(([k, v]) =>
                `<div class="fact-row"><span class="fact-key">${escapeHtml(k)}</span><span class="fact-val">${escapeHtml(v)}</span></div>`
            ).join('');
        }

        const histEl = document.getElementById('historyList');
        const msgs = hd.messages || [];
        if (msgs.length === 0) {
            histEl.innerHTML = '<p style="color:var(--text-dim)">No messages in this session yet.</p>';
        } else {
            histEl.innerHTML = msgs.slice(-20).map(m =>
                `<div class="history-entry"><div class="history-role ${m.role}">${m.role}</div><div>${escapeHtml(m.content)}</div></div>`
            ).join('');
        }
    } catch {
        document.getElementById('factsList').innerHTML = '<p style="color:var(--red)">Could not connect to API.</p>';
    }
}

// --- Guardrails ---
async function loadGuardrails() {
    try {
        const r = await fetch(API + '/guardrails');
        const d = await r.json();
        const el = document.getElementById('guardrailsList');
        const rules = d.rules || [];
        if (rules.length === 0) {
            el.innerHTML = '<p style="color:var(--text-dim)">No guardrail rules.</p>';
        } else {
            el.innerHTML = rules.map(r => {
                const enabled = r.enabled !== false;
                return `<div class="rule-card">
                    <div class="rule-info">
                        <h4>${escapeHtml(r.id)}</h4>
                        <p>${escapeHtml(r.message || r.action || '')}</p>
                    </div>
                    <span class="rule-type ${enabled ? 'rule-enabled' : 'rule-disabled'}">${r.type} ${enabled ? '&#10003;' : '&#10007;'}</span>
                </div>`;
            }).join('');
        }
    } catch {
        document.getElementById('guardrailsList').innerHTML = '<p style="color:var(--red)">Could not connect to API.</p>';
    }
}
