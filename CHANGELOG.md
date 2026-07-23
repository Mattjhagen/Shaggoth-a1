# Changelog

All notable changes to Archon Mobile will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-07-23

### Added

- Complete onboarding flow with 4-page introduction
- Email authentication (sign in / sign up)
- Apple Sign In with ASWebAuthenticationSession
- Keychain-backed session storage
- Project dashboard with list view, search, create, and delete
- AI Builder chat with streaming responses
- Task event timeline with real-time updates
- Model/provider selection
- Retry and cancel task support
- Code browser with file tree navigation
- Syntax highlighting for Swift, JavaScript, TypeScript, HTML, CSS, JSON
- Live preview with WKWebView
- Settings: account, appearance, API config, about
- Dark/light/system appearance modes
- Pull-to-refresh on dashboard
- Empty states for every screen
- Loading skeletons and progress indicators
- Error states with dismissible banners
- Haptic feedback support
- Smooth animations and transitions
- Dynamic Type support
- VoiceOver accessibility labels
- 44pt minimum touch targets
- MockAPIClient with rich demo data
- Unit tests for all view models
- Decoding tests for all model types
- API error decoding tests
- Keychain storage tests
- Polling behavior tests
- Mock flow end-to-end tests
