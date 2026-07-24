import Foundation
import Supabase

final class SupabaseAIGatewayClient: AIClientProtocol {
    private struct GatewayRequest: Encodable {
        let action: String
        let messages: [APIMessage]?
        let model: String?
        let provider: String?
        let maxTokens: Int?
        let reasoningEffort: String?

        enum CodingKeys: String, CodingKey {
            case action, messages, model, provider
            case maxTokens = "max_tokens"
            case reasoningEffort = "reasoning_effort"
        }
    }

    private struct ProvidersResponse: Decodable {
        let providers: [ProviderMetadata]
    }

    private let client: SupabaseClient

    init(client: SupabaseClient = SupabaseClientManager.shared.client) {
        self.client = client
    }

    func fetchProviders() async throws -> [ProviderMetadata] {
        let request = GatewayRequest(
            action: "providers",
            messages: nil,
            model: nil,
            provider: nil,
            maxTokens: nil,
            reasoningEffort: nil
        )
        let response: ProvidersResponse = try await client.functions.invoke(
            "ai-gateway",
            options: FunctionInvokeOptions(body: request)
        )
        return response.providers
    }

    func sendMessage(
        _ message: String,
        history: [APIMessage],
        model: String,
        provider: String
    ) async throws -> ChatAPIResponse {
        var messages = history
        if messages.last?.role != "user" || messages.last?.content != message {
            messages.append(APIMessage(role: "user", content: message))
        }

        let request = GatewayRequest(
            action: "chat",
            messages: messages,
            model: model,
            provider: provider,
            maxTokens: 4096,
            reasoningEffort: "medium"
        )
        return try await client.functions.invoke(
            "ai-gateway",
            options: FunctionInvokeOptions(body: request)
        )
    }
}
