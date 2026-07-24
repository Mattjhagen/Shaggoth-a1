import Foundation
import Supabase

protocol ChatMemoryClientProtocol {
    func fetchMessages(limit: Int) async throws -> [ChatMessage]
    func saveMessage(
        _ message: ChatMessage,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws
    func deleteMessage(id: UUID) async throws
}

protocol ChatSessionMemoryClientProtocol: ChatMemoryClientProtocol {
    func fetchSessions() async throws -> [ChatSession]
    func createSession(title: String, providerId: String?, modelId: String?) async throws -> ChatSession
    func fetchMessages(sessionId: UUID, limit: Int) async throws -> [ChatMessage]
    func fetchCrossSessionMemory(excluding sessionId: UUID, limit: Int) async throws -> [ChatMessage]
    func saveMessage(
        _ message: ChatMessage,
        sessionId: UUID,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws
}

struct ChatSession: Identifiable, Equatable, Codable {
    let id: UUID
    let title: String
    let provider: String?
    let model: String?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, provider, model
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

final class SupabaseChatMemoryClient: ChatSessionMemoryClientProtocol {
    private let client: SupabaseClient
    private let localStore: LocalChatMemoryStore

    init(
        client: SupabaseClient = SupabaseClientManager.shared.client,
        localStore: LocalChatMemoryStore = .shared
    ) {
        self.client = client
        self.localStore = localStore
    }

    // Backward-compatible access used by tests and older installs.
    func fetchMessages(limit: Int = 50) async throws -> [ChatMessage] {
        let rows: [ChatMessageRow] = try await client
            .from("chat_messages")
            .select()
            .is("project_id", value: nil)
            .order("created_at", ascending: false)
            .limit(limit)
            .execute()
            .value
        return rows.reversed().map(\.message)
    }

    func fetchSessions() async throws -> [ChatSession] {
        let userId = try currentUserId()
        do {
            let sessions: [ChatSession] = try await client
                .from("chat_sessions")
                .select()
                .order("updated_at", ascending: false)
                .execute()
                .value
            await localStore.replaceSessions(sessions, userId: userId)
            return sessions
        } catch {
            return await localStore.sessions(userId: userId)
        }
    }

    func createSession(title: String, providerId: String?, modelId: String?) async throws -> ChatSession {
        guard let user = client.auth.currentUser else {
            throw APIError(message: "You must be signed in to create a conversation.", code: 401)
        }

        let rows: [ChatSession] = try await client
            .from("chat_sessions")
            .insert(ChatSessionInsertPayload(
                userId: user.id,
                title: String(title.prefix(80)),
                provider: providerId,
                model: modelId
            ))
            .select()
            .execute()
            .value

        guard let session = rows.first else {
            throw APIError(message: "The conversation could not be created.", code: 500)
        }
        await localStore.upsertSession(session, userId: user.id.uuidString)
        return session
    }

    func fetchMessages(sessionId: UUID, limit: Int = 50) async throws -> [ChatMessage] {
        let userId = try currentUserId()
        do {
            let rows: [ChatMessageRow] = try await client
                .from("chat_messages")
                .select()
                .eq("session_id", value: sessionId)
                .order("created_at", ascending: false)
                .limit(limit)
                .execute()
                .value
            let messages = rows.reversed().map(\.message)
            await localStore.replaceMessages(messages, sessionId: sessionId, userId: userId)
            return messages
        } catch {
            let cached = await localStore.messages(sessionId: sessionId, userId: userId)
            return Array(cached.suffix(limit))
        }
    }

    func fetchCrossSessionMemory(excluding sessionId: UUID, limit: Int = 16) async throws -> [ChatMessage] {
        // Fetch a small recent window and filter locally. RLS guarantees every row
        // belongs to the signed-in user, and the larger window leaves room for the
        // active conversation's messages to be removed.
        let userId = try currentUserId()
        do {
            let rows: [ChatMessageRow] = try await client
                .from("chat_messages")
                .select()
                .order("created_at", ascending: false)
                .limit(max(limit * 5, 50))
                .execute()
                .value

            return rows
                .filter { $0.sessionId != sessionId && $0.role != .system }
                .prefix(limit)
                .reversed()
                .map(\.message)
        } catch {
            return await localStore.crossSessionMessages(
                excluding: sessionId,
                limit: limit,
                userId: userId
            )
        }
    }

