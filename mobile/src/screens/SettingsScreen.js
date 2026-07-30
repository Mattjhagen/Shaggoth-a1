import React, { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  Alert, Platform,
} from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

function SectionHeader({ title }) {
  return (
    <Text style={{
      color: colors.textSecondary,
      fontSize: fontSize.sm,
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: 1,
      marginBottom: spacing.md,
      marginTop: spacing.xl,
    }}>
      {title}
    </Text>
  )
}

export default function SettingsScreen() {
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
    Alert.alert('Saved', 'Settings updated. Reconnect to apply.')
    setSaving(false)
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Settings" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
      >
        <SectionHeader title="Connection" />

        <Text style={{ color: colors.textDim, fontSize: fontSize.sm, marginBottom: spacing.xs }}>
          API URL
        </Text>
        <TextInput
          value={apiUrl}
          onChangeText={setApiUrl}
          autoCapitalize="none"
          style={{
            backgroundColor: colors.surfaceCard,
            color: colors.text,
            borderRadius: radius.lg,
            padding: spacing.lg,
            fontSize: fontSize.md,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: spacing.lg,
          }}
        />

        <Text style={{ color: colors.textDim, fontSize: fontSize.sm, marginBottom: spacing.xs }}>
          API Key
        </Text>
        <TextInput
          value={apiKey}
          onChangeText={setApiKey}
          secureTextEntry
          autoCapitalize="none"
          style={{
            backgroundColor: colors.surfaceCard,
            color: colors.text,
            borderRadius: radius.lg,
            padding: spacing.lg,
            fontSize: fontSize.md,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: spacing.lg,
          }}
        />

        <TouchableOpacity
          onPress={save}
          disabled={saving}
          activeOpacity={0.8}
          style={{
            backgroundColor: colors.primary,
            borderRadius: radius.lg,
            padding: spacing.lg,
            alignItems: 'center',
            opacity: saving ? 0.5 : 1,
            marginBottom: spacing.xl,
          }}
        >
          <Text style={{
            color: colors.white,
            fontSize: fontSize.lg,
            fontWeight: '600',
          }}>
            {saving ? 'Saving...' : 'Save Settings'}
          </Text>
        </TouchableOpacity>

        <SectionHeader title="Guardrails" />
        {guardrails.length === 0 ? (
          <Text style={{ color: colors.textDim, marginBottom: spacing.lg }}>No guardrail rules.</Text>
        ) : (
          guardrails.map(r => (
            <View key={r.id} style={{
              backgroundColor: colors.surfaceCard,
              borderRadius: radius.md,
              padding: spacing.md,
              marginBottom: spacing.sm,
              borderWidth: 1,
              borderColor: colors.border,
            }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{
                  color: colors.text,
                  fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
                  fontSize: fontSize.sm,
                }}>
                  {r.id}
                </Text>
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: spacing.xs,
                  paddingHorizontal: spacing.sm,
                  paddingVertical: spacing.xs,
                  borderRadius: radius.sm,
                  backgroundColor: (r.enabled !== false ? colors.green : colors.red) + '15',
                }}>
                  <Text style={{
                    color: r.enabled !== false ? colors.green : colors.red,
                    fontSize: fontSize.xs,
                    fontWeight: '600',
                  }}>
                    {r.type} {r.enabled !== false ? '✓' : '✗'}
                  </Text>
                </View>
              </View>
              {r.message && (
                <Text style={{
                  color: colors.textDim,
                  fontSize: fontSize.sm,
                  marginTop: spacing.xs,
                }}>
                  {r.message}
                </Text>
              )}
            </View>
          ))
        )}

        {personality && (
          <>
            <SectionHeader title="Personality" />
            <View style={{
              backgroundColor: colors.surfaceCard,
              borderRadius: radius.xl,
              padding: spacing.lg,
              borderWidth: 1,
              borderColor: colors.border,
            }}>
              <Text style={{
                color: colors.text,
                fontSize: fontSize.md,
                lineHeight: 22,
                marginBottom: spacing.md,
              }}>
                {personality.backstory}
              </Text>
              <View style={{
                flexDirection: 'row',
                flexWrap: 'wrap',
                gap: spacing.sm,
              }}>
                {(personality.traits || []).map((t, i) => (
                  <View key={i} style={{
                    backgroundColor: colors.primaryMuted,
                    borderRadius: radius.full,
                    paddingHorizontal: spacing.md,
                    paddingVertical: spacing.xs + 2,
                    borderWidth: 1,
                    borderColor: colors.primaryBorder,
                  }}>
                    <Text style={{ color: colors.primary, fontSize: fontSize.sm }}>
                      {t}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          </>
        )}

        <View style={{ marginTop: spacing.xxxl, alignItems: 'center' }}>
          <Text style={{ fontSize: 24, marginBottom: spacing.sm }}>{'👽'}</Text>
          <Text style={{ color: colors.textDim, fontSize: fontSize.xs }}>
            Shaggoth AI v1.0.0
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: fontSize.xs, marginTop: spacing.xs }}>
            Orbital AI Command Center
          </Text>
        </View>
      </ScrollView>
    </View>
  )
}
