import Foundation

protocol TodoClientProtocol {
    func fetchTodos(projectId: String, userId: String) async throws -> [TodoItem]
    func createTodo(_ request: CreateTodoRequest) async throws -> TodoItem
    func updateTodo(id: UUID, _ request: UpdateTodoRequest) async throws -> TodoItem
    func deleteTodo(id: UUID) async throws
    func deleteTodos(projectId: String, userId: String) async throws
}

extension SupabaseTodoClient: TodoClientProtocol {}
