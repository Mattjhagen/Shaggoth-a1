import Foundation

enum TaskStatus: String, Codable, CaseIterable {
    case queued
    case planning
    case running
    case verifying
    case completed
    case blocked
    case failed
    case cancelling
    case cancelled

    var isActive: Bool {
        switch self {
        case .queued, .planning, .running, .verifying, .cancelling:
            return true
        case .completed, .blocked, .failed, .cancelled:
            return false
        }
    }

    var displayIcon: String {
        switch self {
        case .queued: return "clock"
        case .planning: return "brain.head.profile"
        case .running: return "bolt.fill"
        case .verifying: return "checkmark.shield"
        case .completed: return "checkmark.circle.fill"
        case .blocked: return "exclamationmark.triangle.fill"
        case .failed: return "xmark.circle.fill"
        case .cancelling: return "xmark"
        case .cancelled: return "slash.circle"
        }
    }
}

enum ReasoningEffort: String, Codable, CaseIterable {
    case low
    case medium
    case high

    var displayName: String {
        switch self {
        case .low: return "Low"
        case .medium: return "Medium"
        case .high: return "High"
        }
    }
}
