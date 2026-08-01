import { useState, useCallback, useRef, useEffect } from 'react'
import { Platform } from 'react-native'
import * as Speech from 'expo-speech'

let SpeechRecognition = null
try {
  SpeechRecognition = require('expo-speech-recognition')
} catch {}

const noop = () => {}

export default function useVoice() {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [available, setAvailable] = useState(false)
  const onResultRef = useRef(null)
  const subscribedRef = useRef(false)

  useEffect(() => {
    if (!SpeechRecognition) return

    const mod = SpeechRecognition.ExpoSpeechRecognitionModule
    if (!mod) return

    try {
      setAvailable(mod.isRecognitionAvailable())
    } catch {
      return
    }

    if (subscribedRef.current) return
    subscribedRef.current = true

    const subs = [
      mod.addListener('start', () => setListening(true)),
      mod.addListener('end', () => setListening(false)),
      mod.addListener('error', () => setListening(false)),
      mod.addListener('result', (event) => {
        const text = event.results?.[0]?.transcript || ''
        setTranscript(text)
        if (event.isFinal && onResultRef.current) {
          onResultRef.current(text)
        }
      }),
    ]

    return () => subs.forEach(s => s?.remove?.())
  }, [])

  const startListening = useCallback(async (onResult) => {
    if (!SpeechRecognition) return
    const mod = SpeechRecognition.ExpoSpeechRecognitionModule
    if (!mod) return

    onResultRef.current = onResult || null
    setTranscript('')
    try {
      const { granted } = await mod.requestPermissionsAsync()
      if (!granted) {
        setAvailable(false)
        return
      }
      mod.start({
        lang: 'en-US',
        interimResults: true,
        maxAlternatives: 1,
      })
    } catch {
      setListening(false)
    }
  }, [])

  const stopListening = useCallback(() => {
    if (!SpeechRecognition) return
    try {
      SpeechRecognition.ExpoSpeechRecognitionModule.stop()
    } catch {}
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
