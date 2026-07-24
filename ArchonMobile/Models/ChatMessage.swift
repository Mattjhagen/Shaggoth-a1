import Foundation

// MARK: - Chat Message Model

struct ChatMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let content: String
    let timestamp: Date
    /// Technical details hidden behind the "under the hood" disclosure.
    /// Optional so previously saved conversations decode unchanged.
    var details: BuildDetails?
    /// Attached image data (JPEG), kept out of Codable so chat memory stays
    /// lightweight — attachments display for the current session only.
    var localImageData: [Data]?

    enum CodingKeys: String, CodingKey {
        case id, role, content, timestamp, details
    }

    enum MessageRole: String, Codable {
        case user
        case assistant
        case system
    }

    /// What actually happened behind a friendly assistant reply — the model
    /// that served it, token counts, and elapsed time. Users never need this,
    /// but the curious can peek.
    struct BuildDetails: Codable, Equatable {
        let provider: String
        let model: String
        let inputTokens: Int?
        let outputTokens: Int?
        let elapsedSeconds: Double?
    }

    init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        details: BuildDetails? = nil,
        localImageData: [Data]? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.details = details
        self.localImageData = localImageData
    }

    static func == (lhs: ChatMessage, rhs: ChatMessage) -> Bool {
        lhs.id == rhs.id
    }
}

struct ChatRequest: Encodable {
    let messages: [ChatMessagePayload]
    let model: String?
    let provider: String?
    let maxTokens: UInt32?
    let temperature: Float?
    let reasoningEffort: String?

    enum CodingKeys: String, CodingKey {
        case messages, model, provider
        case maxTokens = "max_tokens"
        case temperature
        case reasoningEffort = "reasoning_effort"
    }
}

struct ChatMessagePayload: Encodable {
    let role: String
    let content: String
}

struct ChatResponse: Decodable {
    let content: String
    let model: String
    let provider: String
    let tokensUsed: TokenUsage?
    let reasoningEffort: String?

    enum CodingKeys: String, CodingKey {
        case content, model, provider
        case tokensUsed = "tokens_used"
        case reasoningEffort = "reasoning_effort"
    }
}

struct TokenUsage: Decodable {
    let input: Int
    let output: Int
}
