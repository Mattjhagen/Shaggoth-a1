import Foundation

struct APIError: Codable, LocalizedError {
    let message: String
    let code: Int?

    init(message: String, code: Int? = nil) {
        self.message = message
        self.code = code
    }

    private enum CodingKeys: String, CodingKey {
        case message
        case error
        case code
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let value = try container.decodeIfPresent(String.self, forKey: .message) {
            message = value
        } else if let value = try container.decodeIfPresent(String.self, forKey: .error) {
            message = value
        } else {
            throw DecodingError.keyNotFound(
                CodingKeys.message,
                DecodingError.Context(
                    codingPath: decoder.codingPath,
                    debugDescription: "Expected either 'message' or 'error' key"
                )
            )
        }
        code = try container.decodeIfPresent(Int.self, forKey: .code)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(message, forKey: .message)
        try container.encodeIfPresent(code, forKey: .code)
    }

    var errorDescription: String? {
        if let code {
            return "\(message) (HTTP \(code))"
        }
        return message
    }
}
