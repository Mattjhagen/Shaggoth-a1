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
    @Published var activeProject: ArchonProject?

    private let aiClient: AIClientProtocol
    private let tasksClient: TasksClientProtocol?
    private let memoryClient: ChatMemoryClientProtocol?
    private let sleeper: SleeperProtocol
    private let projectsClient: ProjectsClientProtocol?
    private let filesClient: ProjectFilesClientProtocol?
    private var pollingTask: Task<Void, Never>?
    private var processedEventIds = Set<String>()
    private static let providerPreferenceKey = "builder.selectedProviderId"
    private static let modelPreferenceKey = "builder.selectedModelId"
    private static let pendingJobPreferenceKey = "builder.pendingAIJob"

    init(
        aiClient: AIClientProtocol = AuthenticatedAPIClient(),
        memoryClient: ChatMemoryClientProtocol = SupabaseChatMemoryClient(),
        projectsClient: ProjectsClientProtocol = SupabaseProjectsClient(),
        filesClient: ProjectFilesClientProtocol = SupabaseProjectFilesClient(),
        sleeper: SleeperProtocol = DefaultSleeper()
    ) {
        self.aiClient = aiClient
        self.tasksClient = nil
        self.memoryClient = memoryClient
        self.projectsClient = projectsClient
        self.filesClient = filesClient
        self.sleeper = sleeper
        self.selectedProviderId = UserDefaults.standard.string(forKey: Self.providerPreferenceKey)
        self.selectedModelId = UserDefaults.standard.string(forKey: Self.modelPreferenceKey)
    }

    init(
        apiClient: APIClientProtocol,
        memoryClient: ChatMemoryClientProtocol? = nil,
        filesClient: ProjectFilesClientProtocol? = nil,
        sleeper: SleeperProtocol = DefaultSleeper()
    ) {
        self.aiClient = apiClient
        self.tasksClient = apiClient
        self.memoryClient = memoryClient
        self.projectsClient = apiClient
        self.filesClient = filesClient
        self.sleeper = sleeper
        self.selectedProviderId = UserDefaults.standard.string(forKey: Self.providerPreferenceKey)
        self.selectedModelId = UserDefaults.standard.string(forKey: Self.modelPreferenceKey)
    }

    var usableProviders: [ProviderMetadata] {
        providers.filter { $0.configured ?? false }
    }

    // MARK: - Message Queue

    /// A message sent while the AI is busy. Nothing interrupts a build in
    /// progress — new requests wait in line and run when the AI frees up.
    struct QueuedMessage: Identifiable, Equatable {
        let id = UUID()
        let text: String
        let projectId: String?
        var attachments: [Data] = []
    }

    @Published private(set) var queuedMessages: [QueuedMessage] = []

    /// Images (JPEG data) staged in the composer, sent with the next message.
    @Published var pendingAttachments: [Data] = []

    /// Single entry point for user messages: sends immediately when idle,
    /// otherwise joins the queue. Returns true when the message started
    /// processing right away.
    @discardableResult
    func submit(message: String, projectId: String? = nil) async -> Bool {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }

        let attachments = pendingAttachments
        pendingAttachments = []

        if isStreaming {
            queuedMessages.append(QueuedMessage(
                text: trimmed,
                projectId: projectId,
                attachments: attachments
            ))
            return false
        }

        await send(message: trimmed, projectId: projectId, attachments: attachments)
        await drainQueue()
        return true
    }

    func cancelQueuedMessage(_ id: UUID) {
        queuedMessages.removeAll { $0.id == id }
    }

    private func drainQueue() async {
        while !queuedMessages.isEmpty && !isStreaming {
            let next = queuedMessages.removeFirst()
            await send(message: next.text, projectId: next.projectId, attachments: next.attachments)
        }
    }

    // MARK: - Follow-up Suggestions

    /// Tappable "what to ask next" ideas shown after the AI replies. Rotates
    /// with the conversation so the chips feel fresh without an extra AI call.
    var followUpSuggestions: [String] {
        guard let last = messages.last, last.role == .assistant, !isStreaming else {
            return []
        }

        var pool = [
            "Change the colors",
            "Make it feel more playful",
            "Add a contact page",
            "Add some photos",
            "Make the words bigger and easier to read",
            "Add another page",
            "Make it look more professional",
            "Simplify it — less is more",
            "Add a dark mode",
            "Write friendlier text for me"
        ]

        let lowered = last.content.lowercased()
        if lowered.contains("store") || lowered.contains("shop") || lowered.contains("product") {
            pool.insert("Add more products", at: 0)
        }
        if lowered.contains("resume") || lowered.contains("about") {
            pool.insert("Add my work history", at: 0)
        }

        let offset = messages.count % pool.count
        let rotated = Array(pool[offset...] + pool[..<offset])
        return Array(rotated.prefix(3))
    }

    /// Priority order for the automatic model choice: the smart router first,
    /// then strong general models, then whatever else is configured.
    static func autoModelChoice(from providers: [ProviderMetadata]) -> (providerId: String, modelId: String)? {
        let preferences: [(provider: String, model: String)] = [
            ("openrouter", "openrouter/auto"),
            ("openai", "gpt-5.6-terra"),
            ("anthropic", "claude-sonnet-5"),
            ("openrouter", "openrouter/free")
        ]
        for preference in preferences {
            if let provider = providers.first(where: { $0.id == preference.provider }),
               provider.models.contains(where: { $0.id == preference.model }) {
                return (preference.provider, preference.model)
            }
        }
        guard let first = providers.first, let model = first.models.first else { return nil }
        return (first.id, model.id)
    }

    var selectedProvider: ProviderMetadata? {
        usableProviders.first { $0.id == selectedProviderId }
    }

    var isTaskActive: Bool {
        currentTask?.status.isActive ?? false
    }

    func useProject(_ project: ArchonProject?) {
        activeProject = project
    }

    // MARK: - Lifecycle

    func loadInitialState() async {
        isLoading = true
        defer { isLoading = false }

        var loadErrors: [String] = []

        do {
            let fetched = try await aiClient.fetchProviders()
            providers = fetched

            // The system picks the model — users never choose. The decision
            // is surfaced per-reply in the "under the hood" details instead.
            let configuredProviders = fetched.filter { $0.configured ?? false }
            if let choice = Self.autoModelChoice(from: configuredProviders) {
                selectedProviderId = choice.providerId
                selectedModelId = choice.modelId
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
            if let projectId = session.projectId?.uuidString,
               let projectsClient,
               let projects = try? await projectsClient.fetchProjects(),
               let project = projects.first(where: {
                   $0.id.caseInsensitiveCompare(projectId) == .orderedSame
               }) {
                activeProject = project
            }
            selectedProviderId = session.provider ?? selectedProviderId
            selectedModelId = session.model ?? selectedModelId
            isShowingConversation = true
            errorMessage = nil
        } catch {
            errorMessage = "Could not open conversation: \(error.localizedDescription)"
        }
    }

    // MARK: - Send Message

    func send(message text: String, projectId: String? = nil, attachments: [Data] = []) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        guard let providerId = selectedProviderId, let modelId = selectedModelId else {
            errorMessage = "Select a provider and model first."
            return
        }
        guard !isStreaming else { return }
        isStreaming = true
        defer { isStreaming = false }

        var effectiveProjectId = projectId ?? activeProject?.id
        if effectiveProjectId == nil {
            guard let projectsClient else {
                errorMessage = "A project is required before starting a build."
                return
            }
            do {
                let created = try await projectsClient.createProject(CreateProjectRequest(
                    name: Self.projectName(from: trimmed),
                    description: String(trimmed.prefix(240))
                ))
                activeProject = created
                effectiveProjectId = created.id
            } catch {
                errorMessage = "Could not create a project for this build: \(error.localizedDescription)"
                return
            }
        }

        if currentSession == nil,
           let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol {
            do {
                let session = try await sessionClient.createSession(
                    title: trimmed,
                    providerId: providerId,
                    modelId: modelId,
                    projectId: effectiveProjectId
                )
                currentSession = session
                sessions.insert(session, at: 0)
            } catch {
                errorMessage = "Could not create conversation: \(error.localizedDescription)"
                return
            }
        }

        let userMessage = ChatMessage(
            role: .user,
            content: trimmed,
            localImageData: attachments.isEmpty ? nil : attachments
        )
        messages.append(userMessage)

        do {
            try await saveToMemory(userMessage, providerId: providerId, modelId: modelId, projectId: effectiveProjectId)
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
                    projectId: effectiveProjectId
                ))
                currentTask = task
                startPolling(taskId: task.id)
            } else {
                // Production builds run without a tasks backend, so track the
                // build locally — otherwise the UI never leaves "Preparing
                // build" and never reports completion.
                currentTask = Self.localTask(
                    status: .running,
                    title: activeProject?.name ?? String(trimmed.prefix(200)),
                    provider: providerId,
                    model: modelId,
                    projectId: effectiveProjectId
                )
            }
            BuildNotifier.requestPermissionIfNeeded()
            errorMessage = nil

            let requestStart = Date()
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
                    projectId: effectiveProjectId,
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

            let assistantMessage = ChatMessage(
                role: .assistant,
                content: response.content,
                details: ChatMessage.BuildDetails(
                    provider: response.provider,
                    model: response.model,
                    inputTokens: response.tokensUsed?.input,
                    outputTokens: response.tokensUsed?.output,
                    elapsedSeconds: Date().timeIntervalSince(requestStart)
                )
            )
            messages.append(assistantMessage)

            if let generatedFiles = response.generatedFiles,
               let effectiveProjectId,
               let filesClient {
                do {
                    try await filesClient.upsertGeneratedFiles(
                        generatedFiles,
                        projectId: effectiveProjectId
                    )
                } catch {
                    errorMessage = "Build completed, but generated files could not be synchronized: \(error.localizedDescription)"
                }
            }

            do {
                try await saveToMemory(assistantMessage, providerId: providerId, modelId: modelId, projectId: effectiveProjectId)
            } catch {
                errorMessage = "Response received, but chat memory could not be saved: \(error.localizedDescription)"
            }

            markBuildFinished(as: .completed)

        } catch let apiError as APIError {
            markBuildFinished(as: .failed)
            errorMessage = apiError.errorDescription ?? apiError.message
        } catch {
            markBuildFinished(as: .failed)
            errorMessage = "Could not start task: \(error.localizedDescription)"
        }
    }

    /// Flip the tracked build into a finished state and let the user know.
    /// Only applies to locally tracked builds — server-backed tasks are
    /// updated by polling instead.
    private func markBuildFinished(as status: TaskStatus) {
        guard var task = currentTask, task.status.isActive, tasksClient == nil else { return }
        task.status = status
        task.currentStep = task.maxSteps
        task.updatedAt = Date()
        currentTask = task
        if status == .completed {
            BuildNotifier.notifyBuildFinished(projectName: activeProject?.name)
        }
    }

    private static func localTask(
        status: TaskStatus,
        title: String,
        provider: String,
        model: String,
        projectId: String?
    ) -> ArchonTask {
        let now = Date()
        return ArchonTask(
            id: "local-\(UUID().uuidString)",
            title: title,
            status: status,
            provider: provider,
            model: model,
            reasoningEffort: .medium,
            currentStep: 0,
            maxSteps: 1,
            creditsUsed: 0,
            creditLimit: 0,
            projectId: projectId,
            createdAt: now,
            updatedAt: now
        )
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
        }.sorted {
            // Prefer another model on the same provider before handing the
            // conversation to a different service. This keeps free/local
            // OpenCode fallback models ahead of metered cloud providers.
            let lhsSameProvider = $0.providerId == initialProviderId
            let rhsSameProvider = $1.providerId == initialProviderId
            if lhsSameProvider != rhsSameProvider {
                return lhsSameProvider
            }
            return false
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
                    },
                    projectId: projectId
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

    private static func projectName(from request: String) -> String {
        let clean = request
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String(clean.prefix(60))
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
            let assistantMessage = ChatMessage(
                role: .assistant,
                content: response.content,
                details: ChatMessage.BuildDetails(
                    provider: response.provider,
                    model: response.model,
                    inputTokens: response.tokensUsed?.input,
                    outputTokens: response.tokensUsed?.output,
                    elapsedSeconds: nil
                )
            )
            var fileSyncError: Error?

            if let generatedFiles = response.generatedFiles,
               let projectId = pending.projectId,
               let filesClient {
                do {
                    try await filesClient.upsertGeneratedFiles(
                        generatedFiles,
                        projectId: projectId
                    )
                } catch {
                    fileSyncError = error
                }
            }

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
            errorMessage = fileSyncError.map {
                "Build completed, but generated files could not be synchronized: \($0.localizedDescription)"
            }
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

    /// Standing instruction combining tone with full awareness of the app
    /// the AI lives in — its screens, flows, and the user's current context —
    /// so it can guide people around Archon better than anyone.
    private func appAwarenessInstruction() -> APIMessage {
        var context = """
        You are Archon, a friendly app-building companion inside the Archon iPhone app, \
        talking to a non-technical user. Speak like a helpful friend: short sentences, \
        plain everyday words, zero jargon. Never mention models, APIs, frameworks, servers, \
        or code unless the user explicitly asks. Describe what you're making in terms of \
        what they will see and tap. When something goes wrong, say what happened simply \
        and what you'll try next. Be warm, encouraging, and a little playful.

        You know the Archon app inside and out. Its screens:
        - Projects tab: every app or site the user has made; tapping one opens it in the Builder.
        - Builder tab: this chat. New builds start with three quick questions or a template \
        (Resume site, Small business, Online store, POS system, Portfolio). During a build, \
        the build screen has Preview and AI Agent tabs, a stop button, and an activity \
        timeline behind the list icon in the top corner.
        - Preview: a live look at their app; swipe up for full screen.
        - Publish: once a build finishes, the Publish button at the top of the build screen \
        puts the site online at a free address ending in .vibecodes.space — the user picks \
        the name, then shares the link.
        - Settings tab: account, appearance, and profile options.
        Messages sent while you're working wait in line and run next — nothing interrupts a build.
        When the user asks where something is or how to do something in Archon, give exact, \
        simple directions using these screens.
        """

        if let project = activeProject {
            context += "\n\nRight now the user is working on the project \"\(project.name)\"."
        }
        if let task = currentTask {
            context += " The current build status is: \(task.status.rawValue)."
        }
        return APIMessage(role: "system", content: context)
    }

    private func historyWithCrossSessionMemory() async -> [APIMessage] {
        var history = messages.map { message in
            APIMessage(
                role: message.role.rawValue,
                content: message.content,
                images: message.localImageData?.map {
                    "data:image/jpeg;base64,\($0.base64EncodedString())"
                }
            )
        }

        guard let sessionId = currentSession?.id,
              let sessionClient = memoryClient as? ChatSessionMemoryClientProtocol,
              let priorMessages = try? await sessionClient.fetchCrossSessionMemory(
                  excluding: sessionId,
                  limit: 16
              ),
              !priorMessages.isEmpty else {
            history.insert(appAwarenessInstruction(), at: 0)
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
        history.insert(appAwarenessInstruction(), at: 0)
        return history
    }

    func cancelActiveTask() async {
        guard let taskId = currentTask?.id else { return }
        guard let tasksClient else {
            // Locally tracked build: there is no server task to cancel, just
            // stop presenting it as active.
            currentTask?.status = .cancelled
            return
        }
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
