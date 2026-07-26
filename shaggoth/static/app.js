// Shaggoth AI Dashboard — app.js
function detectApi() {
    const saved = localStorage.getItem('shaggoth_api');
    if (saved) return saved.replace(/\/+$/, '');
    if (location.hostname === 'ai.vibecodes.space' || location.hostname.endsWith('.workers.dev')) {
        return location.origin + '/api';
    }
    return 'http://127.0.0.1:8420';
}

function getApiKey() {
    return localStorage.getItem('shaggoth_key') || '';
}

const API = detectApi();
let sessionId = 'web-' + Math.random().toString(36).slice(2, 10);

function apiHeaders() {
    const h = { 'Content-Type': 'application/json' };
    const key = getApiKey();
    if (key) h['Authorization'] = 'Bearer ' + key;
    return h;
}

// --- Navigation ---
document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        li.classList.add('active');
        document.getElementById('view-' + li.dataset.view).classList.add('active');
        const v = li.dataset.view;
        if (v === 'memory') loadMemory();
        if (v === 'guardrails') loadGuardrails();
        if (v === 'learn') loadLearnStatus();
        if (v === 'personality') loadPersonality();
        if (v === 'knowledge') loadKnowledgeList();
    });
});

// --- Settings ---
document.getElementById('apiUrl').value = API;
const savedKey = localStorage.getItem('shaggoth_key');
if (savedKey) document.getElementById('apiKey').value = savedKey;

function saveSettings() {
    const url = document.getElementById('apiUrl').value.replace(/\/+$/, '');
    const key = document.getElementById('apiKey').value;
    localStorage.setItem('shaggoth_api', url);
    localStorage.setItem('shaggoth_key', key);
    location.reload();
}

// --- Health ---
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
let useStreaming = true;

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage('user', text);
    chatInput.value = '';
    sendBtn.disabled = true;

    if (useStreaming && hasAuth()) {
        await sendStreamingMessage(text);
    } else {
        await sendJsonMessage(text);
    }

    sendBtn.disabled = false;
    chatInput.focus();
});

function hasAuth() {
    return !getApiKey(); // streaming works without auth currently; fallback to JSON
}

async function sendJsonMessage(text) {
    try {
        const r = await fetch(API + '/chat', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ message: text, session_id: sessionId }),
        });
        const d = await r.json();
        appendMessage('assistant', d.reply, d.source);
        document.getElementById('chatSource').textContent = d.source || '--';
    } catch (err) {
        appendMessage('assistant', `Error: ${err.message}`, 'error');
    }
}

async function sendStreamingMessage(text) {
    const msgDiv = appendMessage('assistant', '');
    const contentDiv = msgDiv.querySelector('.message-content');
    let buffer = '';

    try {
        const r = await fetch(API + '/chat/stream', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ message: text, session_id: sessionId }),
        });

        if (!r.ok) {
            contentDiv.textContent = `Error: ${r.status}`;
            return;
        }

        const reader = r.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.done) {
                            document.getElementById('chatSource').textContent = data.source || '--';
                        } else if (data.token) {
                            buffer += data.token;
                            contentDiv.textContent = buffer;
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        }
                    } catch {}
                }
            }
        }
    } catch (err) {
        contentDiv.textContent = `Error: ${err.message}`;
    }
}

function appendMessage(role, text, source) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    let html = `<div class="message-content">${escapeHtml(text)}</div>`;
    if (source) html += `<div class="message-source">${escapeHtml(source)}</div>`;
    div.innerHTML = html;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
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

