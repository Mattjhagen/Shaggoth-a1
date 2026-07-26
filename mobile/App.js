import React, { useEffect, useState, useCallback, useRef } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView,
  Platform, ActivityIndicator, Alert, ScrollView, Switch, StatusBar,
  SafeAreaView, AppState, Modal
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as api from './src/api/shaggoth'

// ---- Theme ----
const theme = {
  bg: '#212121',
  surface: '#171717',
  surface2: '#2a2a2a',
  border: '#3a3a3a',
  text: '#e0e0e0',
  dim: '#8a8a8a',
  accent: '#a78bfa',
  red: '#f87171',
  green: '#4ade80',
  msgUser: '#a78bfa',
  msgBot: '#2a2a2a',
}

const STORAGE_SESSION = 'shaggoth_session_id'
let _sessionId = ''

async function getSessionId() {
  if (!_sessionId) {
    _sessionId = (await AsyncStorage.getItem(STORAGE_SESSION)) || ''
  }
  if (!_sessionId) {
    _sessionId = 'mobile-' + Math.random().toString(36).slice(2, 10)
    await AsyncStorage.setItem(STORAGE_SESSION, _sessionId)
  }
  return _sessionId
}

async function resetSession() {
  _sessionId = 'mobile-' + Math.random().toString(36).slice(2, 10)
  await AsyncStorage.setItem(STORAGE_SESSION, _sessionId)
  return _sessionId
}

// ---- Main App ----
export default function App() {
  const [screen, setScreen] = useState('chat')
  const [connected, setConnected] = useState(false)
  const [version, setVersion] = useState('')

  useEffect(() => {
    api.initStorage().then(() => {
      api.health().then(d => { setConnected(true); setVersion(d.version) }).catch(() => {})
    })
  }, [])

  const screens = {
    chat: <ChatScreen key="chat" onNavigate={setScreen} connected={connected} version={version} />,
    settings: <SettingsScreen key="settings" onNavigate={setScreen} />,
    info: <InfoScreen key="info" onNavigate={setScreen} />,
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.bg }}>
      <StatusBar barStyle="light-content" backgroundColor={theme.bg} />
      {screens[screen] || screens.chat}
    </SafeAreaView>
  )
}

// ---- Chat Screen ----
function ChatScreen({ onNavigate, connected, version }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(true)
  const [sessionId, setSessionId] = useState('')
  const flatListRef = useRef(null)

  useEffect(() => { getSessionId().then(setSessionId) }, [])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const sid = await getSessionId()
    setSessionId(sid)

    const userMsg = { id: Date.now().toString(), role: 'user', text }
    setMessages(prev => [...prev, userMsg])

    if (!streaming) {
      setLoading(true)
      try {
        const d = await api.chat(text, sid)
        setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', text: d.reply, source: d.source, flag: d.flag }])
      } catch (err) {
        setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', text: 'Error: ' + err.message, source: 'error' }])
      }
      setLoading(false)
      return
    }

    // Streaming
    const botId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', source: 'streaming' }])
    setLoading(true)

    api.chatStream(text, sid,
      (token) => {
        setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: m.text + token } : m))
      },
      (meta) => {
        setMessages(prev => prev.map(m => m.id === botId ? { ...m, source: meta.source || 'model', flag: meta.flag } : m))
        setLoading(false)
      },
      (err) => {
        setMessages(prev => prev.map(m => m.id === botId ? { ...m, text: 'Error: ' + err, source: 'error' } : m))
        setLoading(false)
      }
    )
  }, [input, loading, streaming])

  const newChat = async () => {
    await resetSession()
    setMessages([])
    setSessionId('')
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <Text style={{ flex: 1, fontSize: 17, fontWeight: '700', color: connected ? theme.accent : theme.dim }}>
          Shaggoth {version ? `v${version}` : ''}
        </Text>
        <TouchableOpacity onPress={newChat} style={{ marginRight: 16 }}>
          <Text style={{ color: theme.accent, fontSize: 14 }}>New</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onNavigate('settings')} style={{ marginRight: 16 }}>
          <Text style={{ color: theme.dim, fontSize: 14 }}>Settings</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onNavigate('info')}>
          <Text style={{ color: theme.dim, fontSize: 14 }}>Info</Text>
        </TouchableOpacity>
      </View>

      {/* Messages */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={m => m.id}
        style={{ flex: 1, backgroundColor: theme.bg }}
        contentContainerStyle={{ paddingVertical: 16, paddingHorizontal: 16 }}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <MessageBubble message={item} />
        )}
        ListEmptyComponent={
          <View style={{ padding: 40, alignItems: 'center' }}>
            <Text style={{ color: theme.dim, fontSize: 15, textAlign: 'center', lineHeight: 22 }}>
              Connected to Shaggoth.{'\n'}Start a conversation.
            </Text>
          </View>
        }
      />

      {/* Input */}
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderTopWidth: 1, borderColor: theme.border, backgroundColor: theme.bg }}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Message Shaggoth..."
          placeholderTextColor={theme.dim}
          multiline
          style={{
            flex: 1, backgroundColor: theme.surface, color: theme.text,
            borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10,
            fontSize: 16, maxHeight: 100, borderWidth: 1, borderColor: theme.border, marginRight: 8
          }}
          onSubmitEditing={send}
          blurOnSubmit
        />
        <TouchableOpacity
          onPress={send}
          disabled={loading || !input.trim()}
          style={{
            width: 44, height: 44, borderRadius: 22, backgroundColor: theme.accent,
            alignItems: 'center', justifyContent: 'center', opacity: (loading || !input.trim()) ? 0.5 : 1
          }}
        >
          {loading ? (
            <ActivityIndicator size="small" color="#000" />
          ) : (
            <Text style={{ color: '#000', fontSize: 18, fontWeight: '700' }}>↑</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  )
}

