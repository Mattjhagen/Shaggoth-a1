import { useState, useCallback, useRef } from 'react'
import { Platform } from 'react-native'
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from 'expo-speech-recognition'
import * as Speech from 'expo-speech'

export default function useVoice() {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [available, setAvailable] = useState(
    () => ExpoSpeechRecognitionModule.isRecognitionAvailable()
  )
  const onResultRef = useRef(null)

  useSpeechRecognitionEvent('start', () => setListening(true))
  useSpeechRecognitionEvent('end', () => setListening(false))
  useSpeechRecognitionEvent('error', () => setListening(false))
  useSpeechRecognitionEvent('result', (event) => {
    const text = event.results[0]?.transcript || ''
    setTranscript(text)
    if (event.isFinal && onResultRef.current) {
      onResultRef.current(text)
    }
  })

  const startListening = useCallback(async (onResult) => {
    onResultRef.current = onResult || null
    setTranscript('')
    try {
      const { granted } = await ExpoSpeechRecognitionModule.requestPermissionsAsync()
      if (!granted) {
        setAvailable(false)
        return
      }
      ExpoSpeechRecognitionModule.start({
        lang: 'en-US',
        interimResults: true,
        maxAlternatives: 1,
      })
    } catch {
      setListening(false)
    }
  }, [])

  const stopListening = useCallback(() => {
    try {
      ExpoSpeechRecognitionModule.stop()
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
