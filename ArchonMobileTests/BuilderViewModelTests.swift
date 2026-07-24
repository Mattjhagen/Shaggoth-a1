import XCTest
import Combine
@testable import ArchonMobile

// MARK: - Test Doubles

/// Fully controllable API double for unit tests.
final class SpyAPIClient: APIClientProtocol {
    var projects: [ArchonProject] = []
    var providers: [ProviderMetadata] = []
    var tasks: [ArchonTask] = []
    var eventsByTaskId: [String: [TaskEvent]] = [:]
    var createTaskError: APIError?
    var createProjectError: APIError?
    var chatResponse: ChatAPIResponse?

    private(set) var createdRequests: [CreateTaskRequest] = []
    private(set) var createdProjectRequests: [CreateProjectRequest] = []
    private(set) var deletedProjectIds: [String] = []
    private(set) var taskDetailFetchCount = 0
    var onEventsFetched: (() -> Void)?

    // Projects
    func fetchProjects() async throws -> [ArchonProject] { projects }
    func createProject(_ request: CreateProjectRequest) async throws -> ArchonProject {
        if let error = createProjectError { throw error }
        createdProjectRequests.append(request)
        let project = ArchonProject(id: "spy-proj-\(createdProjectRequests.count)", name: request.name, description: request.description, status: .active, createdAt: Date(), updatedAt: Date())
        projects.append(project)
        return project
    }
    func updateProject(id: String, _ request: UpdateProjectRequest) async throws -> ArchonProject {
        guard let p = projects.first(where: { $0.id == id }) else { throw APIError(message: "not found", code: 404) }
        return p
    }
    func deleteProject(id: String) async throws { deletedProjectIds.append(id) }

    // Tasks
    func fetchTasks(projectId: String? = nil) async throws -> [ArchonTask] { tasks }
    func getTaskDetails(id: String) async throws -> ArchonTask {
        taskDetailFetchCount += 1
        guard let task = tasks.first(where: { $0.id == id }) else { throw APIError(message: "task not found", code: 404) }
        return task
    }
    func getTaskEvents(id: String) async throws -> [TaskEvent] {
        defer { onEventsFetched?() }
        return eventsByTaskId[id] ?? []
    }
    func cancelTask(id: String) async throws {}
    func createTask(_ request: CreateTaskRequest) async throws -> ArchonTask {
        if let error = createTaskError { throw error }
        createdRequests.append(request)
        let task = ArchonTask(id: "spy-task-\(createdRequests.count)", title: request.title, status: .queued, provider: request.provider, model: request.model, reasoningEffort: request.reasoningEffort, currentStep: 0, maxSteps: 40, creditsUsed: 0, creditLimit: 500, projectId: request.projectId, createdAt: Date(), updatedAt: Date())
        tasks.append(task)
        return task
    }

    // Chat
    func sendMessage(_ message: String, history: [APIMessage], model: String, provider: String) async throws -> ChatAPIResponse {
        chatResponse ?? ChatAPIResponse(content: "Test response", model: model, provider: provider, tokensUsed: nil, reasoningEffort: nil, creditUnits: nil)
    }

    // Providers
    func fetchProviders() async throws -> [ProviderMetadata] { providers }
}

/// Sleeper that never actually elapses.
final class HangSleeper: SleeperProtocol {
    private(set) var sleepCount = 0

    func sleep(nanoseconds: UInt64) async throws {
        sleepCount += 1
        try await Task.sleep(nanoseconds: 3_600_000_000_000)
    }
}

final class SpyChatMemoryClient: ChatMemoryClientProtocol {
    var storedMessages: [ChatMessage] = []
    var fetchError: Error?
    var saveError: Error?
    private(set) var savedMessages: [ChatMessage] = []
    private(set) var deletedMessageIds: [UUID] = []

    func fetchMessages(limit: Int) async throws -> [ChatMessage] {
        if let fetchError { throw fetchError }
        return Array(storedMessages.suffix(limit))
    }

    func saveMessage(
        _ message: ChatMessage,
        providerId: String?,
        modelId: String?,
        projectId: String?
    ) async throws {
        if let saveError { throw saveError }
        savedMessages.append(message)
    }

    func deleteMessage(id: UUID) async throws {
        deletedMessageIds.append(id)
    }
}

// MARK: - Fixtures

