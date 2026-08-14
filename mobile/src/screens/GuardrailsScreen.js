import React, { useEffect, useState } from 'react'
import { View, Text, ScrollView, ActivityIndicator, Platform } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

export default function GuardrailsScreen({ onBack }) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getGuardrails()
      .then(d => setRules(d.rules || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Guardrails" onBack={onBack} />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={{
          color: colors.textDim,
          fontSize: fontSize.sm,
          marginBottom: spacing.lg,
          lineHeight: 20,
        }}>
          Safety rules that filter input and output to keep conversations on track.
        </Text>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        ) : rules.length === 0 ? (
          <View style={{ alignItems: 'center', marginTop: 40 }}>
            <Text style={{ fontSize: 48, marginBottom: spacing.md }}>{'🛡'}</Text>
            <Text style={{ color: colors.textDim, fontSize: fontSize.lg }}>
              No guardrail rules configured
            </Text>
          </View>
        ) : (
          rules.map(r => (
            <View key={r.id} style={{
              backgroundColor: colors.surfaceCard,
              borderRadius: radius.xl,
              padding: spacing.lg,
              marginBottom: spacing.md,
              borderWidth: 1,
              borderColor: r.enabled !== false ? colors.green + '30' : colors.border,
            }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm }}>
                <Text style={{
                  color: colors.text,
                  fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
                  fontSize: fontSize.sm,
                  fontWeight: '600',
                }}>
                  {r.id}
                </Text>
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: spacing.xs,
                  paddingHorizontal: spacing.sm,
                  paddingVertical: spacing.xs,
                  borderRadius: radius.full,
                  backgroundColor: (r.enabled !== false ? colors.green : colors.red) + '15',
                }}>
                  <View style={{
                    width: 6, height: 6, borderRadius: 3,
                    backgroundColor: r.enabled !== false ? colors.green : colors.red,
                  }} />
                  <Text style={{
                    color: r.enabled !== false ? colors.green : colors.red,
                    fontSize: fontSize.xs,
                    fontWeight: '600',
                  }}>
                    {r.enabled !== false ? 'Active' : 'Disabled'}
                  </Text>
                </View>
              </View>

              <View style={{
                backgroundColor: colors.surface,
                borderRadius: radius.sm,
                paddingHorizontal: spacing.sm,
                paddingVertical: spacing.xs,
                alignSelf: 'flex-start',
                marginBottom: spacing.sm,
              }}>
                <Text style={{ color: colors.primary, fontSize: fontSize.xs, fontWeight: '600' }}>
                  {r.type || 'filter'}
                </Text>
              </View>

              {r.message && (
                <Text style={{
                  color: colors.textSecondary,
                  fontSize: fontSize.sm,
                  lineHeight: 20,
                }}>
                  {r.message}
                </Text>
              )}

              {r.pattern && (
                <Text style={{
                  color: colors.textDim,
                  fontSize: fontSize.xs,
                  fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
                  marginTop: spacing.xs,
                }}>
                  /{r.pattern}/
                </Text>
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  )
}
