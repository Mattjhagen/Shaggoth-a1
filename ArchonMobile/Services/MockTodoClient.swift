import Foundation

class MockTodoClient: TodoClientProtocol {
    var todos: [TodoItem] = []
    var errorToThrow: Error?

    func fetchTodos(projectId: String, userId: String) async throws -> [TodoItem] {
        if let errorToThrow { throw errorToThrow }
        return todos.filter { $0.projectId == projectId && $0.userId == userId }
    }

    func createTodo(_ request: CreateTodoRequest) async throws -> TodoItem {
        if let errorToThrow { throw errorToThrow }
        let todo = TodoItem(
            id: UUID(),
            title: request.title,
            isCompleted: false,
            projectId: request.projectId,
            userId: request.userId,
            createdAt: Date(),
            updatedAt: Date()
        )
        todos.append(todo)
        return todo
    }

    func updateTodo(id: UUID, _ request: UpdateTodoRequest) async throws -> TodoItem {
        if let errorToThrow { throw errorToThrow }
        guard let index = todos.firstIndex(where: { $0.id == id }) else {
            throw NSError(domain: "MockTodoClient", code: 404, userInfo: [NSLocalizedDescriptionKey: "Todo not found"])
        }
        var todo = todos[index]
        if let title = request.title {
            todo.title = title
        }
        if let isCompleted = request.isCompleted {
            todo.isCompleted = isCompleted
        }
        todo.updatedAt = Date()
        todos[index] = todo
        return todo
    }

    func deleteTodo(id: UUID) async throws {
        if let errorToThrow { throw errorToThrow }
        todos.removeAll { $0.id == id }
    }

    func deleteTodos(projectId: String, userId: String) async throws {
        if let errorToThrow { throw errorToThrow }
        todos.removeAll { $0.projectId == projectId && $0.userId == userId }
    }
}
