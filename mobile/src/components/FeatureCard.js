import React from 'react'
import { View, Text, TouchableOpacity } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'

export default function FeatureCard({ icon, title, subtitle, accentColor, onPress, wide }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.8}
      style={{
        flex: wide ? undefined : 1,
        width: wide ? '100%' : undefined,
        backgroundColor: colors.surfaceCard,
        borderRadius: radius.xl,
        padding: spacing.xl,
        borderWidth: 1,
        borderColor: colors.border,
        minHeight: wide ? 90 : 170,
        justifyContent: 'space-between',
      }}
    >
      <View>
        <View style={{
          width: 44,
          height: 44,
          borderRadius: 14,
          backgroundColor: (accentColor || colors.primary) + '20',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: spacing.md,
        }}>
          <Text style={{ fontSize: 22 }}>{icon}</Text>
        </View>
        <Text style={{
          color: colors.text,
          fontSize: wide ? fontSize.xl : fontSize.lg,
          fontWeight: '700',
          marginBottom: spacing.xs,
        }}>
          {title}
        </Text>
        {subtitle && (
          <Text style={{
            color: colors.textSecondary,
            fontSize: fontSize.sm,
            lineHeight: 18,
          }}>
            {subtitle}
          </Text>
        )}
      </View>
      <View style={{
        alignSelf: 'flex-end',
        marginTop: spacing.md,
      }}>
        <View style={{
          width: 32,
          height: 32,
          borderRadius: 16,
          backgroundColor: colors.surfaceLight,
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 1,
          borderColor: colors.borderLight,
        }}>
          <Text style={{ color: colors.textSecondary, fontSize: 16 }}>{'→'}</Text>
        </View>
      </View>
    </TouchableOpacity>
  )
}
