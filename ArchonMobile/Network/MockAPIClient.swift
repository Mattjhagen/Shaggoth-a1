import Foundation

/// Mock API client with rich demo data for simulator navigation.
/// All data is hardcoded — zero backend dependency.
class MockAPIClient: APIClientProtocol {

    // MARK: - Demo Data

    private(set) var projects: [ArchonProject] = [
        ArchonProject(
            id: "proj-1",
            name: "Weather Dashboard",
            description: "A beautiful weather app with animated icons and 5-day forecast",
            status: .active,
            createdAt: Calendar.current.date(byAdding: .day, value: -7, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .hour, value: -2, to: Date())!
        ),
        ArchonProject(
            id: "proj-2",
            name: "Task Manager Pro",
            description: "Kanban-style task manager with drag-and-drop",
            status: .active,
            createdAt: Calendar.current.date(byAdding: .day, value: -3, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .hour, value: -6, to: Date())!
        ),
        ArchonProject(
            id: "proj-3",
            name: "Fitness Tracker",
            description: "Workout tracker with progress charts and goals",
            status: .draft,
            createdAt: Calendar.current.date(byAdding: .hour, value: -4, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .hour, value: -1, to: Date())!
        ),
        ArchonProject(
            id: "proj-4",
            name: "Recipe Collection",
            description: "Personal recipe book with search and categories",
            status: .active,
            createdAt: Calendar.current.date(byAdding: .day, value: -14, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .day, value: -2, to: Date())!
        )
    ]

    private(set) var tasks: [ArchonTask] = [
        ArchonTask(
            id: "task-1",
            title: "Add animated weather icons",
            status: .completed,
            provider: "anthropic",
            model: "claude-sonnet-5",
            reasoningEffort: .medium,
            currentStep: 12,
            maxSteps: 12,
            creditsUsed: 180,
            creditLimit: 500,
            projectId: "proj-1",
            createdAt: Calendar.current.date(byAdding: .hour, value: -5, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .hour, value: -4, to: Date())!
        ),
        ArchonTask(
            id: "task-2",
            title: "Build drag-and-drop kanban board",
            status: .running,
            provider: "anthropic",
            model: "claude-sonnet-5",
            reasoningEffort: .high,
            currentStep: 8,
            maxSteps: 25,
            creditsUsed: 240,
            creditLimit: 500,
            projectId: "proj-2",
            createdAt: Calendar.current.date(byAdding: .hour, value: -1, to: Date())!,
            updatedAt: Date()
        ),
        ArchonTask(
            id: "task-3",
            title: "Create workout logging UI",
            status: .queued,
            provider: "openai",
            model: "gpt-5.6-sol",
            reasoningEffort: .medium,
            currentStep: 0,
            maxSteps: 20,
            creditsUsed: 0,
            creditLimit: 300,
            projectId: "proj-3",
            createdAt: Date(),
            updatedAt: Date()
        ),
        ArchonTask(
            id: "task-4",
            title: "Fix recipe search indexing",
            status: .failed,
            provider: "anthropic",
            model: "claude-haiku-4-5",
            reasoningEffort: .low,
            currentStep: 3,
            maxSteps: 10,
            creditsUsed: 45,
            creditLimit: 200,
            projectId: "proj-4",
            createdAt: Calendar.current.date(byAdding: .day, value: -1, to: Date())!,
            updatedAt: Calendar.current.date(byAdding: .hour, value: -12, to: Date())!
        )
    ]

