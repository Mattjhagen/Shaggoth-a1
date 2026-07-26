import React, { useEffect, useState, useCallback, useRef } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView,
  Platform, ActivityIndicator, Alert, ScrollView, Modal, StatusBar,
  SafeAreaView, RefreshControl
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as api from './src/api/shaggoth'

const theme = {
  bg: '#212121', surface: '#171717', surface2: '#2a2a2a',
  border: '#3a3a3a', text: '#e0e0e0', dim: '#8a8a8a',
  accent: '#a78bfa', red: '#f87171', green: '#4ade80',
  msgUser: '#a78bfa', msgBot: '#2a2a2a',
}

async function getSessionId() {
  let sid = await AsyncStorage.getItem('shaggoth_session')
  if (!sid) { sid = 'mobile-' + Math.random().toString(36).slice(2,10); await AsyncStorage.setItem('shaggoth_session', sid) }
  return sid
}

// ---- Tabs ----
const TABS = [
  { key: 'chat', label: 'Chat', icon: '💬' },
  { key: 'knowledge', label: 'Knowledge', icon: '📚' },
  { key: 'learn', label: 'Learn', icon: '🧠' },
  { key: 'memory', label: 'Memory', icon: '📝' },
  { key: 'settings', label: 'Settings', icon: '⚙️' },
]

export default function App() {
  const [tab, setTab] = useState('chat')
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    api.initStorage()
    api.health().then(() => setConnected(true)).catch(() => {})
  }, [])

  const screens = {
    chat: <ChatScreen key="chat" />,
    knowledge: <KnowledgeScreen key="knowledge" />,
    learn: <LearnScreen key="learn" />,
    memory: <MemoryScreen key="memory" />,
    settings: <SettingsScreen key="settings" />,
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.bg }}>
      <StatusBar barStyle="light-content" backgroundColor={theme.bg} />
      <View style={{ flex: 1 }}>
        {screens[tab] || screens.chat}
      </View>
      <TabBar tab={tab} onTab={setTab} connected={connected} />
    </SafeAreaView>
  )
}

function TabBar({ tab, onTab, connected }) {
  return (
    <View style={{ flexDirection: 'row', borderTopWidth: 1, borderColor: theme.border, backgroundColor: theme.surface, paddingBottom: Platform.OS === 'ios' ? 20 : 8, paddingTop: 6 }}>
      {TABS.map(t => (
        <TouchableOpacity key={t.key} onPress={() => onTab(t.key)} style={{ flex: 1, alignItems: 'center', opacity: tab === t.key ? 1 : 0.4 }}>
          <Text style={{ fontSize: 20 }}>{t.icon}</Text>
          <Text style={{ fontSize: 10, color: tab === t.key ? theme.accent : theme.dim, marginTop: 2 }}>{t.label}</Text>
        </TouchableOpacity>
      ))}
      <View style={{ position: 'absolute', right: 12, top: 6 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? theme.green : theme.red }} />
      </View>
    </View>
  )
}

