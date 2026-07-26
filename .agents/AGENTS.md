# Shaggoth iOS Project Context

This file serves as a persistent context for agents working on this project across different sessions.

## Project Overview
* **Goal**: A ChatGPT-style conversational AI client for iOS, backed by Supabase (database/auth) and a homegrown AI backend called `Shaggoth-a1`.
* **Origin**: This project was originally an IDE/Builder app named "ArchonMobile" but is currently being refactored into the Shaggoth client.

## Architecture
1. **Authentication & Database (Supabase)**:
    * Handles user authentication.
    * Source of truth for history. We use the `chat_sessions` and `chat_messages` tables.
    * Uses `SupabaseChatMemoryClient` for data operations.
2. **AI Inference (Shaggoth-a1)**:
    * The homegrown AI backend (`shaggoth-a1`) is used purely as the inference engine.
    * Communicates via `ShaggothClient` using `POST /chat`.
    * Requires a `shaggothAPIKey` (managed in `SettingsViewModel` and passed as a Bearer token).

## Current State
* Refactored `MainTabView` to remove IDE/Builder tools. It now features `Chat`, `History`, and `Settings`.
* Refactored `ChatView` and `ChatViewModel` into a standard ChatGPT-like interface.
* Rewired to ensure user messages are saved to Supabase, sent to Shaggoth for an AI response, and the response is saved back to Supabase.
* Created a sleek, glowing "S" cyan-blue app icon.

## Next Steps
* Update the Xcode project to use the newly generated app icon.
* Validate the end-to-end flow with a live Shaggoth-a1 local server.
