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
    let projectId: String?
    let maxTokens: Int?
    let temperature: Double?
    let reasoningEffort: String?
    let fallbackModels: [AIFallbackModel]?

    enum CodingKeys: String, CodingKey {
        case messages, model, provider
        case projectId = "project_id"
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
    var generatedFiles: [GeneratedProjectFile]? = nil

    enum CodingKeys: String, CodingKey {
        case content, model, provider
        case tokensUsed
        case reasoningEffort
        case creditUnits
        case generatedFiles
    }
}

struct GeneratedProjectFile: Decodable, Equatable {
    let path: String
    let content: String
    let mimeType: String

    enum CodingKeys: String, CodingKey {
        case path, content
        case mimeType
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
            case createdAt
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
    /// Older gateway deployments did not include an expiry in the initial
    /// accepted-job response. Treat it as optional so a successful 202 can
    /// always be resumed rather than failing during JSON decoding.
    let expiresAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, status, response, error, logs
        case expiresAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        // `id` is the only field needed to poll an accepted build. Keep the
        // client compatible with gateway versions that omit or evolve the
        // in-progress metadata rather than failing before the model runs.
        id = try container.decode(String.self, forKey: .id)
        status = (try? container.decode(Status.self, forKey: .status)) ?? .queued
        response = try? container.decodeIfPresent(ChatAPIResponse.self, forKey: .response)
        error = try? container.decodeIfPresent(String.self, forKey: .error)
        logs = try? container.decodeIfPresent([Log].self, forKey: .logs)
        expiresAt = try? container.decodeIfPresent(Date.self, forKey: .expiresAt)
    }
}
