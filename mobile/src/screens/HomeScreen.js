import React from 'react'
import { View, Text, ScrollView, TouchableOpacity } from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import FeatureCard from '../components/FeatureCard'

export default function HomeScreen({ onNavigate, connected }) {

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
            <TouchableOpacity
              onPress={() => onNavigate('settings')}
              activeOpacity={0.7}
              style={{
                width: 36,
                height: 36,
                borderRadius: 18,
                backgroundColor: colors.surfaceLight,
                alignItems: 'center',
                justifyContent: 'center',
                borderWidth: 1,
                borderColor: colors.border,
              }}
            >
              <Text style={{ color: colors.text, fontSize: 16 }}>{'⚙'}</Text>
            </TouchableOpacity>
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

        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="👽"
            title="Personality"
            subtitle="View traits, backstory & values"
            accentColor={colors.blue}
            onPress={() => onNavigate('personality')}
          />
          <FeatureCard
            icon="🔭"
            title="Curiosity"
            subtitle="Autonomous research engine"
            accentColor={colors.yellow}
            onPress={() => onNavigate('curiosity')}
          />
        </View>

        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="🛡"
            title="Guardrails"
            subtitle="Safety rules & content filters"
            accentColor={colors.red}
            onPress={() => onNavigate('guardrails')}
          />
          <FeatureCard
            icon="🧠"
            title="Self-Learn"
            subtitle="Web research & training"
            accentColor={colors.primary}
            onPress={() => onNavigate('learn')}
          />
        </View>
      </View>
    </ScrollView>
  )
}