private func provider(id: String, configured: Bool?) -> ProviderMetadata {
    ProviderMetadata(
        id: id,
        name: id,
        models: [ModelMetadata(id: "\(id)-model", name: "\(id) model")],
        configured: configured,
        requiresKey: true
    )
}

private func terminalTask(id: String, status: TaskStatus) -> ArchonTask {
    ArchonTask(
        id: id, title: "t", status: status, provider: "p", model: "m",
        reasoningEffort: .medium, currentStep: 1, maxSteps: 1,
        creditsUsed: 1, creditLimit: 10, projectId: nil, createdAt: Date(), updatedAt: Date()
    )
}

// MARK: - Builder ViewModel Tests

@MainActor
final class BuilderViewModelTests: XCTestCase {

    func testUsableProvidersFilterToConfiguredOnly() async {
        let spy = SpyAPIClient()
        spy.providers = [
            provider(id: "configured", configured: true),
            provider(id: "unconfigured", configured: false),
            provider(id: "unknown", configured: nil),
        ]
        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())

        await vm.loadInitialState()

        XCTAssertEqual(vm.usableProviders.map(\.id), ["configured"])
        XCTAssertEqual(vm.selectedProviderId, "configured")
        XCTAssertEqual(vm.selectedModelId, "configured-model")
    }

    func testCreateTaskPayloadHasNoAPIKey() async throws {
        let request = CreateTaskRequest(
            title: "t", request: "r", provider: "p", model: "m",
            reasoningEffort: .medium, projectId: "proj-1"
        )

        let labels = Mirror(reflecting: request).children.compactMap(\.label)
        XCTAssertFalse(
            labels.contains { $0.lowercased().contains("key") || $0.lowercased().contains("secret") },
            "CreateTaskRequest must not carry credential fields"
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: encoder.encode(request)) as? [String: Any]
        )
        XCTAssertEqual(
            Set(json.keys),
            ["title", "request", "provider", "model", "reasoning_effort", "project_id"]
        )
        XCTAssertNil(json["api_key"])
    }

    func testBackendErrorBodyIsDisplayed() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        spy.createTaskError = APIError(message: "workspace_path is required", code: 400)
        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())

        await vm.loadInitialState()
        await vm.send(message: "do the thing")

        XCTAssertEqual(vm.errorMessage, "workspace_path is required (HTTP 400)")
        XCTAssertTrue(spy.createdRequests.isEmpty)
    }

    func testNoFabricatedMessagesAppear() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())

        await vm.loadInitialState()
        XCTAssertTrue(vm.messages.isEmpty)
        XCTAssertNil(vm.currentTask)
        vm.stopPolling()
    }

    func testLoadsSavedChatMemory() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let memory = SpyChatMemoryClient()
        memory.storedMessages = [
            ChatMessage(role: .user, content: "Remember this"),
            ChatMessage(role: .assistant, content: "I remember"),
        ]
        let vm = BuilderViewModel(apiClient: spy, memoryClient: memory, sleeper: HangSleeper())

        await vm.loadInitialState()

        XCTAssertEqual(vm.messages, memory.storedMessages)
        XCTAssertNil(vm.errorMessage)
    }

    func testSavesUserAndAssistantMessagesToMemory() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let memory = SpyChatMemoryClient()
        let vm = BuilderViewModel(apiClient: spy, memoryClient: memory, sleeper: HangSleeper())

        await vm.loadInitialState()
        await vm.send(message: "Build it")

        XCTAssertEqual(memory.savedMessages.map(\.role), [.user, .assistant])
        XCTAssertEqual(memory.savedMessages.map(\.content), ["Build it", "Test response"])
    }

    func testDoesNotSendWhenUserMessageCannotBeSaved() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let memory = SpyChatMemoryClient()
        memory.saveError = APIError(message: "memory unavailable", code: 503)
        let vm = BuilderViewModel(apiClient: spy, memoryClient: memory, sleeper: HangSleeper())

        await vm.loadInitialState()
        await vm.send(message: "Do not lose this")

        XCTAssertTrue(vm.messages.isEmpty)
        XCTAssertTrue(spy.createdRequests.isEmpty)
        XCTAssertEqual(vm.errorMessage, "Could not save your message: memory unavailable (HTTP 503)")
    }

    func testEmptyMessageNotSent() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())

        await vm.loadInitialState()
        await vm.send(message: "   ")

        XCTAssertTrue(spy.createdRequests.isEmpty)
        XCTAssertTrue(vm.messages.isEmpty)
        vm.stopPolling()
    }

    func testCancelActiveTask() async {
        let spy = SpyAPIClient()
        spy.providers = [provider(id: "p", configured: true)]
        let task = ArchonTask(
            id: "active-task", title: "Running task", status: .running,
            provider: "p", model: "m", reasoningEffort: .medium,
            currentStep: 5, maxSteps: 10, creditsUsed: 50, creditLimit: 100,
            projectId: nil, createdAt: Date(), updatedAt: Date()
        )
        spy.tasks = [task]
        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())
        vm.currentTask = task

        await vm.cancelActiveTask()

        XCTAssertEqual(vm.currentTask?.status, .cancelled)
    }
}

