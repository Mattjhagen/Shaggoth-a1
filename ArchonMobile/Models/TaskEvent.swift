import Foundation

struct TaskEvent: Codable, Identifiable, Hashable {
    let id: String
    let taskId: String
    let sequence: Int
    let timestamp: Date
    let type: EventType
    let content: String
    let metadata: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case id
        case taskId = "task_id"
        case sequence
        case timestamp = "created_at"
        case type = "kind"
        case content = "summary"
        case metadata
    }

    enum EventType: String, Codable {
        case planning
        case modelCall = "model_call"
        case toolCall = "tool_call"
        case toolResult = "tool_result"
        case verification
        case completion
        case blocker
        case error
        case fileEdit = "file_edit"
        case message

        var displayCategory: String {
            switch self {
            case .planning: return "Planning"
            case .modelCall: return "Thinking"
            case .toolCall: return "Using Tool"
            case .toolResult: return "Tool Output"
            case .verification: return "Verifying"
            case .completion: return "Finished"
            case .blocker: return "Blocked"
            case .error: return "Error"
            case .fileEdit: return "Editing File"
            case .message: return "Message"
            }
        }

        var icon: String {
            switch self {
            case .planning: return "brain.head.profile"
            case .modelCall: return "cpu"
            case .toolCall: return "wrench.and.screwdriver"
            case .toolResult: return "text.magnifyingglass"
            case .verification: return "checkmark.shield"
            case .completion: return "checkmark.circle.fill"
            case .blocker: return "exclamationmark.triangle"
            case .error: return "xmark.octagon"
            case .fileEdit: return "doc.text"
            case .message: return "bubble.left.fill"
            }
        }
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    static func == (lhs: TaskEvent, rhs: TaskEvent) -> Bool {
        lhs.id == rhs.id
    }
}
