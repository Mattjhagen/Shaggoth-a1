import Foundation

struct ArchonTask: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    var status: TaskStatus
    let provider: String
    let model: String
    let reasoningEffort: ReasoningEffort
    var currentStep: Int
    var maxSteps: Int
    var creditsUsed: Int
    var creditLimit: Int
    let projectId: String?
    let createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, status, provider, model
        case reasoningEffort = "reasoning_effort"
        case currentStep = "current_step"
        case maxSteps = "max_steps"
        case creditsUsed = "credits_used"
        case creditLimit = "credit_limit"
        case projectId = "project_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CreateTaskRequest: Encodable {
    let title: String
    let request: String
    let provider: String
    let model: String
    let reasoningEffort: ReasoningEffort
    let projectId: String?

    enum CodingKeys: String, CodingKey {
        case title, request, provider, model
        case reasoningEffort = "reasoning_effort"
        case projectId = "project_id"
    }
}
