# Shaggoth Mobile

ChatGPT-style iOS (and Android) app for Shaggoth AI.

## Setup

```bash
cd mobile
npm install
npx expo start
```

This starts the Expo dev server. Install [Expo Go](https://expo.dev/go) on your phone and scan the QR code — or press `i` for the iOS simulator.

## Configuration

Open the **Settings** tab in the app to set:
- **API URL** — your Shaggoth backend (default: `http://100.103.3.35:8420`)
- **API Key** — optional, if auth is enabled on the server

## Architecture

```
mobile/
  App.js           — Main app with navigation and all screens
  src/
    api/
      shaggoth.js  — API client (chat, streaming, health, etc.)
  package.json
  app.json         — Expo config
```

## Features

- Real-time streaming responses (SSE)
- Session management (conversations tied to a persistent session ID)
- Dark theme
- Personality/info screen
- Configurable server URL and API key
- Markdown rendering in messages