// ---- Chat Screen ----
function ChatScreen() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const flatRef = useRef(null)

  useEffect(() => { getSessionId().then(setSessionId) }, [])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const sid = await getSessionId()
    setSessionId(sid)

    const userMsg = { id: Date.now().toString(), role: 'user', text }
    setMessages(prev => [...prev, userMsg])

    const botId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', source: 'streaming' }])
    setLoading(true)

    api.chatStream(text, sid,
      token => setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: m.text + token } : m)),
      meta => { setMessages(prev => prev.map(m => m.id === botId ? { ...m, source: meta.source, flag: meta.flag } : m)); setLoading(false) },
      err => { setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: 'Error: ' + err, source: 'error' } : m)); setLoading(false) }
    )
  }, [input, loading])

  const newChat = async () => {
    await AsyncStorage.removeItem('shaggoth_session')
    setSessionId('')
    setMessages([])
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ flex: 1, fontSize: 17, fontWeight: '700', color: theme.text }}>Shaggoth</Text>
        <TouchableOpacity onPress={newChat}><Text style={{ color: theme.accent, fontSize: 14 }}>New Chat</Text></TouchableOpacity>
      </View>

      <FlatList
        ref={flatRef}
        data={messages}
        keyExtractor={m => m.id}
        style={{ flex: 1, backgroundColor: theme.bg }}
        contentContainerStyle={{ paddingVertical: 16, paddingHorizontal: 16 }}
        onContentSizeChange={() => flatRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={<View style={{ padding: 40, alignItems: 'center' }}><Text style={{ color: theme.dim, fontSize: 15, textAlign: 'center' }}>Connected to Shaggoth.{'\n'}Start a conversation.</Text></View>}
        renderItem={({ item }) => {
          const isUser = item.role === 'user'
          const tags = []
          if (item.source && !['pattern','streaming','error'].includes(item.source)) tags.push(item.source)
          if (item.flag && item.flag !== 'green') tags.push('🚩 ' + item.flag.toUpperCase())
          return (
            <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
              <View style={{ maxWidth: '82%', backgroundColor: isUser ? theme.msgUser : theme.msgBot, borderRadius: 18, borderBottomRightRadius: isUser ? 4 : 18, borderBottomLeftRadius: isUser ? 18 : 4, paddingHorizontal: 14, paddingVertical: 10, borderWidth: isUser ? 0 : 1, borderColor: theme.border }}>
                <Text style={{ color: isUser ? '#000' : theme.text, fontSize: 16, lineHeight: 22 }}>{item.text || (item.source === 'streaming' ? '...' : '')}</Text>
              </View>
              {tags.length > 0 && <Text style={{ color: theme.dim, fontSize: 11, marginTop: 3, marginHorizontal: 4 }}>{tags.join(' · ')}</Text>}
            </View>
          )
        }}
      />

      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, borderTopWidth: 1, borderColor: theme.border, backgroundColor: theme.bg }}>
        <TextInput value={input} onChangeText={setInput} placeholder="Message Shaggoth..." placeholderTextColor={theme.dim} multiline
          style={{ flex: 1, backgroundColor: theme.surface, color: theme.text, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, fontSize: 16, maxHeight: 100, borderWidth: 1, borderColor: theme.border, marginRight: 8 }}
          onSubmitEditing={send} blurOnSubmit
        />
        <TouchableOpacity onPress={send} disabled={loading || !input.trim()}
          style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: theme.accent, alignItems: 'center', justifyContent: 'center', opacity: (loading || !input.trim()) ? 0.5 : 1 }}>
          {loading ? <ActivityIndicator size="small" color="#000" /> : <Text style={{ color: '#000', fontSize: 18, fontWeight: '700' }}>↑</Text>}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  )
}