    private var events: [String: [TaskEvent]] = [
        "task-1": [
            TaskEvent(id: "evt-1a", taskId: "task-1", sequence: 1, timestamp: Date().addingTimeInterval(-3600), type: .planning, content: "Analyzing existing weather icon assets and SVG structure", metadata: nil),
            TaskEvent(id: "evt-1b", taskId: "task-1", sequence: 2, timestamp: Date().addingTimeInterval(-3500), type: .toolCall, content: "Scanning src/Views/WeatherIcon.swift for current implementation", metadata: ["tool": AnyCodable("file_read")]),
            TaskEvent(id: "evt-1c", taskId: "task-1", sequence: 3, timestamp: Date().addingTimeInterval(-3400), type: .modelCall, content: "Designing animation sequences for sun, cloud, rain, and snow icons", metadata: nil),
            TaskEvent(id: "evt-1d", taskId: "task-1", sequence: 4, timestamp: Date().addingTimeInterval(-3300), type: .fileEdit, content: "Created WeatherAnimationView.swift with SwiftUI AnimatableModifier", metadata: ["file": AnyCodable("src/Views/WeatherAnimationView.swift")]),
            TaskEvent(id: "evt-1e", taskId: "task-1", sequence: 5, timestamp: Date().addingTimeInterval(-3200), type: .fileEdit, content: "Updated WeatherIcon.swift to use new animated views", metadata: ["file": AnyCodable("src/Views/WeatherIcon.swift")]),
            TaskEvent(id: "evt-1f", taskId: "task-1", sequence: 6, timestamp: Date().addingTimeInterval(-3100), type: .verification, content: "Running visual regression tests across iPhone SE, 15 Pro, and iPad", metadata: nil),
            TaskEvent(id: "evt-1g", taskId: "task-1", sequence: 7, timestamp: Date().addingTimeInterval(-3000), type: .completion, content: "All 4 animated icons working with smooth 60fps transitions", metadata: nil)
        ],
        "task-2": [
            TaskEvent(id: "evt-2a", taskId: "task-2", sequence: 1, timestamp: Date().addingTimeInterval(-3600), type: .planning, content: "Breaking down kanban board into column, card, and drag components", metadata: nil),
            TaskEvent(id: "evt-2b", taskId: "task-2", sequence: 2, timestamp: Date().addingTimeInterval(-3500), type: .toolCall, content: "Reading existing BoardView.swift and CardModel.swift", metadata: ["tool": AnyCodable("file_read")]),
            TaskEvent(id: "evt-2c", taskId: "task-2", sequence: 3, timestamp: Date().addingTimeInterval(-3400), type: .modelCall, content: "Designing data model with Column and Card entities", metadata: nil),
            TaskEvent(id: "evt-2d", taskId: "task-2", sequence: 4, timestamp: Date().addingTimeInterval(-3300), type: .fileEdit, content: "Created KanbanColumn.swift with drop destination support", metadata: ["file": AnyCodable("src/Kanban/KanbanColumn.swift")]),
            TaskEvent(id: "evt-2e", taskId: "task-2", sequence: 5, timestamp: Date().addingTimeInterval(-3200), type: .fileEdit, content: "Implementing draggable card with .draggable modifier", metadata: ["file": AnyCodable("src/Kanban/KanbanCard.swift")]),
            TaskEvent(id: "evt-2f", taskId: "task-2", sequence: 6, timestamp: Date().addingTimeInterval(-3100), type: .toolCall, content: "Testing drop target hit detection on column boundaries", metadata: ["tool": AnyCodable("xctest")]),
            TaskEvent(id: "evt-2g", taskId: "task-2", sequence: 7, timestamp: Date().addingTimeInterval(-3000), type: .modelCall, content: "Adding haptic feedback on successful card drops", metadata: nil),
            TaskEvent(id: "evt-2h", taskId: "task-2", sequence: 8, timestamp: Date().addingTimeInterval(-2900), type: .fileEdit, content: "Created KanbanBoard.swift container with scroll view", metadata: ["file": AnyCodable("src/Kanban/KanbanBoard.swift")])
        ]
    ]

    private var chatMessages: [ChatMessage] = []

    // MARK: - Projects

    func fetchProjects() async throws -> [ArchonProject] {
        try await simulateNetwork()
        return projects
    }

    func createProject(_ request: CreateProjectRequest) async throws -> ArchonProject {
        try await simulateNetwork()
        let project = ArchonProject(
            id: "proj-\(projects.count + 1)",
            name: request.name,
            description: request.description,
            status: .active,
            createdAt: Date(),
            updatedAt: Date()
        )
        projects.insert(project, at: 0)
        return project
    }

    func updateProject(id: String, _ request: UpdateProjectRequest) async throws -> ArchonProject {
        try await simulateNetwork()
        guard let index = projects.firstIndex(where: { $0.id == id }) else {
            throw APIError(message: "Project not found", code: 404)
        }
        let updated = projects[index]
        if let name = request.name { projects[index].name = name }
        if let desc = request.description { projects[index] = ArchonProject(id: updated.id, name: projects[index].name, description: desc, status: updated.status, createdAt: updated.createdAt, updatedAt: Date()) }
        projects[index] = ArchonProject(id: updated.id, name: projects[index].name, description: projects[index].description, status: updated.status, createdAt: updated.createdAt, updatedAt: Date())
        return projects[index]
    }

