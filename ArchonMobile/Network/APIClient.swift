import Foundation

// MARK: - Projects Client Protocol

protocol ProjectsClientProtocol {
    func fetchProjects() async throws -> [ArchonProject]
    func createProject(_ request: CreateProjectRequest) async throws -> ArchonProject
    func updateProject(id: String, _ request: UpdateProjectRequest) async throws -> ArchonProject
    func deleteProject(id: String) async throws
}

protocol AIClientProtocol {
    func sendMessage(_ message: String, history: [APIMessage], model: String, provider: String) async throws -> ChatAPIResponse
    func fetchProviders() async throws -> [ProviderMetadata]
}

protocol PersistentAIClientProtocol: AIClientProtocol {
    func startPersistentMessage(
        _ message: String,
        history: [APIMessage],
        model: String,
        provider: String,
        fallbackModels: [AIFallbackModel],
        projectId: String?
    ) async throws -> PersistentAIJob
    func getPersistentJob(id: String) async throws -> PersistentAIJob
}

protocol TasksClientProtocol {
    func fetchTasks(projectId: String?) async throws -> [ArchonTask]
    func getTaskDetails(id: String) async throws -> ArchonTask
    func getTaskEvents(id: String) async throws -> [TaskEvent]
    func cancelTask(id: String) async throws
    func createTask(_ request: CreateTaskRequest) async throws -> ArchonTask
}

// MARK: - APIClient Protocol

protocol APIClientProtocol: ProjectsClientProtocol, AIClientProtocol, TasksClientProtocol {}

// MARK: - Authenticated API Client

class AuthenticatedAPIClient: APIClientProtocol, PersistentAIClientProtocol {
    private let urlSession: URLSession
    private let tokenProvider: () async throws -> String

    init(urlSession: URLSession = .shared, tokenProvider: (@Sendable () async throws -> String)? = nil) {
        self.urlSession = urlSession
        self.tokenProvider = tokenProvider ?? {
            try await SupabaseClientManager.shared.client.auth.session.accessToken
        }
    }

    private func performRequest<T: Decodable>(url: URL, method: String, body: Data? = nil, retryCount: Int = 3) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body

        let token = try await tokenProvider()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        var attempt = 0
        while attempt < retryCount {
            let (data, response) = try await urlSession.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError(message: "Invalid response type", code: nil)
            }

            if (200...299).contains(httpResponse.statusCode) {
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                decoder.dateDecodingStrategy = .customISO8601
                return try decoder.decode(T.self, from: data)
            } else if method == "GET" && attempt < retryCount - 1 && httpResponse.statusCode >= 500 {
                attempt += 1
                try await Task.sleep(nanoseconds: UInt64(pow(2.0, Double(attempt))) * 1_000_000_000)
                continue
            } else {
                let decoded = try? JSONDecoder().decode(APIError.self, from: data)
                throw APIError(
                    message: decoded?.message ?? "HTTP error",
                    code: decoded?.code ?? httpResponse.statusCode
                )
            }
        }

        throw APIError(message: "Max retries exceeded", code: nil)
    }

    // MARK: - Projects

    func fetchProjects() async throws -> [ArchonProject] {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("projects")
        return try await performRequest(url: url, method: "GET")
    }

    func createProject(_ request: CreateProjectRequest) async throws -> ArchonProject {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("projects")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(request)
        return try await performRequest(url: url, method: "POST", body: body, retryCount: 1)
    }

    func updateProject(id: String, _ request: UpdateProjectRequest) async throws -> ArchonProject {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("projects/\(id)")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(request)
        return try await performRequest(url: url, method: "PATCH", body: body, retryCount: 1)
    }

    func deleteProject(id: String) async throws {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("projects/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let token = try await tokenProvider()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError(message: "Failed to delete project", code: (response as? HTTPURLResponse)?.statusCode)
        }
    }

    // MARK: - Tasks

    func fetchTasks(projectId: String? = nil) async throws -> [ArchonTask] {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("agent/tasks")
        return try await performRequest(url: url, method: "GET")
    }

    func getTaskDetails(id: String) async throws -> ArchonTask {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("agent/tasks/\(id)")
        return try await performRequest(url: url, method: "GET")
    }

    func getTaskEvents(id: String) async throws -> [TaskEvent] {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("agent/tasks/\(id)/events")
        return try await performRequest(url: url, method: "GET")
    }

    func cancelTask(id: String) async throws {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("agent/tasks/\(id)/cancel")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let token = try await tokenProvider()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError(message: "Failed to cancel task", code: (response as? HTTPURLResponse)?.statusCode)
        }
    }

    func createTask(_ createRequest: CreateTaskRequest) async throws -> ArchonTask {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("agent/tasks")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(createRequest)
        return try await performRequest(url: url, method: "POST", body: body, retryCount: 1)
    }

    // MARK: - Chat

    func sendMessage(_ message: String, history: [APIMessage], model: String, provider: String) async throws -> ChatAPIResponse {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("ai/chat")
        var messages = history
        if messages.last?.role != "user" || messages.last?.content != message {
            messages.append(APIMessage(role: "user", content: message))
        }
        let body = ChatAPIRequest(
            messages: messages,
            model: model,
            provider: provider,
            projectId: nil,
            maxTokens: 4096,
            temperature: 0.7,
            reasoningEffort: "medium",
            fallbackModels: nil
        )
        let encoder = JSONEncoder()
        let encoded = try encoder.encode(body)
        return try await performRequest(url: url, method: "POST", body: encoded, retryCount: 1)
    }

    func startPersistentMessage(
        _ message: String,
        history: [APIMessage],
        model: String,
        provider: String,
        fallbackModels: [AIFallbackModel],
        projectId: String?
    ) async throws -> PersistentAIJob {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("ai/jobs")
        var messages = history
        if messages.last?.role != "user" || messages.last?.content != message {
            messages.append(APIMessage(role: "user", content: message))
        }
        let request = ChatAPIRequest(
            messages: messages,
            model: model,
            provider: provider,
            projectId: projectId,
            maxTokens: 4096,
            temperature: 0.7,
            reasoningEffort: "medium",
            fallbackModels: fallbackModels
        )
        return try await performRequest(
            url: url,
            method: "POST",
            body: try JSONEncoder().encode(request),
            retryCount: 1
        )
    }

    func getPersistentJob(id: String) async throws -> PersistentAIJob {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("ai/jobs/\(id)")
        return try await performRequest(url: url, method: "GET")
    }

    // MARK: - Providers

    func fetchProviders() async throws -> [ProviderMetadata] {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("ai/providers")
        return try await performRequest(url: url, method: "GET")
    }
}
