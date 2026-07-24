import Foundation
import Supabase

final class SupabaseProjectsClient: ProjectsClientProtocol {
    private let client: SupabaseClient

    init(client: SupabaseClient = SupabaseClientManager.shared.client) {
        self.client = client
    }

    func fetchProjects() async throws -> [ArchonProject] {
        let rows: [ProjectRow] = try await client
            .from("projects")
            .select()
            .order("updated_at", ascending: false)
            .execute()
            .value

        return rows.map(\.project)
    }

    func createProject(_ request: CreateProjectRequest) async throws -> ArchonProject {
        guard let user = client.auth.currentUser else {
            throw APIError(message: "You must be signed in to create a project.", code: 401)
        }

        let payload = ProjectInsertPayload(
            userId: user.id,
            name: request.name,
            description: request.description
        )

        let row: ProjectRow = try await client
            .from("projects")
            .insert(payload)
            .select()
            .single()
            .execute()
            .value

        return row.project
    }

    func updateProject(id: String, _ request: UpdateProjectRequest) async throws -> ArchonProject {
        let payload = ProjectUpdatePayload(
            name: request.name,
            description: request.description,
            updatedAt: Date()
        )

        let row: ProjectRow = try await client
            .from("projects")
            .update(payload)
            .eq("id", value: id)
            .select()
            .single()
            .execute()
            .value

        return row.project
    }

    func deleteProject(id: String) async throws {
        try await client
            .from("projects")
            .delete(returning: .minimal)
            .eq("id", value: id)
            .execute()
    }
}

private struct ProjectRow: Decodable {
    let id: UUID
    let name: String
    let description: String?
    let status: ArchonProject.ProjectStatus
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var project: ArchonProject {
        ArchonProject(
            id: id.uuidString,
            name: name,
            description: description,
            status: status,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

private struct ProjectInsertPayload: Encodable {
    let userId: UUID
    let name: String
    let description: String?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case name
        case description
    }
}

private struct ProjectUpdatePayload: Encodable {
    let name: String?
    let description: String?
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case updatedAt = "updated_at"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(name, forKey: .name)
        try container.encodeIfPresent(description, forKey: .description)
        try container.encode(updatedAt, forKey: .updatedAt)
    }
}
