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
          width: 160,
          height: 160,
          borderRadius: 80,
          backgroundColor: colors.surfaceCard,
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 2,
          borderColor: colors.border,
          shadowColor: colors.primary,
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: 0.2,
          shadowRadius: 20,
          elevation: 10,
        }}>
          <View style={{
            width: 140,
            height: 140,
            borderRadius: 70,
            backgroundColor: colors.surfaceLight,
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Text style={{ fontSize: 32, marginBottom: 4 }}>{'👾'}</Text>
            <View style={{
              flexDirection: 'row',
              gap: 16,
              marginTop: 4,
            }}>
              <View style={{
                width: 14,
                height: 14,
                borderRadius: 7,
                backgroundColor: colors.primary,
                shadowColor: colors.primary,
                shadowOffset: { width: 0, height: 0 },
                shadowOpacity: 0.8,
                shadowRadius: 6,
              }} />
              <View style={{
                width: 14,
                height: 14,
                borderRadius: 7,
                backgroundColor: colors.primary,
                shadowColor: colors.primary,
                shadowOffset: { width: 0, height: 0 },
                shadowOpacity: 0.8,
                shadowRadius: 6,
              }} />
            </View>
            <View style={{
              width: 20,
              height: 3,
              borderRadius: 2,
              backgroundColor: colors.primaryDim,
              marginTop: 8,
            }} />
          </View>
        </View>
      </View>

      <View style={{ paddingHorizontal: spacing.lg }}>
        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="💬"
            title="Chat"
            subtitle="Smart AI for seamless conversations"
            accentColor={colors.primary}
            onPress={() => onNavigate('chat')}
          />
          <FeatureCard
            icon="📚"
            title="Knowledge"
            subtitle="Browse & search the knowledge base"
            accentColor={colors.green}
            onPress={() => onNavigate('knowledge')}
          />
        </View>

        <FeatureCard
          icon="🧠"
          title="Self-Learn"
          subtitle="Autonomous web research and knowledge acquisition"
          accentColor={colors.blue}
          onPress={() => onNavigate('learn')}
          wide
        />
      </View>
    </ScrollView>
  )
}
