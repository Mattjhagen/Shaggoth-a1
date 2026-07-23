import Foundation

// MARK: - Chat Message Model

struct ChatMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let content: String
    let timestamp: Date

    enum MessageRole: String, Codable {
        case user
        case assistant
        case system
    }

    init(id: UUID = UUID(), role: MessageRole, content: String, timestamp: Date = Date()) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
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
