import React from 'react'
import { View, TouchableOpacity, Text, Platform } from 'react-native'
import { colors, spacing, fontSize } from '../theme/colors'

const TABS = [
  { key: 'home', label: 'Home', icon: '🛸' },
  { key: 'explore', label: 'Explore', icon: '🌌' },
  { key: 'tools', label: 'Tools', icon: '🔧' },
  { key: 'settings', label: 'Settings', icon: '⚙' },
]

export default function TabBar({ tab, onTab }) {
  return (
    <View style={{
      flexDirection: 'row',
      backgroundColor: colors.surface,
      borderTopWidth: 1,
      borderColor: colors.border,
      paddingBottom: Platform.OS === 'ios' ? 24 : 12,
      paddingTop: 10,
      alignItems: 'flex-end',
    }}>
      {TABS.map((t, idx) => {
        const isCenter = idx === 1
        const active = tab === t.key

        if (isCenter) {
          return (
            <TouchableOpacity
              key={t.key}
              onPress={() => onTab(t.key)}
              activeOpacity={0.8}
              style={{ flex: 1, alignItems: 'center', marginTop: -22 }}
            >
              <View style={{
                width: 54,
                height: 54,
                borderRadius: 27,
                backgroundColor: active ? colors.primary : colors.primaryDim,
                alignItems: 'center',
                justifyContent: 'center',
                shadowColor: colors.primary,
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.4,
                shadowRadius: 8,
                elevation: 8,
                borderWidth: 3,
                borderColor: colors.surface,
              }}>
                <Text style={{ fontSize: 22 }}>
                  {t.icon}
                </Text>
              </View>
              <Text style={{
                fontSize: 10,
                color: active ? colors.primary : colors.textDim,
                marginTop: 4,
                fontWeight: active ? '600' : '400',
              }}>
                {t.label}
              </Text>
            </TouchableOpacity>
          )
        }

        return (
          <TouchableOpacity
            key={t.key}
            onPress={() => onTab(t.key)}
            activeOpacity={0.7}
            style={{ flex: 1, alignItems: 'center' }}
          >
            <Text style={{
              fontSize: 22,
              color: active ? colors.primary : colors.textDim,
            }}>
              {t.icon}
            </Text>
            <Text style={{
              fontSize: 10,
              color: active ? colors.primary : colors.textDim,
              marginTop: 2,
              fontWeight: active ? '600' : '400',
            }}>
              {t.label}
            </Text>
          </TouchableOpacity>
        )
      })}
    </View>
  )
}
