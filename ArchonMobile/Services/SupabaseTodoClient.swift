import Foundation
import Supabase

struct TodoItem: Codable, Identifiable, Hashable {
    let id: UUID
    var title: String
    var isCompleted: Bool
    let projectId: String
    let userId: String
    let createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case isCompleted = "is_completed"
        case projectId = "project_id"
        case userId = "user_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CreateTodoRequest: Encodable {
    let title: String
    let projectId: String
    let userId: String

    enum CodingKeys: String, CodingKey {
        case title
        case projectId = "project_id"
        case userId = "user_id"
    }
}

struct UpdateTodoRequest: Encodable {
    let title: String?
    let isCompleted: Bool?

    enum CodingKeys: String, CodingKey {
        case title
        case isCompleted = "is_completed"
    }
}

class SupabaseTodoClient {
    static let shared = SupabaseTodoClient()

    private let client = SupabaseClientManager.shared.client

    private init() {}

    func fetchTodos(projectId: String, userId: String) async throws -> [TodoItem] {
        let response: [TodoItem] = try await client
            .from("todo_items")
            .select()
            .eq("project_id", value: projectId)
            .eq("user_id", value: userId)
            .order("created_at", ascending: true)
            .execute()
            .value

        return response
    }

    func createTodo(_ request: CreateTodoRequest) async throws -> TodoItem {
        let response: TodoItem = try await client
            .from("todo_items")
            .insert(request)
            .select()
            .single()
            .execute()
            .value

        return response
    }

    func updateTodo(id: UUID, _ request: UpdateTodoRequest) async throws -> TodoItem {
        let response: TodoItem = try await client
            .from("todo_items")
            .update(request)
            .eq("id", value: id.uuidString)
            .select()
            .single()
            .execute()
            .value

        return response
    }

    func deleteTodo(id: UUID) async throws {
        try await client
            .from("todo_items")
            .delete()
            .eq("id", value: id.uuidString)
            .execute()
    }

    func deleteTodos(projectId: String, userId: String) async throws {
        try await client
            .from("todo_items")
            .delete()
            .eq("project_id", value: projectId)
            .eq("user_id", value: userId)
            .execute()
    }
}
