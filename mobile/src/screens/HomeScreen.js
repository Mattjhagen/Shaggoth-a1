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
          marginBottom: spacing.xxl,
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
              flexDirection: 'row',
              alignItems: 'center',
              gap: spacing.xs,
              paddingHorizontal: spacing.sm + 2,
              paddingVertical: spacing.xs + 1,
              borderRadius: radius.full,
              backgroundColor: (connected ? colors.green : colors.red) + '15',
            }}>
              <View style={{
                width: 6,
                height: 6,
                borderRadius: 3,
                backgroundColor: connected ? colors.green : colors.red,
              }} />
              <Text style={{
                color: connected ? colors.green : colors.red,
                fontSize: fontSize.xs,
                fontWeight: '600',
              }}>
                {connected ? 'Online' : 'Offline'}
              </Text>
            </View>
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
        marginBottom: spacing.md,
      }}>
        <View style={{
          width: 150,
          height: 150,
          borderRadius: 75,
          backgroundColor: colors.surfaceCard,
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 2,
          borderColor: connected ? colors.primary + '40' : colors.border,
          shadowColor: connected ? colors.primary : colors.green,
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: connected ? 0.4 : 0.2,
          shadowRadius: 24,
          elevation: 12,
        }}>
          <View style={{
            width: 130,
            height: 130,
            borderRadius: 65,
            backgroundColor: colors.surfaceLight,
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Text style={{ fontSize: 56 }}>{'👽'}</Text>
          </View>
        </View>
        <Text style={{
          color: colors.textDim,
          fontSize: fontSize.sm,
          marginTop: spacing.lg,
          letterSpacing: 2,
          textTransform: 'uppercase',
        }}>
          {connected ? 'Uplink Established' : 'Node Offline'}
        </Text>
      </View>

      <View style={{ paddingHorizontal: spacing.lg }}>
        <TouchableOpacity
          onPress={() => onNavigate('chat')}
          activeOpacity={0.8}
          style={{
            backgroundColor: colors.primary,
            borderRadius: radius.xl,
            padding: spacing.xl,
            marginBottom: spacing.md,
            flexDirection: 'row',
            alignItems: 'center',
            shadowColor: colors.primary,
            shadowOffset: { width: 0, height: 4 },
            shadowOpacity: 0.3,
            shadowRadius: 12,
            elevation: 8,
          }}
        >
          <View style={{
            width: 48,
            height: 48,
            borderRadius: 16,
            backgroundColor: 'rgba(255,255,255,0.2)',
            alignItems: 'center',
            justifyContent: 'center',
            marginRight: spacing.lg,
          }}>
            <Text style={{ fontSize: 24 }}>{'🛸'}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.white, fontSize: fontSize.xl, fontWeight: '700' }}>
              Start Chat
            </Text>
            <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: fontSize.sm, marginTop: 2 }}>
              Transmit messages to the AI core
            </Text>
          </View>
          <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 20 }}>{'→'}</Text>
        </TouchableOpacity>

        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="🌌"
            title="Knowledge"
            subtitle="Browse the orbital knowledge base"
            accentColor={colors.green}
            onPress={() => onNavigate('knowledge')}
          />
          <FeatureCard
            icon="👽"
            title="Personality"
            subtitle="View traits, backstory & values"
            accentColor={colors.blue}
            onPress={() => onNavigate('personality')}
          />
        </View>

        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="🔭"
            title="Curiosity"
            subtitle="Autonomous research engine"
            accentColor={colors.yellow}
            onPress={() => onNavigate('curiosity')}
          />
          <FeatureCard
            icon="🛡"
            title="Guardrails"
            subtitle="Safety rules & content filters"
            accentColor={colors.red}
            onPress={() => onNavigate('guardrails')}
          />
        </View>

        <View style={{
          flexDirection: 'row',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <FeatureCard
            icon="🧠"
            title="Self-Learn"
            subtitle="Web research & training"
            accentColor={colors.primary}
            onPress={() => onNavigate('learn')}
            wide
          />
        </View>
      </View>
    </ScrollView>
  )
}
