import Foundation
import Combine

protocol SleeperProtocol {
    func sleep(nanoseconds: UInt64) async throws
}

struct DefaultSleeper: SleeperProtocol {
    func sleep(nanoseconds: UInt64) async throws {
        try await Task.sleep(nanoseconds: nanoseconds)
    }
}

@MainActor
final class BuilderViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var currentTask: ArchonTask?
    @Published var taskEvents: [TaskEvent] = []
    @Published var providers: [ProviderMetadata] = []
    @Published var selectedProviderId: String? {
        didSet {
            Self.saveSelection(selectedProviderId, key: Self.providerPreferenceKey)
        }
    }
    @Published var selectedModelId: String? {
        didSet {
            Self.saveSelection(selectedModelId, key: Self.modelPreferenceKey)
        }
    }
    @Published var isStreaming = false
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var showEventTimeline = false
    @Published var sessions: [ChatSession] = []
    @Published var currentSession: ChatSession?
    @Published var isShowingConversation = false

    private let aiClient: AIClientProtocol
    private let tasksClient: TasksClientProtocol?
    private let memoryClient: ChatMemoryClientProtocol?
    private let sleeper: SleeperProtocol
    private var pollingTask: Task<Void, Never>?
    private var processedEventIds = Set<String>()
    private static let providerPreferenceKey = "builder.selectedProviderId"
    private static let modelPreferenceKey = "builder.selectedModelId"
    private static let pendingJobPreferenceKey = "builder.pendingAIJob"

    init(
        aiClient: AIClientProtocol = AuthenticatedAPIClient(),
        memoryClient: ChatMemoryClientProtocol = SupabaseChatMemoryClient(),
        sleeper: SleeperProtocol = DefaultSleeper()
    ) {
        self.aiClient = aiClient
        self.tasksClient = nil
        self.memoryClient = memoryClient
        self.sleeper = sleeper
        self.selectedProviderId = UserDefaults.standard.string(forKey: Self.providerPreferenceKey)
        self.selectedModelId = UserDefaults.standard.string(forKey: Self.modelPreferenceKey)
    }

    init(
        apiClient: APIClientProtocol,
        memoryClient: ChatMemoryClientProtocol? = nil,
        sleeper: SleeperProtocol = DefaultSleeper()
    ) {
        self.aiClient = apiClient
        self.tasksClient = apiClient
        self.memoryClient = memoryClient
        self.sleeper = sleeper
        self.selectedProviderId = UserDefaults.standard.string(forKey: Self.providerPreferenceKey)
        self.selectedModelId = UserDefaults.standard.string(forKey: Self.modelPreferenceKey)
    }

    var usableProviders: [ProviderMetadata] {
        providers.filter { $0.configured ?? false }
    }

    var selectedProvider: ProviderMetadata? {
        usableProviders.first { $0.id == selectedProviderId }
    }

    var isTaskActive: Bool {
        currentTask?.status.isActive ?? false
    }

    // MARK: - Lifecycle

    func loadInitialState() async {
        isLoading = true
        defer { isLoading = false }

        var loadErrors: [String] = []

        do {
            let fetched = try await aiClient.fetchProviders()
            providers = fetched

            let configuredProviders = fetched.filter { $0.configured ?? false }
            if let savedProvider = configuredProviders.first(where: { $0.id == selectedProviderId }) {
                if savedProvider.models.contains(where: { $0.id == selectedModelId }) == false {
                    selectedModelId = savedProvider.models.first?.id
                }
            } else if let first = configuredProviders.first {
                selectedProviderId = first.id
                selectedModelId = first.models.first?.id
            }
        } catch {
            loadErrors.append("Could not load providers: \(error.localizedDescription)")
        }

        do {
            if let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol {
                sessions = try await sessionClient.fetchSessions()
                messages = []
                isShowingConversation = false
            } else if let memoryClient {
                messages = try await memoryClient.fetchMessages(limit: 50)
                isShowingConversation = true
            }
        } catch {
            loadErrors.append("Could not load chat memory: \(error.localizedDescription)")
        }

        errorMessage = loadErrors.isEmpty ? nil : loadErrors.joined(separator: "\n")

        if loadPendingJob() != nil {
            Task { [weak self] in
                await self?.resumePendingJobIfNeeded()
            }
        }
    }

    private static func saveSelection(_ value: String?, key: String) {
        if let value {
            UserDefaults.standard.set(value, forKey: key)
        } else {
            UserDefaults.standard.removeObject(forKey: key)
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    func startNewSession() {
        stopPolling()
        messages = []
        currentTask = nil
        taskEvents = []
        processedEventIds = []
        errorMessage = nil
        isStreaming = false
        currentSession = nil
        isShowingConversation = true
    }

    func showConversationList() async {
        stopPolling()
        messages = []
        currentSession = nil
        currentTask = nil
        taskEvents = []
        isShowingConversation = false

        guard let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol else { return }
        do {
            sessions = try await sessionClient.fetchSessions()
            errorMessage = nil
        } catch {
            errorMessage = "Could not load conversations: \(error.localizedDescription)"
        }
    }

    func openSession(_ session: ChatSession) async {
        guard let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            messages = try await sessionClient.fetchMessages(sessionId: session.id, limit: 50)
            currentSession = session
            selectedProviderId = session.provider ?? selectedProviderId
            selectedModelId = session.model ?? selectedModelId
            isShowingConversation = true
            errorMessage = nil
        } catch {
            errorMessage = "Could not open conversation: \(error.localizedDescription)"
        }
    }

    // MARK: - Send Message

    func send(message text: String, projectId: String? = nil) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        guard let providerId = selectedProviderId, let modelId = selectedModelId else {
            errorMessage = "Select a provider and model first."
            return
        }
        guard !isStreaming else { return }
        isStreaming = true
        defer { isStreaming = false }

        if currentSession == nil,
           let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol {
            do {
                let session = try await sessionClient.createSession(
                    title: trimmed,
                    providerId: providerId,
                    modelId: modelId
                )
                currentSession = session
                sessions.insert(session, at: 0)
            } catch {
                errorMessage = "Could not create conversation: \(error.localizedDescription)"
                return
            }
        }

        let userMessage = ChatMessage(role: .user, content: trimmed)
        messages.append(userMessage)

        do {
            try await saveToMemory(userMessage, providerId: providerId, modelId: modelId, projectId: projectId)
        } catch {
            messages.removeAll { $0.id == userMessage.id }
            errorMessage = "Could not save your message: \(error.localizedDescription)"
            return
        }

        // Create task via API
        do {
            if let tasksClient {
                let task = try await tasksClient.createTask(CreateTaskRequest(
                    title: String(trimmed.prefix(200)),
                    request: trimmed,
                    provider: providerId,
                    model: modelId,
                    reasoningEffort: .medium,
                    projectId: projectId
                ))
                currentTask = task
                startPolling(taskId: task.id)
            }
            errorMessage = nil

            let history = await historyWithCrossSessionMemory()
            let response: ChatAPIResponse

            if let persistentClient = aiClient as? PersistentAIClientProtocol,
               let sessionId = currentSession?.id {
                let result = try await sendWithCreditHandoff(
                    trimmed,
                    history: history,
                    initialProviderId: providerId,
                    initialModelId: modelId,
                    sessionId: sessionId,
                    projectId: projectId,
                    client: persistentClient
                )
                response = result.response
                if result.didHandoff {
                    selectedProviderId = result.providerId
                    selectedModelId = result.modelId
                    let providerName = providers.first(where: { $0.id == result.providerId })?.name
                        ?? result.providerId
                    messages.append(ChatMessage(
                        role: .system,
                        content: "The selected model was unavailable. Build continued with \(providerName) · \(result.modelId)."
                    ))
                }
            } else {
                response = try await aiClient.sendMessage(
                    trimmed,
                    history: history,
                    model: modelId,
                    provider: providerId
                )
            }

            let assistantMessage = ChatMessage(role: .assistant, content: response.content)
            messages.append(assistantMessage)

            do {
                try await saveToMemory(assistantMessage, providerId: providerId, modelId: modelId, projectId: projectId)
            } catch {
                errorMessage = "Response received, but chat memory could not be saved: \(error.localizedDescription)"
            }

        } catch let apiError as APIError {
            errorMessage = apiError.errorDescription ?? apiError.message
        } catch {
            errorMessage = "Could not start task: \(error.localizedDescription)"
        }
    }

    private func waitForPersistentJob(
        _ id: String,
        client: PersistentAIClientProtocol
    ) async throws -> ChatAPIResponse {
        while true {
            let job = try await client.getPersistentJob(id: id)
            updateBuildLogs(from: job)
            switch job.status {
            case .queued, .running:
                try await sleeper.sleep(nanoseconds: 3_000_000_000)
            case .completed:
                guard let response = job.response else {
                    throw APIError(message: "The completed build did not include a response.", code: 500)
                }
                return response
            case .failed, .timedOut:
                clearPendingJob()
                throw APIError(message: job.error ?? "The background build failed.", code: 500)
            }
        }
    }

    private func updateBuildLogs(from job: PersistentAIJob) {
        for log in (job.logs ?? []).sorted(by: { $0.sequence < $1.sequence }) {
            guard !processedEventIds.contains(log.id) else { continue }
            processedEventIds.insert(log.id)
            taskEvents.append(TaskEvent(
                id: log.id,
                taskId: job.id,
                sequence: log.sequence,
                timestamp: log.createdAt,
                type: TaskEvent.EventType(rawValue: log.kind) ?? .message,
                content: log.summary,
                metadata: nil
            ))
        }
    }

    private func sendWithCreditHandoff(
        _ message: String,
        history: [APIMessage],
        initialProviderId: String,
        initialModelId: String,
        sessionId: UUID,
        projectId: String?,
        client: PersistentAIClientProtocol
    ) async throws -> (response: ChatAPIResponse, providerId: String, modelId: String, didHandoff: Bool) {
        let initial = (providerId: initialProviderId, modelId: initialModelId)
        let alternatives = usableProviders.flatMap { provider in
            provider.models.map { (providerId: provider.id, modelId: $0.id) }
        }.filter {
            $0.providerId != initialProviderId || $0.modelId != initialModelId
        }
        let candidates = [initial] + alternatives
        var lastError: Error?

        for (index, candidate) in candidates.enumerated() {
            do {
                let job = try await client.startPersistentMessage(
                    message,
                    history: history,
                    model: candidate.modelId,
                    provider: candidate.providerId,
                    fallbackModels: alternatives.map {
                        AIFallbackModel(provider: $0.providerId, model: $0.modelId)
                    }
                )
                updateBuildLogs(from: job)
                savePendingJob(PendingAIJob(
                    id: job.id,
                    sessionId: sessionId,
                    providerId: candidate.providerId,
                    modelId: candidate.modelId,
                    projectId: projectId,
                    // Jobs created by an older server may not include an
                    // expiry in the initial response. Keep a conservative
                    // local deadline so the build can still be resumed.
                    expiresAt: job.expiresAt ?? Date().addingTimeInterval(15 * 60)
                ))
                let response = try await waitForPersistentJob(job.id, client: client)
                clearPendingJob()
                return (
                    response,
                    response.provider,
                    response.model,
                    index > 0 || response.provider != initialProviderId || response.model != initialModelId
                )
            } catch {
                lastError = error
                clearPendingJob()
                guard Self.shouldHandoff(after: error), index < candidates.count - 1 else {
                    throw error
                }
            }
        }

        throw lastError ?? APIError(message: "No configured AI model could continue the build.", code: 402)
    }

    private static func shouldHandoff(after error: Error) -> Bool {
        if let apiError = error as? APIError {
            if apiError.code == 401 || apiError.code == 403 {
                return false
            }
            if apiError.code == 402 || apiError.code == 408 || apiError.code == 429 {
                return true
            }
            if let code = apiError.code, (500...599).contains(code) {
                return true
            }
        }

        let text = error.localizedDescription.lowercased()
        let recoverableSignals = [
            "credit", "quota", "billing", "payment required",
            "insufficient_quota", "insufficient funds", "usage limit",
            "spending limit", "rate limit", "timed out", "timeout",
            "temporarily unavailable", "no provider available",
            "model failed", "server could not be reached"
        ]
        return recoverableSignals.contains { text.contains($0) }
    }

    private func resumePendingJobIfNeeded() async {
        guard let pending = loadPendingJob(),
              let persistentClient = aiClient as? PersistentAIClientProtocol else { return }

        isStreaming = true
        defer { isStreaming = false }

        do {
            let response = try await waitForPersistentJob(pending.id, client: persistentClient)
            let assistantMessage = ChatMessage(role: .assistant, content: response.content)

            if let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol {
                try await sessionClient.saveMessage(
                    assistantMessage,
                    sessionId: pending.sessionId,
                    providerId: pending.providerId,
                    modelId: pending.modelId,
                    projectId: pending.projectId
                )
            }

            if currentSession?.id == pending.sessionId {
                messages.append(assistantMessage)
            }
            clearPendingJob()
            if let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol {
                sessions = try await sessionClient.fetchSessions()
            }
            errorMessage = nil
        } catch {
            if loadPendingJob() == nil || Date() >= pending.expiresAt {
                clearPendingJob()
                errorMessage = "Background build stopped: \(error.localizedDescription)"
            } else {
                errorMessage = "Background build is still saved and will reconnect automatically."
            }
        }
    }

    private func savePendingJob(_ pending: PendingAIJob) {
        guard let data = try? JSONEncoder().encode(pending) else { return }
        UserDefaults.standard.set(data, forKey: Self.pendingJobPreferenceKey)
    }

    private func loadPendingJob() -> PendingAIJob? {
        guard let data = UserDefaults.standard.data(forKey: Self.pendingJobPreferenceKey) else {
            return nil
        }
        return try? JSONDecoder().decode(PendingAIJob.self, from: data)
    }

    private func clearPendingJob() {
        UserDefaults.standard.removeObject(forKey: Self.pendingJobPreferenceKey)
    }

    private func saveToMemory(
        _ message: ChatMessage,
        providerId: String,
        modelId: String,
        projectId: String?
    ) async throws {
        if let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol,
           let sessionId = currentSession?.id {
            try await sessionClient.saveMessage(
                message,
                sessionId: sessionId,
                providerId: providerId,
                modelId: modelId,
                projectId: projectId
            )
        } else {
            try await memoryClient?.saveMessage(
                message,
                providerId: providerId,
                modelId: modelId,
                projectId: projectId
            )
        }
    }

    private func historyWithCrossSessionMemory() async -> [APIMessage] {
        var history = messages.map { APIMessage(role: $0.role.rawValue, content: $0.content) }

        guard let sessionId = currentSession?.id,
              let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol,
              let priorMessages = try? await sessionClient.fetchCrossSessionMemory(
                  excluding: sessionId,
                  limit: 16
              ),
              !priorMessages.isEmpty else {
            return history
        }

        // Keep cross-session context bounded so old conversations cannot crowd
        // the active request out of the model's context window.
        let memoryText = priorMessages
            .map { "\($0.role.rawValue): \($0.content)" }
            .joined(separator: "\n\n")
        let boundedMemory = String(memoryText.suffix(12_000))
        let memoryInstruction = APIMessage(
            role: "system",
            content: """
            Private memory from the user's recent Archon conversations follows. Use it only when relevant to maintain continuity. Prefer the current conversation if anything conflicts. Do not mention this memory unless the user asks.

            \(boundedMemory)
            """
        )
        history.insert(memoryInstruction, at: 0)
        return history
    }

    func cancelActiveTask() async {
        guard let taskId = currentTask?.id, let tasksClient else { return }
        do {
            try await tasksClient.cancelTask(id: taskId)
            pollingTask?.cancel()
            pollingTask = nil
            currentTask?.status = .cancelled
        } catch {
            errorMessage = "Failed to cancel: \(error.localizedDescription)"
        }
    }

    func retryLastMessage() async {
        guard let lastUserMessage = messages.last(where: { $0.role == .user }) else { return }

        do {
            try await memoryClient?.deleteMessage(id: lastUserMessage.id)
        } catch {
            errorMessage = "Could not update chat memory for retry: \(error.localizedDescription)"
            return
        }

        messages.removeAll { $0.id == lastUserMessage.id }
        await send(message: lastUserMessage.content)
    }

    // MARK: - Polling

    private func startPolling(taskId: String) {
        pollingTask?.cancel()
        processedEventIds.removeAll()

        pollingTask = Task { [weak self] in
            var consecutiveFailures = 0

            while !Task.isCancelled {
                guard let self = self else { break }

                let success = await self.fetchTaskDetails(taskId: taskId)

                if success {
                    consecutiveFailures = 0
                } else {
                    consecutiveFailures += 1
                }

                if let status = self.currentTask?.status, !status.isActive {
                    break
                }

                let sleepDuration = success ? 3.0 : min(3.0 * pow(2.0, Double(consecutiveFailures)), 30.0)
                try? await self.sleeper.sleep(nanoseconds: UInt64(sleepDuration * 1_000_000_000))
            }
        }
    }

    private func fetchTaskDetails(taskId: String) async -> Bool {
        guard let tasksClient else { return false }
        var partialSuccess = false

        do {
            let task = try await tasksClient.getTaskDetails(id: taskId)
            if Task.isCancelled { return true }
            self.currentTask = task
            partialSuccess = true
        } catch {}

        do {
            let fetchedEvents = try await tasksClient.getTaskEvents(id: taskId)
            if Task.isCancelled { return true }

            let sortedNewEvents = fetchedEvents.sorted(by: { $0.sequence < $1.sequence })
            for event in sortedNewEvents {
                if !processedEventIds.contains(event.id) {
                    processedEventIds.insert(event.id)
                    taskEvents.append(event)
                }
            }
            taskEvents.sort(by: { $0.sequence < $1.sequence })

            return true
        } catch {
            return partialSuccess
        }
    }

    deinit {
        pollingTask?.cancel()
    }
}

private struct PendingAIJob: Codable {
    let id: String
    let sessionId: UUID
    let providerId: String
    let modelId: String
    let projectId: String?
    let expiresAt: Date
}