// ---- Knowledge Screen ----
function KnowledgeScreen() {
  const [entries, setEntries] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  const [newContent, setNewContent] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      if (query.trim()) {
        const d = await api.searchKnowledge(query)
        setEntries((d.results || []).map(r => ({ topic: r.topic, content: r.content, word_count: r.content.split(' ').length, score: r.score })))
      } else {
        const d = await api.getKnowledge()
        setEntries(d.entries || [])
      }
    } catch {} finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const add = async () => {
    if (!newTopic.trim() || !newContent.trim()) { Alert.alert('Error', 'Topic and content required'); return }
    try {
      await fetch(api.getApiUrl() + '/knowledge/add', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(api.getApiKey() ? { 'Authorization': 'Bearer ' + api.getApiKey() } : {}) }, body: JSON.stringify({ topic: newTopic, content: newContent }) })
      setShowAdd(false); setNewTopic(''); setNewContent(''); load()
    } catch (e) { Alert.alert('Error', e.message) }
  }

  return (
    <View style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ padding: 16, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text, marginBottom: 8 }}>Knowledge</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={query} onChangeText={setQuery} placeholder="Search..." placeholderTextColor={theme.dim}
            onSubmitEditing={load} style={{ flex: 1, backgroundColor: theme.bg, color: theme.text, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, fontSize: 14, borderWidth: 1, borderColor: theme.border }}
          />
          <TouchableOpacity onPress={load} style={{ backgroundColor: theme.accent, borderRadius: 10, paddingHorizontal: 16, justifyContent: 'center' }}><Text style={{ color: '#000', fontWeight: '600' }}>Go</Text></TouchableOpacity>
          <TouchableOpacity onPress={() => setShowAdd(true)} style={{ backgroundColor: theme.surface2, borderRadius: 10, paddingHorizontal: 12, justifyContent: 'center', borderWidth: 1, borderColor: theme.border }}><Text style={{ color: theme.accent, fontWeight: '600' }}>+</Text></TouchableOpacity>
        </View>
      </View>

      {loading ? <ActivityIndicator size="large" color={theme.accent} style={{ marginTop: 40 }} /> : (
        <FlatList data={entries} keyExtractor={(_, i) => String(i)} style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}
          ListEmptyComponent={<Text style={{ color: theme.dim, textAlign: 'center', marginTop: 40 }}>No entries</Text>}
          renderItem={({ item }) => (
            <View style={{ backgroundColor: theme.surface, borderRadius: 12, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: theme.border }}>
              <Text style={{ color: theme.accent, fontWeight: '600', fontSize: 15, marginBottom: 4 }}>{item.topic} {item.score ? <Text style={{ color: theme.dim, fontSize: 12 }}>({item.score})</Text> : null}</Text>
              <Text style={{ color: theme.dim, fontSize: 13, lineHeight: 18 }} numberOfLines={item.score ? 6 : 2}>{item.content || `${item.word_count} words`}</Text>
            </View>
          )}
        />
      )}

      <Modal visible={showAdd} transparent animationType="fade">
        <View style={{ flex: 1, justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.7)', padding: 24 }}>
          <View style={{ backgroundColor: theme.surface, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: theme.border }}>
            <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text, marginBottom: 12 }}>Add Knowledge</Text>
            <TextInput value={newTopic} onChangeText={setNewTopic} placeholder="Topic" placeholderTextColor={theme.dim}
              style={{ backgroundColor: theme.bg, color: theme.text, borderRadius: 10, padding: 12, fontSize: 15, borderWidth: 1, borderColor: theme.border, marginBottom: 12 }}
            />
            <TextInput value={newContent} onChangeText={setNewContent} placeholder="Content" placeholderTextColor={theme.dim} multiline
              style={{ backgroundColor: theme.bg, color: theme.text, borderRadius: 10, padding: 12, fontSize: 15, borderWidth: 1, borderColor: theme.border, marginBottom: 16, minHeight: 100 }}
            />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={() => setShowAdd(false)} style={{ flex: 1, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: theme.border, alignItems: 'center' }}><Text style={{ color: theme.dim }}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity onPress={add} style={{ flex: 1, padding: 12, borderRadius: 10, backgroundColor: theme.accent, alignItems: 'center' }}><Text style={{ color: '#000', fontWeight: '600' }}>Save</Text></TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  )
}

