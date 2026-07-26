import Foundation

struct ShaggothChatRequest: Codable {
    let message: String
    let sessionId: String
    
    enum CodingKeys: String, CodingKey {
        case message
        case sessionId = "session_id"
    }
}

struct ShaggothChatResponse: Codable {
    let reply: String
    let sessionId: String?
    let model: String?
    let tokens: Int?
    let processingTime: Double?
    let done: Bool?
    
    enum CodingKeys: String, CodingKey {
        case reply
        case sessionId = "session_id"
        case model
        case tokens
        case processingTime = "processing_time"
        case done
    }
}

struct ShaggothMessage: Codable, Identifiable, Equatable {
    var id = UUID()
    let role: String
    let content: String
    
    enum CodingKeys: String, CodingKey {
        case role
        case content
    }
}

struct ShaggothHistoryResponse: Codable {
    let messages: [ShaggothMessage]
}
