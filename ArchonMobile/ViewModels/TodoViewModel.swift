import Foundation
import Combine

@MainActor
final class TodoViewModel: ObservableObject {
    @Published var todos: [TodoItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var newTodoTitle = ""

    private let todoClient = SupabaseTodoClient.shared
    private var projectId: String?
    private var userId: String?

    var completedCount: Int {
        todos.filter { $0.isCompleted }.count
    }

    var pendingCount: Int {
        todos.filter { !$0.isCompleted }.count
    }

    var progress: Double {
        guard !todos.isEmpty else { return 0 }
        return Double(completedCount) / Double(todos.count)
    }

    func loadTodos(projectId: String, userId: String) async {
        self.projectId = projectId
        self.userId = userId

        isLoading = true
        defer { isLoading = false }

        do {
            todos = try await todoClient.fetchTodos(projectId: projectId, userId: userId)
        } catch {
            errorMessage = "Failed to load todos: \(error.localizedDescription)"
        }
    }

    func addTodo() async {
        guard let projectId = projectId, let userId = userId else { return }
        let title = newTodoTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return }

        do {
            let todo = try await todoClient.createTodo(CreateTodoRequest(
                title: title,
                projectId: projectId,
                userId: userId
            ))
            todos.append(todo)
            newTodoTitle = ""
        } catch {
            errorMessage = "Failed to add todo: \(error.localizedDescription)"
        }
    }

    func toggleTodo(_ todo: TodoItem) async {
        do {
            let updated = try await todoClient.updateTodo(
                id: todo.id,
                UpdateTodoRequest(title: nil, isCompleted: !todo.isCompleted)
            )
            if let index = todos.firstIndex(where: { $0.id == todo.id }) {
                todos[index] = updated
            }
        } catch {
            errorMessage = "Failed to update todo: \(error.localizedDescription)"
        }
    }

    func updateTodoTitle(_ todo: TodoItem, newTitle: String) async {
        guard !newTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        do {
            let updated = try await todoClient.updateTodo(
                id: todo.id,
                UpdateTodoRequest(title: newTitle, isCompleted: nil)
            )
            if let index = todos.firstIndex(where: { $0.id == todo.id }) {
                todos[index] = updated
            }
        } catch {
            errorMessage = "Failed to update todo: \(error.localizedDescription)"
        }
    }

    func deleteTodo(_ todo: TodoItem) async {
        do {
            try await todoClient.deleteTodo(id: todo.id)
            todos.removeAll { $0.id == todo.id }
        } catch {
            errorMessage = "Failed to delete todo: \(error.localizedDescription)"
        }
    }

    func clearCompleted() async {
        guard projectId != nil, userId != nil else { return }

        let completedIds = todos.filter { $0.isCompleted }.map { $0.id }
        for id in completedIds {
            do {
                try await todoClient.deleteTodo(id: id)
            } catch {
                errorMessage = "Failed to delete todo: \(error.localizedDescription)"
            }
        }
        todos.removeAll { $0.isCompleted }
    }
}