    func saveMessage(
        _ message: ChatMessage,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws {
        try await save(message, sessionId: nil, providerId: providerId, modelId: modelId, projectId: projectId)
    }

    func saveMessage(
        _ message: ChatMessage,
        sessionId: UUID,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws {
        try await save(message, sessionId: sessionId, providerId: providerId, modelId: modelId, projectId: projectId)
        try await client
            .from("chat_sessions")
            .update(["updated_at": ISO8601DateFormatter().string(from: message.timestamp)])
            .eq("id", value: sessionId)
            .execute()
    }

    private func save(
        _ message: ChatMessage,
        sessionId: UUID?,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws {
        guard let user = client.auth.currentUser else {
            throw APIError(message: "You must be signed in to save chat memory.", code: 401)
        }

        try await client
            .from("chat_messages")
            .insert(ChatMessageInsertPayload(
                id: message.id,
                userId: user.id,
                projectId: projectId.flatMap(UUID.init(uuidString:)),
                sessionId: sessionId,
                role: message.role.rawValue,
                content: message.content,
                provider: providerId,
                model: modelId,
                createdAt: message.timestamp
            ))
            .execute()

        await localStore.appendMessage(
            message,
            sessionId: sessionId,
            userId: user.id.uuidString
        )
    }

    func deleteMessage(id: UUID) async throws {
        try await client
            .from("chat_messages")
            .delete(returning: .minimal)
            .eq("id", value: id)
            .execute()
        if let user = client.auth.currentUser {
            await localStore.deleteMessage(id: id, userId: user.id.uuidString)
        }
    }

    private func currentUserId() throws -> String {
        guard let user = client.auth.currentUser else {
            throw APIError(message: "You must be signed in to load chat memory.", code: 401)
        }
        return user.id.uuidString
    }
}

private struct ChatMessageRow: Decodable {
    let id: UUID
    let sessionId: UUID?
    let role: ChatMessage.MessageRole
    let content: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case sessionId = "session_id"
        case createdAt = "created_at"
    }

    var message: ChatMessage {
        ChatMessage(id: id, role: role, content: content, timestamp: createdAt)
    }
}

private struct ChatMessageInsertPayload: Encodable {
    let id: UUID
    let userId: UUID
    let projectId: UUID?
    let sessionId: UUID?
    let role: String
    let content: String
    let provider: String?
    let model: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case projectId = "project_id"
        case sessionId = "session_id"
        case role, content, provider, model
        case createdAt = "created_at"
    }
}

private struct ChatSessionInsertPayload: Encodable {
    let userId: UUID
    let title: String
    let provider: String?
    let model: String?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case title, provider, model
    }
}

actor LocalChatMemoryStore {
    static let shared = LocalChatMemoryStore()

    private struct Snapshot: Codable {
        var users: [String: UserCache] = [:]
    }

    private struct UserCache: Codable {
        var sessions: [ChatSession] = []
        var messagesBySession: [String: [ChatMessage]] = [:]
    }

    private let fileURL: URL
    private var snapshot: Snapshot

    private init() {
        let base = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first ?? FileManager.default.temporaryDirectory
        fileURL = base
            .appendingPathComponent("Archon", isDirectory: true)
            .appendingPathComponent("local-chat-memory.json")

        if let data = try? Data(contentsOf: fileURL),
           let decoded = try? JSONDecoder().decode(Snapshot.self, from: data) {
            snapshot = decoded
        } else {
            snapshot = Snapshot()
        }
    }

    func sessions(userId: String) -> [ChatSession] {
        snapshot.users[userId]?.sessions.sorted { $0.updatedAt > $1.updatedAt } ?? []
    }

    func replaceSessions(_ sessions: [ChatSession], userId: String) {
        var cache = snapshot.users[userId] ?? UserCache()
        cache.sessions = Array(sessions.sorted { $0.updatedAt > $1.updatedAt }.prefix(100))
        snapshot.users[userId] = cache
        persist()
    }

    func upsertSession(_ session: ChatSession, userId: String) {
        var cache = snapshot.users[userId] ?? UserCache()
        cache.sessions.removeAll { $0.id == session.id }
        cache.sessions.insert(session, at: 0)
        cache.sessions = Array(cache.sessions.prefix(100))
        snapshot.users[userId] = cache
        persist()
    }

    func messages(sessionId: UUID, userId: String) -> [ChatMessage] {
        snapshot.users[userId]?.messagesBySession[sessionId.uuidString] ?? []
    }

    func replaceMessages(_ messages: [ChatMessage], sessionId: UUID, userId: String) {
        var cache = snapshot.users[userId] ?? UserCache()
        cache.messagesBySession[sessionId.uuidString] = Array(
            messages.sorted { $0.timestamp < $1.timestamp }.suffix(100)
        )
        snapshot.users[userId] = cache
        persist()
    }

    func appendMessage(
        _ message: ChatMessage,
        sessionId: UUID?,
        userId: String
    ) {
        var cache = snapshot.users[userId] ?? UserCache()
        let key = sessionId?.uuidString ?? "legacy"
        var messages = cache.messagesBySession[key] ?? []
        messages.removeAll { $0.id == message.id }
        messages.append(message)
        cache.messagesBySession[key] = Array(
            messages.sorted { $0.timestamp < $1.timestamp }.suffix(100)
        )
        snapshot.users[userId] = cache
        persist()
    }

    func crossSessionMessages(
        excluding sessionId: UUID,
        limit: Int,
        userId: String
    ) -> [ChatMessage] {
        guard let cache = snapshot.users[userId] else { return [] }
        return cache.messagesBySession
            .filter { $0.key != sessionId.uuidString }
            .flatMap(\.value)
            .filter { $0.role != .system }
            .sorted { $0.timestamp > $1.timestamp }
            .prefix(limit)
            .reversed()
    }

    func deleteMessage(id: UUID, userId: String) {
        guard var cache = snapshot.users[userId] else { return }
        for key in cache.messagesBySession.keys {
            cache.messagesBySession[key]?.removeAll { $0.id == id }
        }
        snapshot.users[userId] = cache
        persist()
    }

    func clear(userId: String) {
        snapshot.users.removeValue(forKey: userId)
        persist()
    }

    private func persist() {
        do {
            try FileManager.default.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let data = try JSONEncoder().encode(snapshot)
            try data.write(to: fileURL, options: .atomic)
            try? FileManager.default.setAttributes(
                [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
                ofItemAtPath: fileURL.path
            )
            var protectedFileURL = fileURL
            var resourceValues = URLResourceValues()
            resourceValues.isExcludedFromBackup = true
            try? protectedFileURL.setResourceValues(resourceValues)
        } catch {
            // Cloud memory remains authoritative if the local cache cannot be written.
        }
    }
}
