import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity,
  ActivityIndicator, TextInput, RefreshControl,
} from 'react-native'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import CategoryChip from '../components/CategoryChip'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

const TOOLS = [
  { key: 'wiki', icon: '🪐', title: 'Wikipedia', desc: 'Look up topics across the galaxy', category: 'Research' },
  { key: 'time', icon: '⏱', title: 'Time', desc: 'Get current stardate info', category: 'Utility' },
  { key: 'calc', icon: '🔢', title: 'Calculator', desc: 'Evaluate math expressions', category: 'Utility' },
  { key: 'research', icon: '🔭', title: 'Research', desc: 'Autonomous topic research', category: 'Research' },
  { key: 'remember', icon: '💾', title: 'Remember', desc: 'Store facts in memory banks', category: 'Memory' },
  { key: 'teach', icon: '📡', title: 'Teach', desc: 'Transmit knowledge directly', category: 'Knowledge' },
  { key: 'know', icon: '🧠', title: 'What I Know', desc: 'Query the knowledge base', category: 'Knowledge' },
  { key: 'learned', icon: '📊', title: 'What I Learned', desc: 'Recent acquisition history', category: 'Research' },
  { key: 'facts', icon: '🛰', title: 'Recall Facts', desc: 'View stored data banks', category: 'Memory' },
]

const CATEGORIES = ['All', 'Research', 'Knowledge', 'Memory', 'Utility']

export default function ExploreScreen({ onNavigate, onBack }) {
  const [category, setCategory] = useState('All')
  const [knowledge, setKnowledge] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const loadKnowledge = useCallback(async () => {
    try {
      const d = await api.getKnowledge()
      setKnowledge(d.entries || [])
    } catch {}
  }, [])

  useEffect(() => {
    loadKnowledge().finally(() => setLoading(false))
  }, [loadKnowledge])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    await loadKnowledge()
    setRefreshing(false)
  }, [loadKnowledge])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return
    setLoading(true)
    try {
      const d = await api.searchKnowledge(searchQuery)
      setKnowledge((d.results || []).map(r => ({
        topic: r.topic,
        content: r.content,
        word_count: r.content ? r.content.split(' ').length : 0,
        score: r.score,
      })))
    } catch {}
    setLoading(false)
  }, [searchQuery])

  const filteredTools = category === 'All'
    ? TOOLS
    : TOOLS.filter(t => t.category === category)

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Explore" onBack={onBack} />

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ maxHeight: 50, paddingHorizontal: spacing.lg, marginBottom: spacing.md }}
        contentContainerStyle={{ alignItems: 'center', gap: spacing.xs }}
      >
        {CATEGORIES.map(cat => (
          <CategoryChip
            key={cat}
            label={cat}
            active={category === cat}
            onPress={() => setCategory(cat)}
          />
        ))}
      </ScrollView>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xl }}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        <Text style={{
          color: colors.textSecondary,
          fontSize: fontSize.md,
          fontWeight: '600',
          marginBottom: spacing.md,
        }}>
          {category}
        </Text>

        <View style={{
          flexDirection: 'row',
          flexWrap: 'wrap',
          gap: spacing.md,
          marginBottom: spacing.xxl,
        }}>
          {filteredTools.map(tool => (
            <TouchableOpacity
              key={tool.key}
              activeOpacity={0.8}
              onPress={() => onNavigate('chat', { command: tool.key })}
              style={{
                width: '47%',
                backgroundColor: colors.surfaceCard,
                borderRadius: radius.xl,
                padding: spacing.lg,
                borderWidth: 1,
                borderColor: colors.border,
                minHeight: 150,
                justifyContent: 'space-between',
              }}
            >
              <View>
                <View style={{
                  width: 40,
                  height: 40,
                  borderRadius: 12,
                  backgroundColor: colors.primaryMuted,
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: spacing.md,
                }}>
                  <Text style={{ fontSize: 20 }}>{tool.icon}</Text>
                </View>
                <Text style={{
                  color: colors.text,
                  fontSize: fontSize.md,
                  fontWeight: '600',
                  marginBottom: spacing.xs,
                }}>
                  {tool.title}
                </Text>
                <Text style={{
                  color: colors.textSecondary,
                  fontSize: fontSize.sm,
                  lineHeight: 16,
                }}>
                  {tool.desc}
                </Text>
              </View>
              <View style={{
                alignSelf: 'flex-end',
                marginTop: spacing.sm,
              }}>
                <View style={{
                  width: 28,
                  height: 28,
                  borderRadius: 14,
                  backgroundColor: colors.surfaceLight,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderWidth: 1,
                  borderColor: colors.borderLight,
                }}>
                  <Text style={{ color: colors.textSecondary, fontSize: 14 }}>{'▸'}</Text>
                </View>
              </View>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={{
          color: colors.textSecondary,
          fontSize: fontSize.md,
          fontWeight: '600',
          marginBottom: spacing.md,
        }}>
          Knowledge Base
        </Text>

        <View style={{
          backgroundColor: colors.surfaceCard,
          borderRadius: radius.lg,
          padding: spacing.md,
          borderWidth: 1,
          borderColor: colors.border,
          marginBottom: spacing.md,
          flexDirection: 'row',
          alignItems: 'center',
        }}>
          <Text style={{ color: colors.textDim, fontSize: fontSize.md, marginRight: spacing.sm }}>{'🔍'}</Text>
          <TextInput
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search knowledge..."
            placeholderTextColor={colors.textDim}
            style={{
              color: colors.text,
              fontSize: fontSize.md,
              padding: 0,
              flex: 1,
            }}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
        ) : knowledge.length === 0 ? (
          <View style={{ alignItems: 'center', marginTop: 40 }}>
            <Text style={{ fontSize: 48, marginBottom: spacing.md }}>{'🌌'}</Text>
            <Text style={{ color: colors.textDim, fontSize: fontSize.lg, textAlign: 'center' }}>
              No knowledge entries yet
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: fontSize.sm, textAlign: 'center', marginTop: spacing.xs }}>
              Use the Learn tool to add knowledge
            </Text>
          </View>
        ) : (
          knowledge.slice(0, 10).map((entry, i) => (
            <View
              key={i}
              style={{
                backgroundColor: colors.surfaceCard,
                borderRadius: radius.lg,
                padding: spacing.lg,
                marginBottom: spacing.sm,
                borderWidth: 1,
                borderColor: colors.border,
              }}
            >
              <Text style={{
                color: colors.primary,
                fontWeight: '600',
                fontSize: fontSize.md,
                marginBottom: spacing.xs,
              }}>
                {entry.topic}
                {entry.score ? (
                  <Text style={{ color: colors.textDim, fontSize: fontSize.xs }}>
                    {' '}({entry.score})
                  </Text>
                ) : null}
              </Text>
              <Text
                style={{
                  color: colors.textSecondary,
                  fontSize: fontSize.sm,
                  lineHeight: 18,
                }}
                numberOfLines={3}
              >
                {entry.content || `${entry.word_count} words`}
              </Text>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  )
}
