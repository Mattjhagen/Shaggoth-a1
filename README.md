# Archon Mobile

A complete, polished iOS app for building apps with AI. Describe what you want in chat, watch an AI agent build it step by step, browse and edit the generated code, and manage your projects.

## Screens

- **Onboarding** — Polished 4-page onboarding with brand introduction
- **Authentication** — Email + Apple Sign In with Keychain-backed sessions
- **Dashboard** — Project list/grid with search, create, delete, pull-to-refresh, empty states
- **AI Builder** — Streaming chat with task timeline, retry/cancel, model selection
- **Code Browser** — File tree + syntax-highlighted editor (Swift/JS/TS/HTML/CSS/JSON)
- **Live Preview** — WKWebView rendering for HTML apps
- **Settings** — Account, appearance (light/dark/system), API config, about, licenses

## Architecture

```
┌─────────────────────────────────────────────┐
│                 ArchonMobileApp              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Onboard │→ │  Auth    │→ │ MainTab    │  │
│  └─────────┘  └──────────┘  └────────────┘  │
└─────────────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌──────────┐
    │Dashboard│  │ Builder │  │  Code    │
    │   VM    │  │   VM    │  │ Browser  │
    └────┬────┘  └────┬────┘  │   VM     │
         │             │      └────┬─────┘
         ▼             ▼           ▼
    ┌─────────────────────────────────────┐
    │         APIClientProtocol           │
    │  ┌───────────┐  ┌───────────────┐   │
    │  │  MockAPI   │  │ Authenticated │   │
    │  │  Client    │  │   APIClient    │   │
    │  └───────────┘  └───────────────┘   │
    └─────────────────────────────────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
    ┌──────────────┐  ┌──────────────┐
    │ Keychain     │  │  Supabase    │
    │ SessionStore │  │   Client     │
    └──────────────┘  └──────────────┘
```

## Build Instructions

### Prerequisites

- macOS with a current App Store-supported Xcode release
- [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`)

### Setup

1. **Clone and configure:**

```bash
git clone https://github.com/Mattjhagen/archon-ios.git
cd archon-ios
cp Config/Config.example.xcconfig Config/Config.xcconfig
```

2. **Edit `Config/Config.xcconfig`** with your Supabase credentials:

```
SUPABASE_ANON_KEY = your_publishable_key_here
SUPABASE_URL = https:/$()/your-project.supabase.co
API_BASE_URL = https:/$()/archon-ide-pacmac.fly.dev/api
```

3. **Generate the Xcode project:**

```bash
xcodegen generate
```

4. **Open and run:**

```bash
open ArchonMobile.xcodeproj
```

Select an iOS 17+ simulator and press Cmd+R.

Production builds use the authenticated Supabase and Fly services. `MockAPIClient` is retained only for unit tests and SwiftUI development.

## TestFlight

See [TESTFLIGHT.md](TESTFLIGHT.md) for the verified release checklist, App Store Connect metadata, and upload steps.

## Project Structure

```
ArchonMobile/
├── App/                    # App entry, main tab view
├── Config/                 # Environment, xcconfig
├── DesignSystem/           # Colors, typography, spacing tokens
├── Models/                 # Codable models, API types
├── Network/                # APIClient protocol, MockAPIClient
├── Services/               # Keychain, Supabase client, Auth
├── ViewModels/             # ObservableObject view models
└── Views/
    ├── Onboarding/         # Welcome flow, auth
    ├── Dashboard/          # Project list/grid
    ├── Builder/            # AI chat, event timeline
    ├── CodeBrowser/        # File tree, syntax editor
    ├── Preview/            # WKWebView preview
    └── Settings/           # App settings
```

## Tech Stack

- **SwiftUI** with iOS 17+ deployment target
- **async/await** for all async operations
- **Supabase Swift SDK** for auth and backend
- **XcodeGen** for project generation
- **Keychain** for secure session storage
- **UIKit** backing for syntax editor (UITextView)

## Design Principles

- **Dark-mode-first** with automatic light mode adaptation
- **Consistent design tokens** in `DesignSystem.swift`
- **44pt minimum touch targets** for accessibility
- **Dynamic Type** support across all screens
- **VoiceOver labels** on every interactive element

## License

MIT License — Copyright (c) 2024 Matt Hagen
