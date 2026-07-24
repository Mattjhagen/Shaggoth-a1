import Foundation

// MARK: - Chat API Message (backend-compatible)

/// Message payload compatible with the backend's /api/ai/chat endpoint.
struct APIMessage: Encodable {
    let role: String
    let content: String
}

struct AIFallbackModel: Encodable {
    let provider: String
    let model: String
}

/// Request body for the backend's chat endpoint.
struct ChatAPIRequest: Encodable {
    let messages: [APIMessage]
    let model: String
    let provider: String
    let maxTokens: Int?
    let temperature: Double?
    let reasoningEffort: String?
    let fallbackModels: [AIFallbackModel]?

    enum CodingKeys: String, CodingKey {
        case messages, model, provider
        case maxTokens = "max_tokens"
        case temperature
        case reasoningEffort = "reasoning_effort"
        case fallbackModels = "fallback_models"
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

struct PersistentAIJob: Decodable {
    struct Log: Decodable, Identifiable {
        let id: String
        let sequence: Int
        let createdAt: Date
        let kind: String
        let summary: String

        enum CodingKeys: String, CodingKey {
            case id, sequence, kind, summary
            case createdAt = "created_at"
        }
    }

    enum Status: String, Decodable {
        case queued
        case running
        case completed
        case failed
        case timedOut = "timed_out"

        var isActive: Bool {
            self == .queued || self == .running
        }
    }

    let id: String
    let status: Status
    let response: ChatAPIResponse?
    let error: String?
    let logs: [Log]?
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case id, status, response, error, logs
        case expiresAt = "expires_at"
    }
}
