import React, { useState, useCallback, useRef, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator, Animated,
  Keyboard, Modal,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import useVoice from '../hooks/useVoice'
import * as api from '../api/shaggoth'

const SOURCE_LABELS = {
  knowledge: 'Knowledge Base',
  model: 'AI Model',
  reasoning: 'Multi-step Reasoning',
  pattern: 'Pattern Match',
  guardrail: 'Guardrail',
  plugin: 'Plugin',
  fallback: 'Fallback',
}

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
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: listening ? colors.red : colors.surfaceCard,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: listening ? colors.red : colors.border,
        marginRight: spacing.sm,
        transform: [{ scale: pulseAnim }],
      }}>
        <Text style={{ fontSize: 18 }}>{listening ? '⏹' : '🎙'}</Text>
      </Animated.View>
    </TouchableOpacity>
  )
}

function FeedbackBar({ item, onFeedback }) {
  if (!item.text || item.source === 'streaming' || item.source === 'error') return null

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: spacing.xs }}>
      <TouchableOpacity
        onPress={() => onFeedback(item, 'good')}
        activeOpacity={0.7}
        style={{
          paddingHorizontal: spacing.sm,
          paddingVertical: spacing.xs,
          borderRadius: radius.sm,
          backgroundColor: item.verdict === 'good' ? colors.green + '25' : 'transparent',
        }}
      >
        <Text style={{
          fontSize: 14,
          opacity: item.verdict === 'bad' ? 0.3 : 1,
        }}>{'👍'}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        onPress={() => onFeedback(item, 'bad')}
        activeOpacity={0.7}
        style={{
          paddingHorizontal: spacing.sm,
          paddingVertical: spacing.xs,
          borderRadius: radius.sm,
          backgroundColor: item.verdict === 'bad' ? colors.red + '25' : 'transparent',
        }}
      >
        <Text style={{
          fontSize: 14,
          opacity: item.verdict === 'good' ? 0.3 : 1,
        }}>{'👎'}</Text>
      </TouchableOpacity>
      {item.source && !['pattern', 'streaming', 'error'].includes(item.source) && (
        <TouchableOpacity
          onPress={() => onFeedback(item, 'explain')}
          activeOpacity={0.7}
          style={{
            paddingHorizontal: spacing.sm,
            paddingVertical: spacing.xs,
            marginLeft: spacing.xs,
            borderRadius: radius.sm,
            backgroundColor: colors.surfaceLight,
          }}
        >
          <Text style={{ fontSize: fontSize.xs, color: colors.textSecondary, fontWeight: '600' }}>How?</Text>
        </TouchableOpacity>
      )}
    </View>
  )
}