// ---- Message Bubble ----
function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const tags = []
  if (message.source && message.source !== 'pattern' && message.source !== 'streaming' && message.source !== 'error') tags.push(message.source)
  if (message.flag && message.flag !== 'green') tags.push('🚩 ' + message.flag.toUpperCase())

  return (
    <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
      <View style={{
        maxWidth: '82%',
        backgroundColor: isUser ? theme.msgUser : theme.msgBot,
        borderRadius: 18,
        borderBottomRightRadius: isUser ? 4 : 18,
        borderBottomLeftRadius: isUser ? 18 : 4,
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderWidth: isUser ? 0 : 1,
        borderColor: theme.border,
      }}>
        <Text style={{ color: isUser ? '#000' : theme.text, fontSize: 16, lineHeight: 22 }}>
          {message.text || (message.source === 'streaming' ? '...' : '')}
        </Text>
      </View>
      {tags.length > 0 && (
        <Text style={{ color: theme.dim, fontSize: 11, marginTop: 3, marginHorizontal: 4 }}>{tags.join(' · ')}</Text>
      )}
    </View>
  )
}

// ---- Settings Screen ----
function SettingsScreen({ onNavigate }) {
  const [apiUrl, setApiUrl] = useState(api.getApiUrl())
  const [apiKey, setApiKey] = useState(api.getApiKey())
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await api.saveApiUrl(apiUrl)
    await api.saveApiKey(apiKey)
    Alert.alert('Saved', 'Settings saved. Restart the app to reconnect.')
    setSaving(false)
  }

  return (
    <View style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <TouchableOpacity onPress={() => onNavigate('chat')}>
          <Text style={{ color: theme.accent, fontSize: 16, marginRight: 16 }}>← Back</Text>
        </TouchableOpacity>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>Settings</Text>
      </View>

      <ScrollView style={{ flex: 1, padding: 16 }}>
        <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 6 }}>Shaggoth API URL</Text>
        <TextInput
          value={apiUrl}
          onChangeText={setApiUrl}
          style={{
            backgroundColor: theme.surface, color: theme.text, borderRadius: 12,
            paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
            borderWidth: 1, borderColor: theme.border, marginBottom: 20
          }}
          autoCapitalize="none"
          autoCorrect={false}
        />

        <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 6 }}>API Key (optional)</Text>
        <TextInput
          value={apiKey}
          onChangeText={setApiKey}
          secureTextEntry
          style={{
            backgroundColor: theme.surface, color: theme.text, borderRadius: 12,
            paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
            borderWidth: 1, borderColor: theme.border, marginBottom: 20
          }}
          autoCapitalize="none"
          autoCorrect={false}
        />

        <TouchableOpacity
          onPress={save}
          disabled={saving}
          style={{
            backgroundColor: theme.accent, borderRadius: 12, paddingVertical: 14,
            alignItems: 'center', opacity: saving ? 0.6 : 1
          }}
        >
          <Text style={{ color: '#000', fontSize: 16, fontWeight: '600' }}>{saving ? 'Saving...' : 'Save'}</Text>
        </TouchableOpacity>

        <View style={{ marginTop: 32, padding: 16, backgroundColor: theme.surface, borderRadius: 12, borderWidth: 1, borderColor: theme.border }}>
          <Text style={{ color: theme.dim, fontSize: 13, marginBottom: 4 }}>Connected to</Text>
          <Text style={{ color: theme.text, fontSize: 14 }}>{api.getApiUrl()}</Text>
        </View>
      </ScrollView>
    </View>
  )
}

// ---- Info Screen ----
function InfoScreen({ onNavigate }) {
  const [personality, setPersonality] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getPersonality().then(d => { setPersonality(d); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  return (
    <View style={{ flex: 1, backgroundColor: theme.bg }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderColor: theme.border, backgroundColor: theme.surface }}>
        <TouchableOpacity onPress={() => onNavigate('chat')}>
          <Text style={{ color: theme.accent, fontSize: 16, marginRight: 16 }}>← Back</Text>
        </TouchableOpacity>
        <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>About Shaggoth</Text>
      </View>

      <ScrollView style={{ flex: 1, padding: 16 }}>
        {loading ? (
          <ActivityIndicator size="large" color={theme.accent} style={{ marginTop: 40 }} />
        ) : personality ? (
          <>
            <Section title="Backstory" text={personality.backstory} />
            <Section title="Traits" tags={personality.traits} />
            <Section title="Speaking Style" text={personality.speaking_style} />
            <Section title="Interests" tags={personality.interests} />
            <Section title="Values" tags={personality.values} />
          </>
        ) : (
          <Text style={{ color: theme.dim, textAlign: 'center', marginTop: 40 }}>Could not load personality. Check connection.</Text>
        )}
      </ScrollView>
    </View>
  )
}

function Section({ title, text, tags }) {
  return (
    <View style={{ marginBottom: 20 }}>
      <Text style={{ color: theme.dim, fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>{title}</Text>
      {text && <Text style={{ color: theme.text, fontSize: 15, lineHeight: 22 }}>{text}</Text>}
      {tags && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {tags.map((t, i) => (
            <View key={i} style={{ backgroundColor: 'rgba(167,139,250,0.12)', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 4, borderWidth: 1, borderColor: 'rgba(167,139,250,0.2)' }}>
              <Text style={{ color: theme.accent, fontSize: 13 }}>{t}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
