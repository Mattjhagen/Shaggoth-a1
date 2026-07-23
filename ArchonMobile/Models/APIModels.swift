import Foundation

// MARK: - Chat API Message (backend-compatible)

/// Message payload compatible with the backend's /api/ai/chat endpoint.
struct APIMessage: Encodable {
    let role: String
    let content: String
}

/// Request body for the backend's chat endpoint.
struct ChatAPIRequest: Encodable {
    let messages: [APIMessage]
    let model: String
    let provider: String
    let maxTokens: Int?
    let temperature: Double?
    let reasoningEffort: String?

    enum CodingKeys: String, CodingKey {
        case messages, model, provider
        case maxTokens = "max_tokens"
        case temperature
        case reasoningEffort = "reasoning_effort"
    }
}

/// Response from the backend's chat endpoint.
struct ChatAPIResponse: Decodable {
    let content: String
    let model: String
    let provider: String
    let tokensUsed: APITokenUsage?
    let reasoningEffort: String?
    let creditUnits: Int?

    enum CodingKeys: String, CodingKey {
        case content, model, provider
        case tokensUsed = "tokens_used"
        case reasoningEffort = "reasoning_effort"
        case creditUnits = "credit_units"
    }
}

struct APITokenUsage: Decodable {
    let input: Int
    let output: Int
}
