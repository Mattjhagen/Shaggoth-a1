import React from 'react'
import { Text, TouchableOpacity } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'

export default function CategoryChip({ label, active, onPress }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.7}
      style={{
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm,
        borderRadius: radius.full,
        backgroundColor: active ? colors.primary : 'transparent',
        borderWidth: 1,
        borderColor: active ? colors.primary : colors.borderLight,
        marginRight: spacing.sm,
      }}
    >
      <Text style={{
        color: active ? colors.white : colors.textSecondary,
        fontSize: fontSize.md,
        fontWeight: active ? '600' : '400',
      }}>
        {label}
      </Text>
    </TouchableOpacity>
  )
}
