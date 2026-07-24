import Foundation

struct PublishedSite: Decodable {
    let id: String
    let slug: String
    let url: String
}

struct SiteNameAvailability: Decodable {
    let available: Bool
    let reason: String?
}

protocol PublishClientProtocol {
    func checkName(_ name: String) async throws -> SiteNameAvailability
    func publish(projectId: String, siteName: String) async throws -> PublishedSite
}

/// Talks to the backend's one-click publishing endpoints, which put a
/// project live at `<name>.vibecodes.space`.
final class PublishClient: PublishClientProtocol {
    private let urlSession: URLSession
    private let tokenProvider: () async throws -> String

    init(
        urlSession: URLSession = .shared,
        tokenProvider: (@Sendable () async throws -> String)? = nil
    ) {
        self.urlSession = urlSession
        self.tokenProvider = tokenProvider ?? {
            try await SupabaseClientManager.shared.client.auth.session.accessToken
        }
    }

    func checkName(_ name: String) async throws -> SiteNameAvailability {
        var components = URLComponents(
            url: AppEnvironment.current.apiBaseURL.appendingPathComponent("deployments/check"),
            resolvingAgainstBaseURL: false
        )
        components?.queryItems = [URLQueryItem(name: "name", value: name)]
        guard let url = components?.url else {
            throw APIError(message: "Invalid publish URL", code: nil)
        }
        return try await request(url: url, method: "GET", body: nil)
    }

    func publish(projectId: String, siteName: String) async throws -> PublishedSite {
        let url = AppEnvironment.current.apiBaseURL.appendingPathComponent("deployments")
        let body = try JSONSerialization.data(withJSONObject: [
            "project_id": projectId,
            "site_name": siteName
        ])
        return try await request(url: url, method: "POST", body: body)
    }

    private func request<T: Decodable>(url: URL, method: String, body: Data?) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body

        let token = try await tokenProvider()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await urlSession.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "Invalid response type", code: nil)
        }
        guard (200...299).contains(http.statusCode) else {
            let decoded = try? JSONDecoder().decode(APIError.self, from: data)
            throw APIError(
                message: decoded?.message ?? "Something went wrong while publishing",
                code: decoded?.code ?? http.statusCode
            )
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
