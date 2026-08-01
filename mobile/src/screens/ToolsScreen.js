import React, { useEffect, useState, useCallback, useRef } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  ActivityIndicator, Alert, Modal, RefreshControl,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { colors, spacing, radius, fontSize } from '../theme/colors'
import Header from '../components/Header'
import * as api from '../api/shaggoth'

function fmt(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

function StatCard({ label, value, color }) {
  return (
    <View style={{
      flex: 1,
      backgroundColor: colors.surfaceCard,
      borderRadius: radius.lg,
      padding: spacing.md,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: colors.border,
    }}>
      <Text style={{
        fontSize: fontSize.xxl,
        fontWeight: '700',
        color: color || colors.primary,
      }}>
        {value}
      </Text>
      <Text style={{
        fontSize: fontSize.xs,
        color: colors.textDim,
        textTransform: 'uppercase',
        letterSpacing: 1,
        marginTop: spacing.xs,
      }}>
        {label}
      </Text>
    </View>
  )
}

function SectionHeader({ title }) {
  return (
    <Text style={{
      color: colors.textSecondary,
      fontSize: fontSize.sm,
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: 1,
      marginBottom: spacing.md,
      marginTop: spacing.xl,
    }}>
      {title}
    </Text>
  )
}

export default function ToolsScreen({ onBack }) {
  const [section, setSection] = useState('learn')
  const [learnStatus, setLearnStatus] = useState(null)
  const [learnHistory, setLearnHistory] = useState([])
  const [facts, setFacts] = useState({})
  const [history, setHistory] = useState([])
  const [urls, setUrls] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [learning, setLearning] = useState(false)
  const [showAddKnowledge, setShowAddKnowledge] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  const [newContent, setNewContent] = useState('')
  const pollRef = useRef(null)

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const loadAll = useCallback(async () => {
    try {
      const [status, histResp, factsResp, memResp] = await Promise.all([
        api.getLearnStatus().catch(() => null),
        api.getLearnSessions().catch(() => ({ sessions: [] })),
        api.getFacts().catch(() => ({ facts: {} })),
        (async () => {
          let sid = await AsyncStorage.getItem('shaggoth_session')
          if (!sid) return { messages: [] }
          return api.getHistory(sid).catch(() => ({ messages: [] }))
        })(),
      ])
      if (status) { setLearnStatus(status); setLearning(status.is_learning) }
      setLearnHistory(histResp.sessions || [])
      setFacts(factsResp.facts || {})
      setHistory(memResp.messages || [])
    } catch {}
  }, [])

  useEffect(() => {
    setLoading(true)
    loadAll().finally(() => setLoading(false))
  }, [loadAll])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    await loadAll()
    setRefreshing(false)
  }, [loadAll])

  const startLearning = async () => {
    const seeds = urls.split('\n').map(u => u.trim()).filter(Boolean)
    if (!seeds.length) { Alert.alert('Error', 'Enter at least one URL'); return }
    setLearning(true)
    try {
      await api.startLearning(seeds, 1, 20, 500)
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.getLearnStatus()
          if (!s.is_learning) {
            clearInterval(pollRef.current)
            pollRef.current = null
            setLearning(false)
            loadAll()
          }
        } catch {
          clearInterval(pollRef.current)
          pollRef.current = null
          setLearning(false)
        }
      }, 3000)
    } catch (e) {
      Alert.alert('Error', e.message)
      setLearning(false)
    }
  }

  const addKnowledgeEntry = async () => {
    if (!newTopic.trim() || !newContent.trim()) {
      Alert.alert('Error', 'Topic and content required')
      return
    }
    try {
      await api.addKnowledge(newTopic.trim(), newContent.trim())
      setShowAddKnowledge(false)
      setNewTopic('')
      setNewContent('')
      Alert.alert('Added', 'Knowledge entry saved.')
    } catch (e) { Alert.alert('Error', e.message) }
  }

  const tabs = [
    { key: 'learn', label: 'Learn', icon: '🧠' },
    { key: 'memory', label: 'Memory', icon: '🛰' },
    { key: 'add', label: 'Add', icon: '📡' },
  ]

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Header title="Tools" onBack={onBack} />

      <View style={{
        flexDirection: 'row',
        paddingHorizontal: spacing.lg,
        gap: spacing.sm,
        marginBottom: spacing.md,
      }}>
        {tabs.map(t => (
          <TouchableOpacity
            key={t.key}
            onPress={() => {
              if (t.key === 'add') { setShowAddKnowledge(true); return }
              setSection(t.key)
            }}
            activeOpacity={0.7}
            style={{
              flex: 1,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              gap: spacing.xs,
              paddingVertical: spacing.sm + 2,
              borderRadius: radius.lg,
              backgroundColor: section === t.key && t.key !== 'add'
                ? colors.primaryMuted
                : colors.surfaceCard,
              borderWidth: 1,
              borderColor: section === t.key && t.key !== 'add'
                ? colors.primaryBorder
                : colors.border,
            }}
          >
            <Text style={{ fontSize: 14 }}>{t.icon}</Text>
            <Text style={{
              color: section === t.key && t.key !== 'add'
                ? colors.primary
                : colors.textSecondary,
              fontSize: fontSize.sm,
              fontWeight: '600',
            }}>
              {t.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: spacing.lg }}
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
          {section === 'learn' && (
            <>
              {learnStatus && (
                <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg }}>
                  <StatCard label="Pages" value={learnStatus.scraper_stats?.pages_stored || 0} />
                  <StatCard label="Words" value={fmt(learnStatus.scraper_stats?.total_words || 0)} color={colors.green} />
                  <StatCard label="Model" value={learnStatus.model_exists ? 'Yes' : 'No'} color={colors.blue} />
                  <StatCard label="Sessions" value={learnStatus.total_sessions || 0} color={colors.yellow} />
                </View>
              )}

              <TextInput
                value={urls}
                onChangeText={setUrls}
                placeholder="Seed URLs (one per line)"
                placeholderTextColor={colors.textDim}
                multiline
                style={{
                  backgroundColor: colors.surfaceCard,
                  color: colors.text,
                  borderRadius: radius.lg,
                  padding: spacing.lg,
                  fontSize: fontSize.md,
                  borderWidth: 1,
                  borderColor: colors.border,
                  minHeight: 100,
                  marginBottom: spacing.md,
                  textAlignVertical: 'top',
                }}
              />

              <TouchableOpacity
                onPress={startLearning}
                disabled={learning}
                activeOpacity={0.8}
                style={{
                  backgroundColor: colors.primary,
                  borderRadius: radius.lg,
                  padding: spacing.lg,
                  alignItems: 'center',
                  opacity: learning ? 0.5 : 1,
                  marginBottom: spacing.xl,
                }}
              >
                <Text style={{
                  color: colors.white,
                  fontSize: fontSize.lg,
                  fontWeight: '600',
                }}>
                  {learning ? 'Learning...' : 'Start Learning'}
                </Text>
              </TouchableOpacity>

              <SectionHeader title="History" />
              {learnHistory.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: spacing.xxl }}>
                  <Text style={{ fontSize: 32, marginBottom: spacing.sm }}>{'📚'}</Text>
                  <Text style={{ color: colors.textDim, fontSize: fontSize.md }}>No learning sessions yet</Text>
                </View>
              ) : (
                [...learnHistory].reverse().map((s, i) => (
                  <View key={i} style={{
                    backgroundColor: colors.surfaceCard,
                    borderRadius: radius.md,
                    padding: spacing.md,
                    marginBottom: spacing.sm,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{
                        color: s.status === 'completed' ? colors.green
                          : s.status === 'failed' ? colors.red
                          : colors.primary,
                        fontSize: fontSize.sm,
                        fontWeight: '600',
                      }}>
                        {(s.status || 'unknown').toUpperCase()}
                      </Text>
                      <Text style={{ color: colors.textDim, fontSize: fontSize.xs }}>
                        {s.pages_scraped || 0}p · {fmt(s.words_learned || 0)}w
                      </Text>
                    </View>
                    {s.error && (
                      <Text style={{ color: colors.red, fontSize: fontSize.xs, marginTop: spacing.xs }}>
                        {s.error}
                      </Text>
                    )}
                  </View>
                ))
              )}
            </>
          )}

          {section === 'memory' && (
            <>
              <SectionHeader title="Facts" />
              {Object.keys(facts).length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: spacing.xxl }}>
                  <Text style={{ fontSize: 32, marginBottom: spacing.sm }}>{'🛰'}</Text>
                  <Text style={{ color: colors.textDim, fontSize: fontSize.md }}>No facts stored</Text>
                </View>
              ) : (
                Object.entries(facts).map(([k, v]) => (
                  <View key={k} style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    backgroundColor: colors.surfaceCard,
                    borderRadius: radius.md,
                    padding: spacing.md,
                    marginBottom: spacing.sm,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}>
                    <Text style={{ color: colors.primary, fontWeight: '600', fontSize: fontSize.md }}>{k}</Text>
                    <Text style={{ color: colors.text, fontSize: fontSize.md, flex: 1, textAlign: 'right', marginLeft: spacing.md }}>{v}</Text>
                  </View>
                ))
              )}

              <SectionHeader title="Recent Messages" />
              {history.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: spacing.xxl }}>
                  <Text style={{ fontSize: 32, marginBottom: spacing.sm }}>{'💬'}</Text>
                  <Text style={{ color: colors.textDim, fontSize: fontSize.md }}>No messages yet</Text>
                </View>
              ) : (
                history.slice(-20).map(m => (
                  <View key={m.id} style={{
                    backgroundColor: colors.surfaceCard,
                    borderRadius: radius.md,
                    padding: spacing.md,
                    marginBottom: spacing.sm,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}>
                    <Text style={{
                      fontSize: fontSize.xs,
                      color: m.role === 'assistant' ? colors.primary : colors.textDim,
                      textTransform: 'uppercase',
                      fontWeight: '600',
                      marginBottom: spacing.xs,
                    }}>
                      {m.role}
                    </Text>
                    <Text style={{ color: colors.text, fontSize: fontSize.md, lineHeight: 20 }}>
                      {m.content}
                    </Text>
                  </View>
                ))
              )}
            </>
          )}
        </ScrollView>
      )}

      <Modal visible={showAddKnowledge} transparent animationType="fade">
        <View style={{
          flex: 1,
          justifyContent: 'center',
          backgroundColor: 'rgba(0,0,0,0.8)',
          padding: spacing.xxl,
        }}>
          <View style={{
            backgroundColor: colors.surface,
            borderRadius: radius.xl,
            padding: spacing.xl,
            borderWidth: 1,
            borderColor: colors.border,
          }}>
            <Text style={{
              fontSize: fontSize.xl,
              fontWeight: '700',
              color: colors.text,
              marginBottom: spacing.lg,
            }}>
              Add Knowledge
            </Text>
            <TextInput
              value={newTopic}
              onChangeText={setNewTopic}
              placeholder="Topic"
              placeholderTextColor={colors.textDim}
              style={{
                backgroundColor: colors.inputBg,
                color: colors.text,
                borderRadius: radius.md,
                padding: spacing.md,
                fontSize: fontSize.lg,
                borderWidth: 1,
                borderColor: colors.inputBorder,
                marginBottom: spacing.md,
              }}
            />
            <TextInput
              value={newContent}
              onChangeText={setNewContent}
              placeholder="Content"
              placeholderTextColor={colors.textDim}
              multiline
              style={{
                backgroundColor: colors.inputBg,
                color: colors.text,
                borderRadius: radius.md,
                padding: spacing.md,
                fontSize: fontSize.lg,
                borderWidth: 1,
                borderColor: colors.inputBorder,
                marginBottom: spacing.lg,
                minHeight: 120,
                textAlignVertical: 'top',
              }}
            />
            <View style={{ flexDirection: 'row', gap: spacing.sm }}>
              <TouchableOpacity
                onPress={() => setShowAddKnowledge(false)}
                style={{
                  flex: 1,
                  padding: spacing.md,
                  borderRadius: radius.md,
                  borderWidth: 1,
                  borderColor: colors.border,
                  alignItems: 'center',
                }}
              >
                <Text style={{ color: colors.textSecondary }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={addKnowledgeEntry}
                style={{
                  flex: 1,
                  padding: spacing.md,
                  borderRadius: radius.md,
                  backgroundColor: colors.primary,
                  alignItems: 'center',
                }}
              >
                <Text style={{ color: colors.white, fontWeight: '600' }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  )
}
