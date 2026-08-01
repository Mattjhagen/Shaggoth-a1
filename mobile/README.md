# Shaggoth Mobile

Expo React Native app for Shaggoth AI — voice-enabled, dark-themed, with Android digital assistant integration.

## Branch

Build from the main development branch:

```bash
git checkout claude/ai-model-guardrails-platform-o6b50g
```

## Setup

```bash
cd mobile
npm install
npx expo start
```

This starts the Expo dev server. Install [Expo Go](https://expo.dev/go) on your phone and scan the QR code, or press `i` / `a` for iOS simulator / Android emulator.

## Building for Device

### Development build (recommended for voice features)

Voice input (speech-to-text) and the Android assistant require a native build — they won't work in Expo Go.

```bash
# Install EAS CLI
npm install -g eas-cli

# Log in to your Expo account
eas login

# Build for Android (APK for sideloading)
eas build --platform android --profile preview

# Build for iOS (requires Apple Developer account)
eas build --platform ios --profile preview
```

### Production build

```bash
# Android (AAB for Play Store)
eas build --platform android --profile production

# iOS (IPA for App Store)
eas build --platform ios --profile production
```

### Local build (no EAS account needed)

```bash
# Generate native projects
npx expo prebuild

# Build Android locally (requires Android SDK)
cd android && ./gradlew assembleRelease

# Build iOS locally (requires Xcode)
cd ios && xcodebuild -workspace ShaggothMobile.xcworkspace -scheme ShaggothMobile archive
```

## Android Digital Assistant

After installing on Android, go to **Settings > Apps > Default apps > Digital assistant app** and select **Shaggoth AI**. Pressing and holding the side button will launch Shaggoth directly into voice chat mode.

## Configuration

Open the **Settings** tab in the app to set:
- **API URL** — your Shaggoth backend (default: `http://100.103.3.35:8420`)
- **API Key** — optional, if auth is enabled on the server

## Architecture

```
mobile/
  App.js                        — Entry point, navigation, push notifications
  app.json                      — Expo config (icons, plugins, permissions)
  plugins/
    withAndroidAssistant.js      — Config plugin: Android VoiceInteractionService
  src/
    api/
      shaggoth.js                — API client (chat, streaming, health, etc.)
    hooks/
      useVoice.js                — TTS (expo-speech) + STT (expo-speech-recognition)
    components/
      Header.js                  — Reusable header with back button
      TabBar.js                  — Bottom tab bar (Home, Explore, Tools, Settings)
      FeatureCard.js             — Card component with icon and arrow
      CategoryChip.js            — Filterable pill/chip component
    screens/
      HomeScreen.js              — Landing with status + feature cards
      ChatScreen.js              — Chat UI with voice input/output
      ExploreScreen.js           — Tool browser + knowledge search
      ToolsScreen.js             — Self-learning controls + memory
      SettingsScreen.js          — API config, guardrails, personality
    theme/
      colors.js                  — Design tokens (colors, spacing, radius, fontSize)
```

## Features

- Voice input (speech-to-text) with animated mic button
- Text-to-speech response playback with auto-speak toggle
- Android digital assistant (side button launch)
- Real-time streaming responses
- Session management with persistent session IDs
- Dark theme with alien/space aesthetic
- Shaggoth eye app icon (matches PWA favicon)
- Push notifications via Expo
- Configurable server URL and API key
