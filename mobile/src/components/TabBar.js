import React from 'react'
import { View, TouchableOpacity, Text, Platform } from 'react-native'
import { colors } from '../theme/colors'

const TABS = [
  { key: 'home', label: 'Home', icon: '⌂' },
  { key: 'explore', label: 'Explore', icon: '◈' },
  { key: 'tools', label: 'Tools', icon: '✦' },
  { key: 'settings', label: 'Settings', icon: '⚙' },
]

export default function TabBar({ tab, onTab }) {
  return (
    <View style={{
      flexDirection: 'row',
      backgroundColor: colors.surface,
      borderTopWidth: 1,
      borderColor: colors.border,
      paddingBottom: Platform.OS === 'ios' ? 24 : 10,
      paddingTop: 8,
      alignItems: 'center',
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
              style={{ flex: 1, alignItems: 'center', marginTop: -20 }}
            >
              <View style={{
                width: 52,
                height: 52,
                borderRadius: 26,
                backgroundColor: colors.primary,
                alignItems: 'center',
                justifyContent: 'center',
                shadowColor: colors.primary,
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: 0.4,
                shadowRadius: 8,
                elevation: 8,
              }}>
                <Text style={{ fontSize: 22, color: colors.white }}>
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
