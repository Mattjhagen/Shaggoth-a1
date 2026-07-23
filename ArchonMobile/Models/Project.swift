import Foundation

struct ArchonProject: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    let description: String?
    var status: ProjectStatus
    let createdAt: Date
    var updatedAt: Date

    enum ProjectStatus: String, Codable, CaseIterable {
        case active
        case archived
        case draft
    }
}

struct CreateProjectRequest: Encodable {
    let name: String
    let description: String?
}

struct UpdateProjectRequest: Encodable {
    let name: String?
    let description: String?
}
