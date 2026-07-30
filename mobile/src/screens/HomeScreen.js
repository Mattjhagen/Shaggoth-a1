import React, { useEffect, useState } from 'react'
import { View, Text, ScrollView } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import FeatureCard from '../components/FeatureCard'
import * as api from '../api/shaggoth'

export default function HomeScreen({ onNavigate, connected }) {
  const [greeting, setGreeting] = useState('')

  useEffect(() => {
    api.health()
      .then(() => setGreeting('Online'))
      .catch(() => setGreeting('Offline'))
  }, [])

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ paddingBottom: 20 }}
      showsVerticalScrollIndicator={false}
    >
      <View style={{
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.xl,
      }}>
        <View style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: spacing.xxxl,
        }}>
          <Text style={{
            color: colors.text,
            fontSize: fontSize.xxl,
            fontWeight: '700',
          }}>
            <Text style={{ color: colors.primary }}>Shaggoth </Text>
            AI
          </Text>
          <View style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: spacing.sm,
          }}>
            <View style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              backgroundColor: connected ? colors.green : colors.red,
            }} />
            <View style={{
              width: 36,
              height: 36,
              borderRadius: 18,
              backgroundColor: colors.surfaceLight,
              alignItems: 'center',
              justifyContent: 'center',
              borderWidth: 1,
              borderColor: colors.border,
            }}>
              <Text style={{ color: colors.text, fontSize: 16 }}>{'⚙'}</Text>
            </View>
          </View>
        </View>
      </View>

      <View style={{
        alignItems: 'center',
        paddingVertical: spacing.xxl,
        marginBottom: spacing.lg,
      }}>
        <View style={{
          width: 170,
          height: 170,
          borderRadius: 85,
          backgroundColor: colors.surfaceCard,
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 2,
          borderColor: colors.border,
          shadowColor: colors.green,
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: 0.3,
          shadowRadius: 24,
          elevation: 12,
        }}>
          <View style={{
            width: 148,
            height: 148,
            borderRadius: 74,
            backgroundColor: colors.surfaceLight,
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Text style={{ fontSize: 64 }}>{'👽'}</Text>
          </View>
        </View>
        <Text style={{
          color: colors.textDim,
          fontSize: fontSize.sm,
          marginTop: spacing.md,
          letterSpacing: 2,
          textTransform: 'uppercase',
        }}>
          {connected ? 'Uplink Established' : 'Node Offline'}
        </Text>
      </View>

      <View style={{ paddingHorizontal: spacing.lg }}>
        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="🛸"
            title="Chat"
            subtitle="Transmit messages to the AI core"
            accentColor={colors.primary}
            onPress={() => onNavigate('chat')}
          />
          <FeatureCard
            icon="🌌"
            title="Knowledge"
            subtitle="Browse the orbital knowledge base"
            accentColor={colors.green}
            onPress={() => onNavigate('knowledge')}
          />
        </View>

        <FeatureCard
          icon="🧠"
          title="Self-Learn"
          subtitle="Autonomous web research & knowledge acquisition"
          accentColor={colors.blue}
          onPress={() => onNavigate('learn')}
          wide
        />
      </View>
    </ScrollView>
  )
}