export default function ChatScreen({ onBack, assistMode }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(false)
  const [keyboardHeight, setKeyboardHeight] = useState(0)
  const [feedbackModal, setFeedbackModal] = useState(null)
  const [feedbackNote, setFeedbackNote] = useState('')
  const [expandedMsg, setExpandedMsg] = useState(null)
  const flatRef = useRef(null)
  const loadingRef = useRef(false)
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
    if (!text?.trim() || loadingRef.current) return
    loadingRef.current = true
    setLoading(true)
    setInput('')
    const sid = await getSessionId()

    const userMsg = { id: Date.now().toString(), role: 'user', text: text.trim() }
    setMessages(prev => [...prev, userMsg])

    const botId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: botId, role: 'assistant', text: '', source: 'streaming', question: text.trim() }])

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
          m.id === botId ? {
            ...m,
            source: meta.source,
            flag: meta.flag,
            reasoning: meta.reasoning,
            entries_used: meta.entries_used,
            mode: meta.mode,
          } : m
        ))
        loadingRef.current = false
        setLoading(false)
        if (autoSpeak && fullReply) voice.speak(fullReply)
      },
      err => {
        setMessages(prev => prev.map(m =>
          m.id === botId ? { ...m, text: 'Error: ' + err, source: 'error' } : m
        ))
        loadingRef.current = false
        setLoading(false)
      }
    )
  }, [autoSpeak, voice])

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

  const handleFeedback = useCallback(async (item, action) => {
    if (action === 'explain') {
      setExpandedMsg(expandedMsg === item.id ? null : item.id)
      return
    }
    if (item.verdict === action) return
    setMessages(prev => prev.map(m =>
      m.id === item.id ? { ...m, verdict: action } : m
    ))
    setFeedbackModal({ ...item, verdict: action })
    setFeedbackNote('')
  }, [expandedMsg])

  const submitFeedback = useCallback(async () => {
    if (!feedbackModal) return
    const sid = await getSessionId()
    api.sendFeedback({
      question: feedbackModal.question || '',
      verdict: feedbackModal.verdict,
      note: feedbackNote,
      answer: feedbackModal.text,
      source: feedbackModal.source,
      entries_used: feedbackModal.entries_used || [],
      reasoning: feedbackModal.reasoning || [],
      session_id: sid,
    }).catch(() => {})
    setFeedbackModal(null)
    setFeedbackNote('')
  }, [feedbackModal, feedbackNote])

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
                {autoSpeak ? '🔊' : '🔇'}
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
                  New
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
        keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1, backgroundColor: colors.background }}
        contentContainerStyle={{ paddingVertical: spacing.lg, paddingHorizontal: spacing.lg, flexGrow: 1 }}
        onContentSizeChange={() => flatRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <Text style={{ fontSize: 56, marginBottom: spacing.md }}>{'👽'}</Text>
            <Text style={{
              color: colors.text,
              fontSize: fontSize.xl,
              fontWeight: '600',
              textAlign: 'center',
              marginBottom: spacing.xs,
            }}>
              Open a channel
            </Text>
            <Text style={{
              color: colors.textDim,
              fontSize: fontSize.sm,
              textAlign: 'center',
              maxWidth: 220,
              lineHeight: 18,
            }}>
              {voice.available
                ? 'Type a message or tap the mic to speak'
                : 'Type a message to start a conversation'
              }
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const isUser = item.role === 'user'
          const isExpanded = expandedMsg === item.id
          const tags = []
          if (item.source && !['pattern', 'streaming', 'error'].includes(item.source))
            tags.push(SOURCE_LABELS[item.source] || item.source)
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

              {!isUser && (
                <View style={{ maxWidth: '82%' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' }}>
                    {tags.length > 0 && (
                      <Text style={{
                        color: colors.textDim,
                        fontSize: fontSize.xs,
                        marginTop: spacing.xs,
                        marginRight: spacing.xs,
                      }}>
                        {tags.join(' · ')}
                      </Text>
                    )}
                    {item.text && item.source !== 'streaming' && (
                      <TouchableOpacity
                        onPress={() => voice.speaking ? voice.stopSpeaking() : voice.speak(item.text)}
                        activeOpacity={0.7}
                        style={{ marginTop: spacing.xs, marginRight: spacing.xs }}
                      >
                        <Text style={{ fontSize: 14, color: voice.speaking ? colors.primary : colors.textDim }}>
                          {voice.speaking ? '🔊' : '🔈'}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  <FeedbackBar item={item} onFeedback={handleFeedback} />

                  {isExpanded && (
                    <View style={{
                      backgroundColor: colors.surface,
                      borderRadius: radius.md,
                      padding: spacing.md,
                      marginTop: spacing.sm,
                      borderWidth: 1,
                      borderColor: colors.border,
                    }}>
                      <Text style={{ color: colors.textSecondary, fontSize: fontSize.xs, fontWeight: '600', marginBottom: spacing.xs }}>
                        HOW IT GOT THAT ANSWER
                      </Text>
                      {item.source && (
                        <Text style={{ color: colors.text, fontSize: fontSize.sm, marginBottom: spacing.xs }}>
                          Source: {SOURCE_LABELS[item.source] || item.source}
                        </Text>
                      )}
                      {item.mode && (
                        <Text style={{ color: colors.text, fontSize: fontSize.sm, marginBottom: spacing.xs }}>
                          Mode: {item.mode === 'no_drift' ? 'Grounded' : 'Creative'}
                        </Text>
                      )}
                      {item.entries_used?.length > 0 && (
                        <View style={{ marginBottom: spacing.xs }}>
                          <Text style={{ color: colors.textDim, fontSize: fontSize.xs, marginBottom: 2 }}>
                            Knowledge used:
                          </Text>
                          {item.entries_used.map((e, i) => (
                            <Text key={i} style={{ color: colors.primary, fontSize: fontSize.sm }}>
                              {'  '}• {e}
                            </Text>
                          ))}
                        </View>
                      )}
                      {item.reasoning?.length > 0 && (
                        <View>
                          <Text style={{ color: colors.textDim, fontSize: fontSize.xs, marginBottom: 2 }}>
                            Reasoning:
                          </Text>
                          {item.reasoning.map((step, i) => (
                            <Text key={i} style={{ color: colors.textSecondary, fontSize: fontSize.sm }}>
                              {i + 1}. {step}
                            </Text>
                          ))}
                        </View>
                      )}
                    </View>
                  )}
                </View>
              )}
            </View>
          )
        }}
      />

      <View style={{
        flexDirection: 'row',
        alignItems: 'flex-end',
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
            textAlignVertical: 'center',
          }}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          onPress={send}
          disabled={loading || !input.trim()}
          activeOpacity={0.7}
          style={{
            width: 44,
            height: 44,
            borderRadius: 22,
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
            : <Text style={{ color: colors.white, fontSize: 18, transform: [{ rotate: '45deg' }] }}>{'➤'}</Text>
          }
        </TouchableOpacity>
      </View>

      <Modal visible={!!feedbackModal} transparent animationType="fade">
        <View style={{
          flex: 1,
          justifyContent: 'center',
          backgroundColor: 'rgba(0,0,0,0.8)',
          padding: spacing.xxl,
        }}>
          <View style={{
            backgroundColor: colors.surface,
            borderRadius: radius.xl,
            padding: spacing.xl,
            borderWidth: 1,
            borderColor: colors.border,
          }}>
            <Text style={{
              fontSize: fontSize.xl,
              fontWeight: '700',
              color: colors.text,
              marginBottom: spacing.sm,
            }}>
              {feedbackModal?.verdict === 'good' ? '👍 Good answer' : '👎 Bad answer'}
            </Text>
            <Text style={{
              fontSize: fontSize.sm,
              color: colors.textDim,
              marginBottom: spacing.lg,
            }}>
              Leave a note to help retrain the model (optional)
            </Text>
            <TextInput
              value={feedbackNote}
              onChangeText={setFeedbackNote}
              placeholder="What was good/bad about this answer?"
              placeholderTextColor={colors.textDim}
              multiline
              style={{
                backgroundColor: colors.inputBg,
                color: colors.text,
                borderRadius: radius.md,
                padding: spacing.md,
                fontSize: fontSize.md,
                borderWidth: 1,
                borderColor: colors.inputBorder,
                marginBottom: spacing.lg,
                minHeight: 80,
                textAlignVertical: 'top',
              }}
            />
            <View style={{ flexDirection: 'row', gap: spacing.sm }}>
              <TouchableOpacity
                onPress={() => { setFeedbackModal(null); setFeedbackNote('') }}
                style={{
                  flex: 1,
                  padding: spacing.md,
                  borderRadius: radius.md,
                  borderWidth: 1,
                  borderColor: colors.border,
                  alignItems: 'center',
                }}
              >
                <Text style={{ color: colors.textSecondary }}>Skip</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={submitFeedback}
                style={{
                  flex: 1,
                  padding: spacing.md,
                  borderRadius: radius.md,
                  backgroundColor: colors.primary,
                  alignItems: 'center',
                }}
              >
                <Text style={{ color: colors.white, fontWeight: '600' }}>Submit</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </Wrapper>
  )
}
