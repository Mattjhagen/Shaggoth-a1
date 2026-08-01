import React, { useState, useCallback, useRef, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator, Animated,
  Keyboard,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import useVoice from '../hooks/useVoice'
import * as api from '../api/shaggoth'

async function getSessionId() {
  let sid = await AsyncStorage.getItem('shaggoth_session')
  if (!sid) {
    sid = 'mobile-' + Math.random().toString(36).slice(2, 10)
    await AsyncStorage.setItem('shaggoth_session', sid)
  }
  return sid
}

function MicButton({ listening, onPress, available }) {
  const pulseAnim = useRef(new Animated.Value(1)).current

  useEffect(() => {
    if (listening) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.25, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start()
    } else {
      pulseAnim.stopAnimation()
      pulseAnim.setValue(1)
    }
  }, [listening, pulseAnim])

  if (!available) return null

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7}>
      <Animated.View style={{
        width: 48,
        height: 48,
        borderRadius: 24,
        backgroundColor: listening ? colors.red : colors.surfaceCard,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: listening ? colors.red : colors.border,
        marginRight: spacing.sm,
        transform: [{ scale: pulseAnim }],
      }}>
        <Text style={{ fontSize: 20 }}>{listening ? '⏹' : '🎙'}</Text>
      </Animated.View>
    </TouchableOpacity>
  )
}

function SpeakerButton({ speaking, onPress }) {
  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7} style={{ marginLeft: spacing.xs }}>
      <View style={{
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.xs,
        borderRadius: radius.sm,
        backgroundColor: speaking ? colors.primaryMuted : 'transparent',
      }}>
        <Text style={{ fontSize: 14, color: speaking ? colors.primary : colors.textDim }}>
          {speaking ? '🔊' : '🔈'}
        </Text>
      </View>
    </TouchableOpacity>
  )
}

export default function ChatScreen({ onBack, assistMode }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(false)
  const [keyboardHeight, setKeyboardHeight] = useState(0)
  const flatRef = useRef(null)
  const voice = useVoice()

  useEffect(() => {
    if (Platform.OS !== 'android') return
    const showSub = Keyboard.addListener('keyboardDidShow', (e) => {
      setKeyboardHeight(e.endCoordinates.height)
    })
    const hideSub = Keyboard.addListener('keyboardDidHide', () => {
      setKeyboardHeight(0)
    })
    return () => { showSub.remove(); hideSub.remove() }
  }, [])

  useEffect(() => {
    if (assistMode && voice.available) {
      voice.startListening((text) => {
        if (text) {
          setInput(text)
          setTimeout(() => sendWithText(text), 300)
        }
      })
    }
  }, [assistMode, voice.available])

  const sendWithText = useCallback(async (text) => {
    if (!text?.trim() || loading) return
    setInput('')
    const sid = await getSessionId()

    const userMsg = { id: Date.now().toString(), role: 'user', text: text.trim() }
    setMessages(prev => [...prev, userMsg])

    const botId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', source: 'streaming' }])
    setLoading(true)

    let fullReply = ''
    api.chatStream(text.trim(), sid,
      token => {
        fullReply += token
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, text: m.text + token } : m
        ))
      },
      meta => {
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, source: meta.source, flag: meta.flag } : m
        ))
        setLoading(false)
        if (autoSpeak && fullReply) voice.speak(fullReply)
      },
      err => {
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, text: 'Error: ' + err, source: 'error' } : m
        ))
        setLoading(false)
      }
    )
  }, [loading, autoSpeak, voice])

  const send = useCallback(() => sendWithText(input), [input, sendWithText])

  const handleMicPress = useCallback(() => {
    if (voice.listening) {
      voice.stopListening()
    } else {
      voice.startListening((text) => {
        if (text) setInput(text)
      })
    }
  }, [voice])

  const newChat = async () => {
    await AsyncStorage.removeItem('shaggoth_session')
    setMessages([])
    voice.stopSpeaking()
  }

  const Wrapper = Platform.OS === 'ios' ? KeyboardAvoidingView : View
  const wrapperProps = Platform.OS === 'ios'
    ? { style: { flex: 1, backgroundColor: colors.background }, behavior: 'padding', keyboardVerticalOffset: 44 }
    : { style: { flex: 1, backgroundColor: colors.background, paddingBottom: keyboardHeight } }

  return (
    <Wrapper {...wrapperProps}>
      <Header
        title="Comms"
        onBack={onBack}
        rightContent={
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <TouchableOpacity
              onPress={() => setAutoSpeak(v => !v)}
              activeOpacity={0.7}
              style={{
                paddingHorizontal: spacing.md,
                paddingVertical: spacing.xs + 2,
                borderRadius: radius.full,
                backgroundColor: autoSpeak ? colors.primaryMuted : colors.surfaceCard,
                borderWidth: 1,
                borderColor: autoSpeak ? colors.primaryBorder : colors.border,
                marginRight: spacing.sm,
              }}
            >
              <Text style={{
                color: autoSpeak ? colors.primary : colors.textDim,
                fontSize: fontSize.sm,
                fontWeight: '600',
              }}>
                {autoSpeak ? '🔊 Voice' : '🔇 Mute'}
              </Text>
            </TouchableOpacity>
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
          </View>
        }
      />

      {voice.listening && voice.transcript ? (
        <View style={{
          backgroundColor: colors.surfaceCard,
          borderBottomWidth: 1,
          borderColor: colors.border,
          paddingHorizontal: spacing.lg,
          paddingVertical: spacing.md,
          flexDirection: 'row',
          alignItems: 'center',
        }}>
          <View style={{
            width: 8, height: 8, borderRadius: 4,
            backgroundColor: colors.red, marginRight: spacing.md,
          }} />
          <Text style={{ color: colors.textSecondary, fontSize: fontSize.md, flex: 1 }}
            numberOfLines={2}>
            {voice.transcript}
          </Text>
        </View>
      ) : null}

      <FlatList
        ref={flatRef}
        data={messages}
        keyExtractor={m => m.id}
        keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'none'}
        keyboardShouldPersistTaps="handled"
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
            {voice.available && (
              <Text style={{
                color: colors.textDim,
                fontSize: fontSize.sm,
                textAlign: 'center',
                marginTop: spacing.sm,
              }}>
                Tap the mic to speak
              </Text>
            )}
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
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
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
                {!isUser && item.text && item.source !== 'streaming' && (
                  <SpeakerButton
                    speaking={voice.speaking}
                    onPress={() => voice.speaking ? voice.stopSpeaking() : voice.speak(item.text)}
                  />
                )}
              </View>
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
        <MicButton
          listening={voice.listening}
          onPress={handleMicPress}
          available={voice.available}
        />
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
          blurOnSubmit={false}
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
    </Wrapper>
  )
}
