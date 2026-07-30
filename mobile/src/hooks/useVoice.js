import { useState, useEffect, useCallback, useRef } from 'react'
import { Platform } from 'react-native'
import Voice from '@react-native-voice/voice'
import * as Speech from 'expo-speech'

export default function useVoice() {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [available, setAvailable] = useState(false)
  const onResultRef = useRef(null)

  useEffect(() => {
    Voice.isAvailable().then((yes) => setAvailable(!!yes)).catch(() => {})

    Voice.onSpeechStart = () => setListening(true)
    Voice.onSpeechEnd = () => setListening(false)
    Voice.onSpeechResults = (e) => {
      const text = e.value?.[0] || ''
      setTranscript(text)
      if (onResultRef.current) onResultRef.current(text)
    }
    Voice.onSpeechPartialResults = (e) => {
      setTranscript(e.value?.[0] || '')
    }
    Voice.onSpeechError = () => {
      setListening(false)
    }

    return () => {
      Voice.destroy().then(Voice.removeAllListeners).catch(() => {})
    }
  }, [])

  const startListening = useCallback(async (onResult) => {
    onResultRef.current = onResult || null
    setTranscript('')
    try {
      await Voice.start('en-US')
    } catch {
      setListening(false)
    }
  }, [])

  const stopListening = useCallback(async () => {
    try {
      await Voice.stop()
    } catch {}
    setListening(false)
  }, [])

  const speak = useCallback((text) => {
    if (!text) return
    Speech.stop()
    setSpeaking(true)
    Speech.speak(text, {
      language: 'en-US',
      pitch: 0.95,
      rate: Platform.OS === 'ios' ? 0.52 : 0.9,
      onDone: () => setSpeaking(false),
      onStopped: () => setSpeaking(false),
      onError: () => setSpeaking(false),
    })
  }, [])

  const stopSpeaking = useCallback(() => {
    Speech.stop()
    setSpeaking(false)
  }, [])

  return {
    listening,
    speaking,
    transcript,
    available,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
  }
}