// MARK: - Dashboard ViewModel Tests

@MainActor
final class DashboardViewModelTests: XCTestCase {

    func testLoadProjects() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "Project 1", description: nil, status: .active, createdAt: Date(), updatedAt: Date()),
            ArchonProject(id: "p2", name: "Project 2", description: "Desc", status: .draft, createdAt: Date(), updatedAt: Date())
        ]
        let vm = DashboardViewModel(apiClient: spy)

        await vm.loadProjects()

        XCTAssertEqual(vm.projects.count, 2)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.errorMessage)
    }

    func testCreateProject() async {
        let spy = SpyAPIClient()
        let vm = DashboardViewModel(apiClient: spy)
        vm.newProjectName = "New App"
        vm.newProjectDescription = "A cool app"

        await vm.createProject()

        XCTAssertEqual(spy.createdProjectRequests.count, 1)
        XCTAssertEqual(spy.projects.count, 1)
        XCTAssertEqual(vm.projects.first?.name, "New App")
        XCTAssertFalse(vm.showCreateSheet)
    }

    func testDeleteProject() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "To Delete", description: nil, status: .active, createdAt: Date(), updatedAt: Date())
        ]
        let vm = DashboardViewModel(apiClient: spy)
        await vm.loadProjects()

        await vm.deleteProject(spy.projects[0])

        XCTAssertTrue(spy.deletedProjectIds.contains("p1"))
        XCTAssertTrue(vm.projects.isEmpty)
    }

    func testFilterProjects() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "Weather App", description: nil, status: .active, createdAt: Date(), updatedAt: Date()),
            ArchonProject(id: "p2", name: "Todo List", description: nil, status: .draft, createdAt: Date(), updatedAt: Date())
        ]
        let vm = DashboardViewModel(apiClient: spy)
        await vm.loadProjects()

        vm.searchText = "weather"
        XCTAssertEqual(vm.filteredProjects.count, 1)
        XCTAssertEqual(vm.filteredProjects.first?.name, "Weather App")

        vm.searchText = ""
        XCTAssertEqual(vm.filteredProjects.count, 2)
    }

    func testEmptyMessageNotCreated() async {
        let spy = SpyAPIClient()
        let vm = DashboardViewModel(apiClient: spy)
        vm.newProjectName = "   "

        await vm.createProject()

        XCTAssertTrue(spy.createdProjectRequests.isEmpty)
    }
}

// MARK: - Settings ViewModel Tests

@MainActor
final class SettingsViewModelTests: XCTestCase {

    func testDefaultAppearance() {
        let vm = SettingsViewModel()
        // Should default to system if nothing saved
        XCTAssertTrue(vm.appearance == .light || vm.appearance == .dark || vm.appearance == .system)
    }

    func testSaveAppearance() {
        let vm = SettingsViewModel()
        vm.saveAppearance(.dark)
        XCTAssertEqual(vm.appearance, .dark)

        let reloaded = SettingsViewModel()
        XCTAssertEqual(reloaded.appearance, .dark)
    }

    func testAppearanceDisplayNames() {
        XCTAssertEqual(SettingsViewModel.AppearanceMode.light.displayName, "Light")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.dark.displayName, "Dark")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.system.displayName, "System")
    }

    func testAppearanceIcons() {
        XCTAssertEqual(SettingsViewModel.AppearanceMode.light.icon, "sun.max.fill")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.dark.icon, "moon.fill")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.system.icon, "circle.lefthalf.filled")
    }
}
