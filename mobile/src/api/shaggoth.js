const API_URL = 'https://shaggoth.relayapp.pro'

let _apiKey = ''

export async function initStorage() {
  try {
    const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default
    const key = await AsyncStorage.getItem('shaggoth_api_token')
    if (key) _apiKey = key
  } catch {}
}

export async function saveApiKey(key) {
  _apiKey = key
  try {
    const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default
    await AsyncStorage.setItem('shaggoth_api_token', key)
  } catch {}
}

export function getApiUrl() { return API_URL }
export function getApiKey() { return _apiKey }

function headers() {
  const h = { 'Content-Type': 'application/json' }
  if (_apiKey) h['Authorization'] = 'Bearer ' + _apiKey
  return h
}

async function fetchJson(path, options = {}) {
  const url = `${API_URL}${path}`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const res = await fetch(url, {
      ...options,
      headers: { ...headers(), ...options.headers },
      signal: controller.signal,
    })
    if (!res.ok) {
      const body = await res.text()
      throw new Error(body || `HTTP ${res.status}`)
    }
    return res.json()
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(`Connection timed out — is Shaggoth running at ${API_URL}?`)
    }
    if (err.message?.includes('Network request failed')) {
      throw new Error(`Can't reach Shaggoth at ${API_URL} — check your network connection.`)
    }
    throw err
  } finally {
    clearTimeout(timeout)
  }
}

export async function health() {
  return fetchJson('/health')
}

export async function chat(message, sessionId) {
  return fetchJson('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId }),
  })
}

export async function chatStream(message, sessionId, onToken, onDone, onError) {
  try {
    const data = await chat(message, sessionId)
    const reply = data.reply || data.response || ''
    if (reply) {
      const words = reply.split(/(?<=\s)/)
      for (let i = 0; i < words.length; i++) {
        onToken(words[i])
        await new Promise(r => setTimeout(r, 20))
      }
    } else {
      onToken('No response from Shaggoth.')
    }
    onDone(data)
  } catch (err) {
    onError(err.message)
  }
}

export async function getHistory(sessionId) {
  return fetchJson(`/history?session_id=${encodeURIComponent(sessionId)}`)
}

export async function getFacts() {
  return fetchJson('/facts')
}

export async function getPersonality() {
  return fetchJson('/personality')
}

export async function getGuardrails() {
  return fetchJson('/guardrails')
}

export async function getLearnStatus() {
  return fetchJson('/learn/status')
}

export async function startLearning(urls, depth, maxPages, steps) {
  return fetchJson('/learn/start', {
    method: 'POST',
    body: JSON.stringify({ urls, crawl_depth: depth, max_pages: maxPages, training_steps: steps }),
  })
}

export async function getKnowledge() {
  return fetchJson('/knowledge')
}

export async function searchKnowledge(query) {
  return fetchJson(`/knowledge/query?q=${encodeURIComponent(query)}`)
}

export async function registerPushToken(token, platform) {
  return fetchJson('/push/register', {
    method: 'POST',
    body: JSON.stringify({ token, platform }),
  })
}

export async function sendFeedback({ question, verdict, note, answer, source, entries_used, reasoning, session_id }) {
  return fetchJson('/feedback', {
    method: 'POST',
    body: JSON.stringify({ question, verdict, note, answer, source, entries_used, reasoning, session_id }),
  })
}

export async function getCuriosityStatus() {
  return fetchJson('/curiosity/status')
}

export async function getCuriosityHistory() {
  return fetchJson('/curiosity/history')
}

export async function triggerCuriosityResearch(topic) {
  return fetchJson('/curiosity/research', {
    method: 'POST',
    body: JSON.stringify({ topic }),
  })
}

export async function triggerCuriosityScheduler() {
  return fetchJson('/curiosity/scheduler/trigger', {
    method: 'POST',
  })
}

export async function getLearnHistory() {
  return fetchJson('/learn/history')
}

export async function getCriticStatus() {
  return fetchJson('/critic')
}

export async function addKnowledge(topic, content) {
  return fetchJson('/knowledge/add', {
    method: 'POST',
    body: JSON.stringify({ topic, content }),
  })
}

export async function getLearnSessions() {
  return fetchJson('/learn/history')
}