    func deleteProject(id: String) async throws {
        try await simulateNetwork()
        projects.removeAll { $0.id == id }
    }

    // MARK: - Tasks

    func fetchTasks(projectId: String? = nil) async throws -> [ArchonTask] {
        try await simulateNetwork()
        if let projectId {
            return tasks.filter { $0.projectId == projectId }
        }
        return tasks
    }

    func getTaskDetails(id: String) async throws -> ArchonTask {
        try await simulateNetwork()
        guard let task = tasks.first(where: { $0.id == id }) else {
            throw APIError(message: "Task not found", code: 404)
        }
        return task
    }

    func getTaskEvents(id: String) async throws -> [TaskEvent] {
        try await simulateNetwork()
        return events[id] ?? []
    }

    func createTask(_ request: CreateTaskRequest) async throws -> ArchonTask {
        try await simulateNetwork()
        let task = ArchonTask(
            id: "task-\(tasks.count + 1)",
            title: request.title,
            status: .queued,
            provider: request.provider,
            model: request.model,
            reasoningEffort: request.reasoningEffort,
            currentStep: 0,
            maxSteps: 40,
            creditsUsed: 0,
            creditLimit: 500,
            projectId: request.projectId,
            createdAt: Date(),
            updatedAt: Date()
        )
        tasks.append(task)
        return task
    }

    func cancelTask(id: String) async throws {
        try await simulateNetwork()
        if let index = tasks.firstIndex(where: { $0.id == id }) {
            tasks[index].status = .cancelled
            tasks[index].updatedAt = Date()
        }
    }

    // MARK: - Chat

    func sendMessage(_ message: String, history: [APIMessage], model: String, provider: String) async throws -> ChatAPIResponse {
        try await simulateNetwork(delay: 1.5)

        let responses = [
            "I'll help you build that! Let me start by creating the project structure and setting up the necessary components.",
            "Great idea! I'm analyzing the requirements and breaking this down into manageable pieces. Here's what I'll create:\n\n1. **Data Model** - Core types and persistence\n2. **UI Components** - Reusable SwiftUI views\n3. **Business Logic** - ViewModels and services\n\nLet me start building each piece.",
            "I've identified the key architectural patterns for this app. Using MVVM with SwiftUI, I'll create:\n\n- A `@Observable` view model for state management\n- Async/await for network calls\n- SwiftUI's navigation stack for routing\n\nStarting implementation now!",
            "Perfect! I've completed the core functionality. The app now has:\n\n- Full CRUD operations\n- Smooth animations\n- Dark mode support\n- Accessibility labels\n\nWould you like me to add any additional features or refine the existing ones?",
            "I'm working on the data layer now. Using a clean architecture approach with:\n\n```swift\n@Observable\nclass ItemViewModel {\n    private(set) var items: [Item] = []\n    \n    func loadItems() async {\n        items = await repository.fetch()\n    }\n}\n```\n\nThis keeps the UI reactive and the business logic testable."
        ]

        let content = responses.randomElement() ?? responses[0]
        return ChatAPIResponse(
            content: content,
            model: model,
            provider: provider,
            tokensUsed: APITokenUsage(input: message.count / 4, output: content.count / 4),
            reasoningEffort: "medium",
            creditUnits: 3
        )
    }

    // MARK: - Providers

    func fetchProviders() async throws -> [ProviderMetadata] {
        try await simulateNetwork()
        return [
            ProviderMetadata(
                id: "anthropic",
                name: "Anthropic",
                models: [
                    ModelMetadata(id: "claude-sonnet-5", name: "Claude Sonnet 5"),
                    ModelMetadata(id: "claude-haiku-4-5", name: "Claude Haiku 4.5")
                ],
                configured: true,
                requiresKey: true
            ),
            ProviderMetadata(
                id: "openai",
                name: "OpenAI",
                models: [
                    ModelMetadata(id: "gpt-5.6-sol", name: "GPT-5.6 Sol"),
                    ModelMetadata(id: "gpt-5.6-terra", name: "GPT-5.6 Terra")
                ],
                configured: true,
                requiresKey: true
            ),
            ProviderMetadata(
                id: "mock",
                name: "Demo (Simulated)",
                models: [
                    ModelMetadata(id: "mock-responses", name: "Demo Responses")
                ],
                configured: true,
                requiresKey: false
            )
        ]
    }

    // MARK: - Helpers

    private func simulateNetwork(delay: TimeInterval = 0.3) async throws {
        try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
    }
}