// ---- Learn Screen ----
function LearnScreen() {
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [urls, setUrls] = useState('')
  const [loading, setLoading] = useState(true)
  const [learning, setLearning] = useState(false)

  const load = async () => {
    try {
      const [s, h] = await Promise.all([api.getLearnStatus(), fetch(api.getApiUrl() + '/learn/history', { headers: { ...(api.getApiKey() ? { 'Authorization': 'Bearer ' + api.getApiKey() } : {}) } }).then(r => r.json())])
      setStatus(s); setHistory(h.sessions || []); setLearning(s.is_learning)
    } catch {} finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const start = async () => {
    const seeds = urls.split('\n').map(u => u.trim()).filter(Boolean)
    if (!seeds.length) { Alert.alert('Error', 'Enter at least one URL'); return }
    setLearning(true)
    try {
      await api.startLearning(seeds, 1, 20, 500)
      const iv = setInterval(async () => {
        const s = await api.getLearnStatus()
        if (!s.is_learning) { clearInterval(iv); setLearning(false); load() }
      }, 3000)
    } catch { setLearning(false) }
  }

  return (
    <View style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ padding: 16, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>Self-Learn</Text>
      </View>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
        {status && (
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
            {[{ l: 'Pages', v: status.scraper_stats?.pages_stored || 0 }, { l: 'Words', v: fmt(status.scraper_stats?.total_words || 0) }, { l: 'Model', v: status.model_exists ? 'Yes' : 'No' }, { l: 'Sessions', v: status.total_sessions || 0 }].map(s => (
              <View key={s.l} style={{ flex: 1, backgroundColor: theme.surface, borderRadius: 12, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: theme.border }}>
                <Text style={{ fontSize: 20, fontWeight: '700', color: theme.accent }}>{s.v}</Text>
                <Text style={{ fontSize: 10, color: theme.dim, textTransform: 'uppercase' }}>{s.l}</Text>
              </View>
            ))}
          </View>
        )}
        <TextInput value={urls} onChangeText={setUrls} placeholder="Seed URLs (one per line)" placeholderTextColor={theme.dim} multiline
          style={{ backgroundColor: theme.surface, color: theme.text, borderRadius: 12, padding: 12, fontSize: 14, borderWidth: 1, borderColor: theme.border, minHeight: 100, marginBottom: 12 }}
        />
        <TouchableOpacity onPress={start} disabled={learning}
          style={{ backgroundColor: theme.accent, borderRadius: 12, padding: 14, alignItems: 'center', opacity: learning ? 0.5 : 1, marginBottom: 20 }}>
          <Text style={{ color: '#000', fontSize: 15, fontWeight: '600' }}>{learning ? 'Learning...' : 'Start Learning'}</Text>
        </TouchableOpacity>

        <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 8 }}>History</Text>
        {history.length === 0 ? <Text style={{ color: theme.dim }}>No sessions yet.</Text> : history.reverse().map((s, i) => (
          <View key={i} style={{ backgroundColor: theme.surface, borderRadius: 8, padding: 10, marginBottom: 6, borderWidth: 1, borderColor: theme.border }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: s.status === 'completed' ? theme.green : s.status === 'failed' ? theme.red : theme.accent, fontSize: 12, fontWeight: '600' }}>{s.status.toUpperCase()}</Text>
              <Text style={{ color: theme.dim, fontSize: 11 }}>{s.pages_scraped}p · {fmt(s.words_learned)}w</Text>
            </View>
            {s.error && <Text style={{ color: theme.red, fontSize: 11, marginTop: 4 }}>{s.error}</Text>}
          </View>
        ))}
      </ScrollView>
    </View>
  )
}

// ---- Memory Screen ----
function MemoryScreen() {
  const [facts, setFacts] = useState({})
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const [fd, hd] = await Promise.all([api.getFacts(), api.getHistory(await getSessionId())])
        setFacts(fd.facts || {}); setHistory(hd.messages || [])
      } catch {} finally { setLoading(false) }
    })()
  }, [])

  return (
    <View style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ padding: 16, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>Memory</Text>
      </View>
      {loading ? <ActivityIndicator size="large" color={theme.accent} style={{ marginTop: 40 }} /> : (
        <FlatList data={[]} style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}
          ListHeaderComponent={
            <>
              <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Facts</Text>
              {Object.keys(facts).length === 0 ? <Text style={{ color: theme.dim, marginBottom: 20 }}>No facts stored.</Text> : Object.entries(facts).map(([k, v]) => (
                <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', backgroundColor: theme.surface, borderRadius: 8, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: theme.border }}>
                  <Text style={{ color: theme.accent, fontWeight: '600' }}>{k}</Text>
                  <Text style={{ color: theme.text }}>{v}</Text>
                </View>
              ))}
              <Text style={{ color: theme.dim, fontSize: 13, marginVertical: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Recent</Text>
              {history.length === 0 ? <Text style={{ color: theme.dim }}>No messages yet.</Text> : history.slice(-20).map(m => (
                <View key={m.id} style={{ backgroundColor: theme.surface, borderRadius: 8, padding: 10, marginBottom: 6, borderWidth: 1, borderColor: theme.border }}>
                  <Text style={{ fontSize: 10, color: m.role === 'assistant' ? theme.accent : theme.dim, textTransform: 'uppercase', marginBottom: 4 }}>{m.role}</Text>
                  <Text style={{ color: theme.text, fontSize: 14 }}>{m.content}</Text>
                </View>
              ))}
            </>
          }
        />
      )}
    </View>
  )
}

