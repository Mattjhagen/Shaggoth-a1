import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  Platform, RefreshControl,
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

function StatusDot({ connected, checking }) {
  const color = checking ? colors.yellow : connected ? colors.green : colors.red
  const label = checking ? 'Connecting...' : connected ? 'Online' : 'Offline'
  return (
    <View style={{
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingHorizontal: spacing.sm,
      paddingVertical: spacing.xs,
      borderRadius: radius.full,
      backgroundColor: color + '15',
    }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />
      <Text style={{ color, fontSize: fontSize.xs, fontWeight: '600' }}>
        {label}
      </Text>
    </View>
  )
}

export default function SettingsScreen({ connected: initialConnected, onConnectionChange }) {
  const [apiKey, setApiKey] = useState(api.getApiKey())
  const [guardrails, setGuardrails] = useState([])
  const [personality, setPersonality] = useState(null)
  const [connected, setConnected] = useState(initialConnected)
  const [checking, setChecking] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    setConnected(initialConnected)
  }, [initialConnected])

  const loadData = useCallback(async () => {
    if (!connected) return
    try {
      const [g, p] = await Promise.all([
        api.getGuardrails().catch(() => ({ rules: [] })),
        api.getPersonality().catch(() => null),
      ])
      setGuardrails(g.rules || [])
      if (p) setPersonality(p)
    } catch {}
  }, [connected])

  useEffect(() => { loadData() }, [loadData])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    await loadData()
    setRefreshing(false)
  }, [loadData])

  const reconnect = useCallback(async () => {
    setChecking(true)
    await api.saveApiKey(apiKey)
    try {
      await api.health()
      setConnected(true)
      if (onConnectionChange) onConnectionChange(true)
    } catch {
      setConnected(false)
      if (onConnectionChange) onConnectionChange(false)
    }
    setChecking(false)
  }, [apiKey, onConnectionChange])

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header
        title="Settings"
        rightContent={<StatusDot connected={connected} checking={checking} />}
      />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        <SectionHeader title="Connection" />

        <View style={{
          backgroundColor: colors.surfaceCard,
          borderRadius: radius.xl,
          padding: spacing.lg,
          borderWidth: 1,
          borderColor: connected ? colors.green + '40' : colors.border,
          marginBottom: spacing.lg,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md }}>
            <View style={{
              width: 10, height: 10, borderRadius: 5,
              backgroundColor: checking ? colors.yellow : connected ? colors.green : colors.red,
              marginRight: spacing.md,
            }} />
            <Text style={{ color: colors.text, fontSize: fontSize.lg, fontWeight: '600', flex: 1 }}>
              {checking ? 'Connecting...' : connected ? 'Connected to Shaggoth' : 'Not connected'}
            </Text>
          </View>
          <Text style={{ color: colors.textDim, fontSize: fontSize.sm, marginBottom: spacing.md }}>
            {api.getApiUrl()}
          </Text>
          {!connected && !checking && (
            <TouchableOpacity
              onPress={reconnect}
              activeOpacity={0.8}
              style={{
                backgroundColor: colors.primary,
                borderRadius: radius.lg,
                padding: spacing.md,
                alignItems: 'center',
              }}
            >
              <Text style={{ color: colors.white, fontSize: fontSize.md, fontWeight: '600' }}>
                Reconnect
              </Text>
            </TouchableOpacity>
          )}
        </View>

        <TouchableOpacity
          onPress={() => setShowAdvanced(v => !v)}
          activeOpacity={0.7}
          style={{ marginBottom: spacing.md }}
        >
          <Text style={{ color: colors.textSecondary, fontSize: fontSize.sm }}>
            {showAdvanced ? '▾ Hide advanced' : '▸ Advanced connection settings'}
          </Text>
        </TouchableOpacity>

        {showAdvanced && (
          <View style={{ marginBottom: spacing.lg }}>
            <Text style={{ color: colors.textDim, fontSize: fontSize.sm, marginBottom: spacing.xs }}>
              API Key (optional)
            </Text>
            <TextInput
              value={apiKey}
              onChangeText={setApiKey}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="None required for local network"
              placeholderTextColor={colors.textMuted}
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
              onPress={reconnect}
              disabled={checking}
              activeOpacity={0.8}
              style={{
                backgroundColor: colors.primary,
                borderRadius: radius.lg,
                padding: spacing.lg,
                alignItems: 'center',
                opacity: checking ? 0.5 : 1,
              }}
            >
              <Text style={{ color: colors.white, fontSize: fontSize.lg, fontWeight: '600' }}>
                {checking ? 'Connecting...' : 'Save & Reconnect'}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        <SectionHeader title="Guardrails" />
        {guardrails.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: spacing.xxl }}>
            <Text style={{ fontSize: 32, marginBottom: spacing.sm }}>{'🛡'}</Text>
            <Text style={{ color: colors.textDim, fontSize: fontSize.md }}>
              {connected ? 'No guardrail rules' : 'Connect to view guardrails'}
            </Text>
          </View>
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
