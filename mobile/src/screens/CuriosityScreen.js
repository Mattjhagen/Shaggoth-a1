import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  ActivityIndicator, Alert,
} from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

function StatCard({ label, value, color }) {
  return (
    <View style={{
      flex: 1,
      backgroundColor: colors.surfaceCard,
      borderRadius: radius.lg,
      padding: spacing.md,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: colors.border,
    }}>
      <Text style={{
        fontSize: fontSize.xxl,
        fontWeight: '700',
        color: color || colors.primary,
      }}>
        {value}
      </Text>
      <Text style={{
        fontSize: fontSize.xs,
        color: colors.textDim,
        textTransform: 'uppercase',
        letterSpacing: 1,
        marginTop: spacing.xs,
      }}>
        {label}
      </Text>
    </View>
  )
}

export default function CuriosityScreen({ onBack }) {
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [topic, setTopic] = useState('')
  const [researching, setResearching] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, h] = await Promise.all([
        api.getCuriosityStatus().catch(() => null),
        api.getCuriosityHistory().catch(() => ({ sessions: [] })),
      ])
      if (s) setStatus(s)
      setHistory(h.sessions || h.history || [])
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const startResearch = async () => {
    if (!topic.trim()) { Alert.alert('Error', 'Enter a topic to research'); return }
    setResearching(true)
    try {
      await api.triggerCuriosityResearch(topic.trim())
      setTopic('')
      Alert.alert('Started', 'Curiosity engine is researching: ' + topic.trim())
      setTimeout(load, 3000)
    } catch (e) {
      Alert.alert('Error', e.message)
    }
    setResearching(false)
  }

  const triggerScheduler = async () => {
    try {
      await api.triggerCuriosityScheduler()
      Alert.alert('Triggered', 'Autonomous research cycle started')
      setTimeout(load, 3000)
    } catch (e) {
      Alert.alert('Error', e.message)
    }
  }

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <Header title="Curiosity Engine" onBack={onBack} />
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 60 }} />
      </View>
    )
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Curiosity Engine" onBack={onBack} />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {status && (
          <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg }}>
            <StatCard label="Topics" value={status.topics_researched || 0} />
            <StatCard label="Sources" value={status.sources_found || 0} color={colors.green} />
            <StatCard label="Active" value={status.is_active ? 'Yes' : 'No'} color={colors.blue} />
          </View>
        )}

        <Text style={{
          color: colors.textSecondary,
          fontSize: fontSize.xs,
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: 1,
          marginBottom: spacing.md,
        }}>
          Research a Topic
        </Text>

        <TextInput
          value={topic}
          onChangeText={setTopic}
          placeholder="What should Shaggoth research?"
          placeholderTextColor={colors.textDim}
          style={{
            backgroundColor: colors.surfaceCard,
            color: colors.text,
            borderRadius: radius.lg,
            padding: spacing.lg,
            fontSize: fontSize.md,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: spacing.md,
          }}
        />

        <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xxl }}>
          <TouchableOpacity
            onPress={startResearch}
            disabled={researching}
            activeOpacity={0.8}
            style={{
              flex: 2,
              backgroundColor: colors.primary,
              borderRadius: radius.lg,
              padding: spacing.lg,
              alignItems: 'center',
              opacity: researching ? 0.5 : 1,
            }}
          >
            <Text style={{ color: colors.white, fontSize: fontSize.md, fontWeight: '600' }}>
              {researching ? 'Researching...' : 'Research'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={triggerScheduler}
            activeOpacity={0.8}
            style={{
              flex: 1,
              backgroundColor: colors.surfaceCard,
              borderRadius: radius.lg,
              padding: spacing.lg,
              alignItems: 'center',
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <Text style={{ color: colors.textSecondary, fontSize: fontSize.md, fontWeight: '600' }}>
              Auto
            </Text>
          </TouchableOpacity>
        </View>

        <Text style={{
          color: colors.textSecondary,
          fontSize: fontSize.xs,
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: 1,
          marginBottom: spacing.md,
        }}>
          Research History
        </Text>

        {history.length === 0 ? (
          <Text style={{ color: colors.textDim }}>No research sessions yet.</Text>
        ) : (
          [...history].reverse().slice(0, 20).map((s, i) => (
            <View key={i} style={{
              backgroundColor: colors.surfaceCard,
              borderRadius: radius.md,
              padding: spacing.md,
              marginBottom: spacing.sm,
              borderWidth: 1,
              borderColor: colors.border,
            }}>
              <Text style={{
                color: colors.text,
                fontSize: fontSize.md,
                fontWeight: '600',
                marginBottom: spacing.xs,
              }}>
                {s.topic || s.query || 'Research session'}
              </Text>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{
                  color: s.status === 'completed' ? colors.green
                    : s.status === 'failed' ? colors.red
                    : colors.primary,
                  fontSize: fontSize.xs,
                  fontWeight: '600',
                }}>
                  {(s.status || 'done').toUpperCase()}
                </Text>
                {s.sources_found != null && (
                  <Text style={{ color: colors.textDim, fontSize: fontSize.xs }}>
                    {s.sources_found} sources
                  </Text>
                )}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  )
}
