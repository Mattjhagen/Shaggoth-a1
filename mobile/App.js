import React, { useEffect, useState } from 'react'
import { View, StatusBar, SafeAreaView, Platform } from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Notifications from 'expo-notifications'
import * as Device from 'expo-device'
import * as Linking from 'expo-linking'
import { colors } from './src/theme/colors'
import TabBar from './src/components/TabBar'
import HomeScreen from './src/screens/HomeScreen'
import ChatScreen from './src/screens/ChatScreen'
import ExploreScreen from './src/screens/ExploreScreen'
import ToolsScreen from './src/screens/ToolsScreen'
import SettingsScreen from './src/screens/SettingsScreen'
import * as api from './src/api/shaggoth'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
})

export default function App() {
  const [tab, setTab] = useState('home')
  const [subScreen, setSubScreen] = useState(null)
  const [connected, setConnected] = useState(false)
  const [assistMode, setAssistMode] = useState(false)

  const checkConnection = async () => {
    try {
      await api.health()
      setConnected(true)
    } catch {
      setConnected(false)
    }
  }

  useEffect(() => {
    api.initStorage().then(checkConnection)
    const interval = setInterval(checkConnection, 30000)

    Linking.getInitialURL().then((url) => {
      if (url && url.includes('assistMode')) {
        setAssistMode(true)
        setSubScreen({ screen: 'chat', params: {} })
      }
    })

    async function setupPush() {
      if (!Device.isDevice) return
      const { status: existing } = await Notifications.getPermissionsAsync()
      let final = existing
      if (existing !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync()
        final = status
      }
      if (final !== 'granted') return
      const tokenData = await Notifications.getExpoPushTokenAsync()
      api.registerPushToken(tokenData.data, Platform.OS).catch(() => {})
    }
    setupPush()

    return () => clearInterval(interval)
  }, [])

  const navigate = (screen, params) => {
    if (screen === 'settings') {
      setSubScreen(null)
      setTab('settings')
      return
    }
    if (['chat', 'knowledge', 'learn'].includes(screen)) {
      setSubScreen({ screen, params })
    }
  }

  const goBack = () => {
    setSubScreen(null)
    setAssistMode(false)
  }

  const renderContent = () => {
    if (subScreen) {
      switch (subScreen.screen) {
        case 'chat':
          return <ChatScreen onBack={goBack} assistMode={assistMode} />
        case 'knowledge':
          return <ExploreScreen onNavigate={navigate} onBack={goBack} />
        case 'learn':
          return <ToolsScreen onBack={goBack} />
      }
    }

    switch (tab) {
      case 'home':
        return <HomeScreen onNavigate={navigate} connected={connected} />
      case 'explore':
        return <ExploreScreen onNavigate={navigate} />
      case 'tools':
        return <ToolsScreen />
      case 'settings':
        return <SettingsScreen connected={connected} onConnectionChange={setConnected} />
      default:
        return <HomeScreen onNavigate={navigate} connected={connected} />
    }
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />
      <View style={{ flex: 1 }}>
        {renderContent()}
      </View>
      {!subScreen && (
        <TabBar tab={tab} onTab={(t) => { setSubScreen(null); setTab(t) }} />
      )}
    </SafeAreaView>
  )
}