// --- Personality ---
async function loadPersonality() {
    try {
        const r = await fetch(API + '/personality', { headers: apiHeaders() });
        const d = await r.json();
        const el = document.getElementById('personalityDisplay');
        el.innerHTML = `
            <div class="personality-section">
                <h3>Backstory</h3>
                <p>${escapeHtml(d.backstory || 'N/A')}</p>
            </div>
            <div class="personality-section">
                <h3>Traits</h3>
                <div class="trait-tags">${(d.traits || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
            </div>
            <div class="personality-section">
                <h3>Speaking Style</h3>
                <p>${escapeHtml(d.speaking_style || 'N/A')}</p>
            </div>
            <div class="personality-section">
                <h3>Interests</h3>
                <div class="trait-tags">${(d.interests || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
            </div>
            <div class="personality-section">
                <h3>Values</h3>
                <div class="trait-tags">${(d.values || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
            </div>
            <div class="personality-section">
                <h3>Mood</h3>
                <p>${escapeHtml(d.mood || 'N/A')}</p>
            </div>
        `;
    } catch {
        document.getElementById('personalityDisplay').innerHTML = '<p style="color:var(--red)">Could not connect to API.</p>';
    }
}

async function reloadPersonality() {
    await loadPersonality();
}

// --- Knowledge ---
async function loadKnowledgeList() {
    try {
        const r = await fetch(API + '/knowledge', { headers: apiHeaders() });
        const d = await r.json();
        const el = document.getElementById('knowledgeList');
        const entries = d.entries || [];
        if (entries.length === 0) {
            el.innerHTML = '<p style="color:var(--text-dim)">No knowledge entries yet. Add some above!</p>';
        } else {
            el.innerHTML = entries.map(e =>
                `<div class="knowledge-entry">
                    <div class="knowledge-topic">${escapeHtml(e.topic)}</div>
                    <div class="knowledge-meta">${e.word_count} words</div>
                </div>`
            ).join('');
        }
    } catch {
        document.getElementById('knowledgeList').innerHTML = '<p style="color:var(--red)">Could not connect to API.</p>';
    }
}

async function searchKnowledge() {
    const q = document.getElementById('knowledgeSearch').value.trim();
    if (!q) return;
    try {
        const r = await fetch(API + '/knowledge/query?q=' + encodeURIComponent(q), { headers: apiHeaders() });
        const d = await r.json();
        const el = document.getElementById('knowledgeList');
        const results = d.results || [];
        if (results.length === 0) {
            el.innerHTML = '<p style="color:var(--text-dim)">No relevant knowledge found.</p>';
        } else {
            el.innerHTML = results.map(r =>
                `<div class="knowledge-entry">
                    <div class="knowledge-topic">${escapeHtml(r.topic)} <span class="knowledge-score">${r.score}</span></div>
                    <div class="knowledge-content">${escapeHtml(r.content.slice(0, 300))}</div>
                </div>`
            ).join('');
        }
    } catch {}
}

async function addKnowledge() {
    const topic = document.getElementById('knowledgeTopic').value.trim();
    const content = document.getElementById('knowledgeContent').value.trim();
    if (!topic || !content) { alert('Topic and content required.'); return; }
    try {
        await fetch(API + '/knowledge/add', {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ topic, content }),
        });
        document.getElementById('knowledgeTopic').value = '';
        document.getElementById('knowledgeContent').value = '';
        loadKnowledgeList();
    } catch (err) {
        alert('Failed: ' + err.message);
    }
}

// --- Self-Learn ---
async function loadLearnStatus() {
    try {
        const r = await fetch(API + '/learn/status', { headers: apiHeaders() });
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

        const lr = await fetch(API + '/learn/history', { headers: apiHeaders() });
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
    } catch {}
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
            headers: apiHeaders(),
            body: JSON.stringify({ urls, crawl_depth: depth, max_pages: maxPages, training_steps: steps }),
        });
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
            const r = await fetch(API + '/learn/status', { headers: apiHeaders() });
            const d = await r.json();
            if (!d.is_learning) {
                clearInterval(iv);
                document.getElementById('learnBtn').disabled = false;
                document.getElementById('learnBtn').textContent = 'Start Learning';
                loadLearnStatus();
            }
        } catch {}
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
            fetch(API + '/facts', { headers: apiHeaders() }),
            fetch(API + '/history?session_id=' + sessionId, { headers: apiHeaders() }),
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
        const r = await fetch(API + '/guardrails', { headers: apiHeaders() });
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
