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
    @Published var selectedProviderId: String?
    @Published var selectedModelId: String?
    @Published var isStreaming = false
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var showEventTimeline = false

    private let apiClient: APIClientProtocol
    private let sleeper: SleeperProtocol
    private var pollingTask: Task<Void, Never>?
    private var processedEventIds = Set<String>()

    init(apiClient: APIClientProtocol = MockAPIClient(), sleeper: SleeperProtocol = DefaultSleeper()) {
        self.apiClient = apiClient
        self.sleeper = sleeper
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

        do {
            let fetched = try await apiClient.fetchProviders()
            providers = fetched
            if selectedProviderId == nil,
               let first = fetched.first(where: { $0.configured ?? false }) {
                selectedProviderId = first.id
                selectedModelId = first.models.first?.id
            }
        } catch {
            errorMessage = "Could not load providers: \(error.localizedDescription)"
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    // MARK: - Send Message

    func send(message text: String, projectId: String? = nil) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        let userMessage = ChatMessage(role: .user, content: trimmed)
        messages.append(userMessage)

        guard let providerId = selectedProviderId, let modelId = selectedModelId else {
            errorMessage = "Select a provider and model first."
            return
        }

        isStreaming = true
        defer { isStreaming = false }

        // Create task via API
        do {
            let task = try await apiClient.createTask(CreateTaskRequest(
                title: String(trimmed.prefix(200)),
                request: trimmed,
                provider: providerId,
                model: modelId,
                reasoningEffort: .medium,
                projectId: projectId
            ))
            currentTask = task
            errorMessage = nil

            // Start polling for events
            startPolling(taskId: task.id)

            // Simulate initial AI response
            let response = try await apiClient.sendMessage(
                trimmed,
                history: messages.map { APIMessage(role: $0.role.rawValue, content: $0.content) },
                model: modelId,
                provider: providerId
            )

            let assistantMessage = ChatMessage(role: .assistant, content: response.content)
            messages.append(assistantMessage)

        } catch let apiError as APIError {
            errorMessage = apiError.errorDescription ?? apiError.message
        } catch {
            errorMessage = "Could not start task: \(error.localizedDescription)"
        }
    }

    func cancelActiveTask() async {
        guard let taskId = currentTask?.id else { return }
        do {
            try await apiClient.cancelTask(id: taskId)
            pollingTask?.cancel()
            pollingTask = nil
            currentTask?.status = .cancelled
        } catch {
            errorMessage = "Failed to cancel: \(error.localizedDescription)"
        }
    }

    func retryLastMessage() async {
        guard let lastUserMessage = messages.last(where: { $0.role == .user }) else { return }
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
        var partialSuccess = false

        do {
            let task = try await apiClient.getTaskDetails(id: taskId)
            if Task.isCancelled { return true }
            self.currentTask = task
            partialSuccess = true
        } catch {}

        do {
            let fetchedEvents = try await apiClient.getTaskEvents(id: taskId)
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