// ---- Settings Screen ----
function SettingsScreen() {
  const [apiUrl, setApiUrl] = useState(api.getApiUrl())
  const [apiKey, setApiKey] = useState(api.getApiKey())
  const [guardrails, setGuardrails] = useState([])
  const [personality, setPersonality] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getGuardrails().then(d => setGuardrails(d.rules || [])).catch(() => {})
    api.getPersonality().then(setPersonality).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    await api.saveApiUrl(apiUrl)
    await api.saveApiKey(apiKey)
    Alert.alert('Saved', 'Reconnect to apply.')
    setSaving(false)
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ padding: 16, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>Settings</Text>
      </View>
      <View style={{ padding: 16 }}>
        <Text style={{ color: theme.dim, fontSize: 12, marginBottom: 4 }}>API URL</Text>
        <TextInput value={apiUrl} onChangeText={setApiUrl} style={{ backgroundColor: theme.surface, color: theme.text, borderRadius: 10, padding: 12, fontSize: 15, borderWidth: 1, borderColor: theme.border, marginBottom: 16 }} autoCapitalize="none" />
        <Text style={{ color: theme.dim, fontSize: 12, marginBottom: 4 }}>API Key</Text>
        <TextInput value={apiKey} onChangeText={setApiKey} secureTextEntry style={{ backgroundColor: theme.surface, color: theme.text, borderRadius: 10, padding: 12, fontSize: 15, borderWidth: 1, borderColor: theme.border, marginBottom: 16 }} autoCapitalize="none" />
        <TouchableOpacity onPress={save} disabled={saving} style={{ backgroundColor: theme.accent, borderRadius: 10, padding: 14, alignItems: 'center', marginBottom: 24, opacity: saving ? 0.6 : 1 }}><Text style={{ color: '#000', fontSize: 15, fontWeight: '600' }}>{saving ? 'Saving...' : 'Save'}</Text></TouchableOpacity>

        <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Guardrails</Text>
        {guardrails.length === 0 ? <Text style={{ color: theme.dim, marginBottom: 16 }}>No guardrail rules.</Text> : guardrails.map(r => (
          <View key={r.id} style={{ backgroundColor: theme.surface, borderRadius: 8, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: theme.border }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: theme.text, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 13 }}>{r.id}</Text>
              <Text style={{ color: r.enabled !== false ? theme.green : theme.red, fontSize: 12 }}>{r.type} {r.enabled !== false ? '✓' : '✗'}</Text>
            </View>
            {r.message && <Text style={{ color: theme.dim, fontSize: 12, marginTop: 4 }}>{r.message}</Text>}
          </View>
        ))}

        {personality && (
          <>
            <Text style={{ color: theme.dim, fontSize: 13, marginVertical: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Personality</Text>
            <View style={{ backgroundColor: theme.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: theme.border }}>
              <Text style={{ color: theme.text, fontSize: 14, lineHeight: 20 }}>{personality.backstory}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                {(personality.traits || []).map((t, i) => <View key={i} style={{ backgroundColor: 'rgba(167,139,250,0.12)', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: 'rgba(167,139,250,0.2)' }}><Text style={{ color: theme.accent, fontSize: 12 }}>{t}</Text></View>)}
              </View>
            </View>
          </>
        )}
      </View>
    </ScrollView>
  )
}

function fmt(n) { if (n >= 1e6) return (n/1e6).toFixed(1)+'M'; if (n >= 1e3) return (n/1e3).toFixed(1)+'K'; return String(n) }
