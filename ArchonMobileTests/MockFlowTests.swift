import XCTest
@testable import ArchonMobile

/// End-to-end mock flow tests verifying the entire app is navigable.
@MainActor
final class MockFlowTests: XCTestCase {

    func testMockClientReturnsRichProjectData() async throws {
        let client = MockAPIClient()
        let projects = try await client.fetchProjects()

        XCTAssertFalse(projects.isEmpty, "Mock should return demo projects")
        XCTAssertNotNil(projects.first?.name)
        XCTAssertNotNil(projects.first?.description)
    }

    func testMockClientReturnsRichTaskData() async throws {
        let client = MockAPIClient()
        let tasks = try await client.fetchTasks()

        XCTAssertFalse(tasks.isEmpty, "Mock should return demo tasks")
        // Should have different statuses
        let statuses = Set(tasks.map(\.status))
        XCTAssertGreaterThan(statuses.count, 1, "Mock should have varied task statuses")
    }

    func testMockClientReturnsTaskEvents() async throws {
        let client = MockAPIClient()
        let events = try await client.getTaskEvents(id: "task-1")

        XCTAssertFalse(events.isEmpty, "Mock should return events for task-1")
        XCTAssertEqual(events.first?.sequence, 1)
    }

    func testMockClientCanCreateTask() async throws {
        let client = MockAPIClient()
        let initialCount = (try await client.fetchTasks()).count

        let task = try await client.createTask(CreateTaskRequest(
            title: "Test Task",
            request: "Build something",
            provider: "mock",
            model: "mock-responses",
            reasoningEffort: .medium,
            projectId: "proj-1"
        ))

        XCTAssertEqual(task.status, .queued)
        XCTAssertEqual(task.title, "Test Task")

        let afterCount = (try await client.fetchTasks()).count
        XCTAssertEqual(afterCount, initialCount + 1)
    }

    func testMockClientCanCancelTask() async throws {
        let client = MockAPIClient()
        try await client.cancelTask(id: "task-2")

        let task = try await client.getTaskDetails(id: "task-2")
        XCTAssertEqual(task.status, .cancelled)
    }

    func testMockClientCanCreateAndDeleteProject() async throws {
        let client = MockAPIClient()
        let project = try await client.createProject(CreateProjectRequest(
            name: "Test Project",
            description: "A test"
        ))

        XCTAssertEqual(project.name, "Test Project")
        XCTAssertEqual(project.status, .active)

        let afterCreate = try await client.fetchProjects()
        XCTAssertTrue(afterCreate.contains(where: { $0.id == project.id }))

        try await client.deleteProject(id: project.id)

        let afterDelete = try await client.fetchProjects()
        XCTAssertFalse(afterDelete.contains(where: { $0.id == project.id }))
    }

    func testMockClientChatReturnsResponse() async throws {
        let client = MockAPIClient()
        let response = try await client.sendMessage(
            "Build a todo app",
            history: [],
            model: "mock-responses",
            provider: "mock"
        )

        XCTAssertFalse(response.content.isEmpty, "Mock chat should return content")
        XCTAssertEqual(response.model, "mock-responses")
    }

    func testMockClientReturnsProviders() async throws {
        let client = MockAPIClient()
        let providers = try await client.fetchProviders()

        XCTAssertFalse(providers.isEmpty)
        let configured = providers.filter { $0.configured == true }
        XCTAssertFalse(configured.isEmpty, "Mock should have configured providers")
    }

    func testDashboardViewModelFullFlow() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "App 1", description: "Desc 1", status: .active, createdAt: Date(), updatedAt: Date()),
            ArchonProject(id: "p2", name: "App 2", description: nil, status: .draft, createdAt: Date(), updatedAt: Date())
        ]

        let vm = DashboardViewModel(apiClient: spy)
        await vm.loadProjects()

        XCTAssertEqual(vm.projects.count, 2)
        XCTAssertEqual(vm.activeProjects.count, 1)
        XCTAssertEqual(vm.draftProjects.count, 1)

        vm.searchText = "App 1"
        XCTAssertEqual(vm.filteredProjects.count, 1)

        vm.searchText = ""
        XCTAssertEqual(vm.filteredProjects.count, 2)
    }

    func testBuilderViewModelFullChatFlow() async {
        let spy = SpyAPIClient()
        spy.providers = [
            ProviderMetadata(id: "mock", name: "Mock", models: [ModelMetadata(id: "mock-model", name: "Mock Model")], configured: true, requiresKey: false)
        ]
        spy.chatResponse = ChatAPIResponse(
            content: "I'll build that for you!",
            model: "mock-model",
            provider: "mock",
            tokensUsed: APITokenUsage(input: 10, output: 20),
            reasoningEffort: "medium",
            creditUnits: 1
        )

        let vm = BuilderViewModel(apiClient: spy, sleeper: HangSleeper())
        await vm.loadInitialState()

        XCTAssertEqual(vm.usableProviders.count, 1)
        XCTAssertEqual(vm.selectedProviderId, "mock")

        await vm.send(message: "Build a todo app")

        XCTAssertEqual(vm.messages.count, 2) // user + assistant
        XCTAssertEqual(vm.messages.first?.role, .user)
        XCTAssertEqual(vm.messages.last?.role, .assistant)
        XCTAssertEqual(spy.createdRequests.count, 1)

        vm.stopPolling()
    }
}
