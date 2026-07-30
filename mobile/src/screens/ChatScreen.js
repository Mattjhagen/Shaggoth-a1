import React, { useState, useCallback, useRef } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

async function getSessionId() {
  let sid = await AsyncStorage.getItem('shaggoth_session')
  if (!sid) {
    sid = 'mobile-' + Math.random().toString(36).slice(2, 10)
    await AsyncStorage.setItem('shaggoth_session', sid)
  }
  return sid
}

export default function ChatScreen({ onBack }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const flatRef = useRef(null)

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const sid = await getSessionId()

    const userMsg = { id: Date.now().toString(), role: 'user', text }
    setMessages(prev => [...prev, userMsg])

    const botId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', source: 'streaming' }])
    setLoading(true)

    api.chatStream(text, sid,
      token => setMessages(prev => prev.map(m =>
        m.id === botId ? { ...m, text: m.text + token } : m
      )),
      meta => {
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, source: meta.source, flag: meta.flag } : m
        ))
        setLoading(false)
      },
      err => {
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, text: 'Error: ' + err, source: 'error' } : m
        ))
        setLoading(false)
      }
    )
  }, [input, loading])

  const newChat = async () => {
    await AsyncStorage.removeItem('shaggoth_session')
    setMessages([])
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      <Header
        title="AI Chat"
        onBack={onBack}
        rightContent={
          <TouchableOpacity onPress={newChat} activeOpacity={0.7}>
            <View style={{
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.xs + 2,
              borderRadius: radius.full,
              backgroundColor: colors.primaryMuted,
              borderWidth: 1,
              borderColor: colors.primaryBorder,
            }}>
              <Text style={{ color: colors.primary, fontSize: fontSize.sm, fontWeight: '600' }}>
                New Chat
              </Text>
            </View>
          </TouchableOpacity>
        }
      />

      <FlatList
        ref={flatRef}
        data={messages}
        keyExtractor={m => m.id}
        style={{ flex: 1, backgroundColor: colors.background }}
        contentContainerStyle={{ paddingVertical: spacing.lg, paddingHorizontal: spacing.lg, flexGrow: 1 }}
        onContentSizeChange={() => flatRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <Text style={{ fontSize: 48, marginBottom: spacing.md }}>{'👽'}</Text>
            <Text style={{
              color: colors.textDim,
              fontSize: fontSize.lg,
              textAlign: 'center',
            }}>
              Open a channel to Shaggoth
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const isUser = item.role === 'user'
          const tags = []
          if (item.source && !['pattern', 'streaming', 'error'].includes(item.source))
            tags.push(item.source)
          if (item.flag && item.flag !== 'green')
            tags.push(item.flag.toUpperCase())

          return (
            <View style={{
              alignItems: isUser ? 'flex-end' : 'flex-start',
              marginBottom: spacing.md,
            }}>
              <View style={{
                maxWidth: '82%',
                backgroundColor: isUser ? colors.primary : colors.surfaceCard,
                borderRadius: radius.xl,
                borderBottomRightRadius: isUser ? radius.sm : radius.xl,
                borderBottomLeftRadius: isUser ? radius.xl : radius.sm,
                paddingHorizontal: spacing.lg,
                paddingVertical: spacing.md,
                borderWidth: isUser ? 0 : 1,
                borderColor: colors.border,
              }}>
                <Text style={{
                  color: isUser ? colors.white : colors.text,
                  fontSize: fontSize.lg,
                  lineHeight: 22,
                }}>
                  {item.text || (item.source === 'streaming' ? '...' : '')}
                </Text>
              </View>
              {tags.length > 0 && (
                <Text style={{
                  color: colors.textDim,
                  fontSize: fontSize.xs,
                  marginTop: spacing.xs,
                  marginHorizontal: spacing.xs,
                }}>
                  {tags.join(' · ')}
                </Text>
              )}
            </View>
          )
        }}
      />

      <View style={{
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        backgroundColor: colors.background,
        borderTopWidth: 1,
        borderColor: colors.border,
      }}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Type your message..."
          placeholderTextColor={colors.textDim}
          multiline
          style={{
            flex: 1,
            backgroundColor: colors.inputBg,
            color: colors.text,
            borderRadius: radius.xl,
            paddingHorizontal: spacing.lg,
            paddingVertical: spacing.md,
            fontSize: fontSize.lg,
            maxHeight: 100,
            borderWidth: 1,
            borderColor: colors.inputBorder,
            marginRight: spacing.sm,
          }}
          onSubmitEditing={send}
          blurOnSubmit
        />
        <TouchableOpacity
          onPress={send}
          disabled={loading || !input.trim()}
          activeOpacity={0.7}
          style={{
            width: 48,
            height: 48,
            borderRadius: 24,
            backgroundColor: colors.primary,
            alignItems: 'center',
            justifyContent: 'center',
            opacity: (loading || !input.trim()) ? 0.4 : 1,
            shadowColor: colors.primary,
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.4,
            shadowRadius: 6,
            elevation: 4,
          }}
        >
          {loading
            ? <ActivityIndicator size="small" color={colors.white} />
            : <Text style={{ color: colors.white, fontSize: 20, transform: [{ rotate: '45deg' }] }}>{'➤'}</Text>
          }
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  )
}
