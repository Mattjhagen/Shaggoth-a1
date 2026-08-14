import React, { useEffect, useState } from 'react'
import { View, Text, ScrollView, ActivityIndicator } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

export default function PersonalityScreen({ onBack }) {
  const [personality, setPersonality] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getPersonality()
      .then(setPersonality)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <Header title="Personality" onBack={onBack} />
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 60 }} />
      </View>
    )
  }

  if (!personality) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <Header title="Personality" onBack={onBack} />
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <Text style={{ color: colors.textDim, fontSize: fontSize.lg }}>
            Could not load personality data
          </Text>
        </View>
      </View>
    )
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Personality" onBack={onBack} />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
      >
        <View style={{ alignItems: 'center', marginBottom: spacing.xxl }}>
          <Text style={{ fontSize: 64, marginBottom: spacing.md }}>{'👽'}</Text>
          <Text style={{ color: colors.text, fontSize: fontSize.xxl, fontWeight: '700' }}>
            {personality.name || 'Shaggoth'}
          </Text>
        </View>

        {personality.backstory && (
          <View style={{
            backgroundColor: colors.surfaceCard,
            borderRadius: radius.xl,
            padding: spacing.xl,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: spacing.lg,
          }}>
            <Text style={{
              color: colors.textSecondary,
              fontSize: fontSize.xs,
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: spacing.md,
            }}>
              Backstory
            </Text>
            <Text style={{
              color: colors.text,
              fontSize: fontSize.md,
              lineHeight: 22,
            }}>
              {personality.backstory}
            </Text>
          </View>
        )}

        {personality.traits?.length > 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <Text style={{
              color: colors.textSecondary,
              fontSize: fontSize.xs,
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: spacing.md,
            }}>
              Traits
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
              {personality.traits.map((t, i) => (
                <View key={i} style={{
                  backgroundColor: colors.primaryMuted,
                  borderRadius: radius.full,
                  paddingHorizontal: spacing.lg,
                  paddingVertical: spacing.sm,
                  borderWidth: 1,
                  borderColor: colors.primaryBorder,
                }}>
                  <Text style={{ color: colors.primary, fontSize: fontSize.sm, fontWeight: '600' }}>
                    {t}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {personality.speaking_style && (
          <View style={{
            backgroundColor: colors.surfaceCard,
            borderRadius: radius.xl,
            padding: spacing.xl,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: spacing.lg,
          }}>
            <Text style={{
              color: colors.textSecondary,
              fontSize: fontSize.xs,
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: spacing.md,
            }}>
              Speaking Style
            </Text>
            <Text style={{ color: colors.text, fontSize: fontSize.md, lineHeight: 22 }}>
              {personality.speaking_style}
            </Text>
          </View>
        )}

        {personality.interests?.length > 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <Text style={{
              color: colors.textSecondary,
              fontSize: fontSize.xs,
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: spacing.md,
            }}>
              Interests
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
              {personality.interests.map((t, i) => (
                <View key={i} style={{
                  backgroundColor: colors.blue + '20',
                  borderRadius: radius.full,
                  paddingHorizontal: spacing.lg,
                  paddingVertical: spacing.sm,
                  borderWidth: 1,
                  borderColor: colors.blue + '30',
                }}>
                  <Text style={{ color: colors.blue, fontSize: fontSize.sm }}>
                    {t}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {personality.values?.length > 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <Text style={{
              color: colors.textSecondary,
              fontSize: fontSize.xs,
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: spacing.md,
            }}>
              Values
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
              {personality.values.map((t, i) => (
                <View key={i} style={{
                  backgroundColor: colors.green + '20',
                  borderRadius: radius.full,
                  paddingHorizontal: spacing.lg,
                  paddingVertical: spacing.sm,
                  borderWidth: 1,
                  borderColor: colors.green + '30',
                }}>
                  <Text style={{ color: colors.green, fontSize: fontSize.sm }}>
                    {t}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  )
}
