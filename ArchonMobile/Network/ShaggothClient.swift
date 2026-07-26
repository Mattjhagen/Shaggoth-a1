import Foundation

class ShaggothClient {
    static let shared = ShaggothClient()
    
    private let urlSession: URLSession
    
    init(urlSession: URLSession = .shared) {
        self.urlSession = urlSession
    }
    
    private var apiBaseURL: URL {
        return AppEnvironment.current.apiBaseURL
    }
    
    func sendMessage(_ message: String, sessionId: String = "default") async throws -> ShaggothChatResponse {
        let url = apiBaseURL.appendingPathComponent("chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ShaggothChatRequest(message: message, sessionId: sessionId)
        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(body)
        
        if let apiKey = AppEnvironment.current.shaggothAPIKey, !apiKey.isEmpty {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        if (200...299).contains(httpResponse.statusCode) {
            let decoder = JSONDecoder()
            return try decoder.decode(ShaggothChatResponse.self, from: data)
        } else {
            throw URLError(.badServerResponse)
        }
    }
    
    func fetchHistory(sessionId: String = "default") async throws -> ShaggothHistoryResponse {
        var components = URLComponents(url: apiBaseURL.appendingPathComponent("history"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "session_id", value: sessionId)]
        
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        if let apiKey = AppEnvironment.current.shaggothAPIKey, !apiKey.isEmpty {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await urlSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(ShaggothHistoryResponse.self, from: data)
    }
}
