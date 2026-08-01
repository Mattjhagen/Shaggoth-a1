import React from 'react'
import { View, Text, TouchableOpacity } from 'react-native'
import { colors, spacing, fontSize } from '../theme/colors'

export default function Header({ title, onBack, rightContent }) {
  return (
    <View style={{
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
      backgroundColor: colors.background,
    }}>
      {onBack && (
        <TouchableOpacity
          onPress={onBack}
          activeOpacity={0.7}
          style={{
            width: 36,
            height: 36,
            borderRadius: 18,
            backgroundColor: colors.surfaceLight,
            alignItems: 'center',
            justifyContent: 'center',
            marginRight: spacing.md,
            borderWidth: 1,
            borderColor: colors.border,
          }}
        >
          <Text style={{ color: colors.text, fontSize: 18 }}>{'←'}</Text>
        </TouchableOpacity>
      )}
      <Text style={{
        flex: 1,
        color: colors.text,
        fontSize: fontSize.xl,
        fontWeight: '700',
      }}>
        {title}
      </Text>
      {rightContent}
    </View>
  )
}
