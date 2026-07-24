import Foundation

enum Environment {
    case development
    case staging
    case production

    static var current: Environment {
        #if DEBUG
        return .development
        #else
        return .production
        #endif
    }

    /// Native callback used for Supabase email confirmation and OAuth flows.
    /// This exact URL must also be present in Supabase Auth's Redirect URLs.
    static let authRedirectURL = URL(string: "com.matthagen.archon://auth/callback")!

    var supabaseURL: URL {
        switch self {
        case .development:
            let custom = Bundle.main.infoDictionary?["SUPABASE_URL"] as? String
            return Self.secureURL(
                custom,
                fallback: URL(string: "https://sbbkmdnyzzidywjkdhye.supabase.co")!
            )
        case .staging:
            return URL(string: "https://staging.archon.app")!
        case .production:
            let custom = Bundle.main.infoDictionary?["SUPABASE_URL"] as? String
            return Self.secureURL(
                custom,
                fallback: URL(string: "https://sbbkmdnyzzidywjkdhye.supabase.co")!
            )
        }
    }

    var supabaseAnonKey: String {
        let value = Bundle.main.infoDictionary?["SUPABASE_ANON_KEY"] as? String
        guard let value,
              !value.isEmpty,
              !value.hasPrefix("$("),
              value != "YOUR_ANON_KEY_HERE" else {
            return "CONFIGURATION_REQUIRED"
        }
        return value
    }

    var apiBaseURL: URL {
        let fallback = URL(string: "https://archon-ide-pacmac.fly.dev/api")!
        let saved = UserDefaults.standard.string(forKey: "apiEndpoint")
        if let savedURL = Self.validAPIURL(saved) {
            return savedURL
        }
        let configured = Bundle.main.infoDictionary?["API_BASE_URL"] as? String
        return Self.secureURL(configured, fallback: fallback)
    }

    static func validAPIURL(_ value: String?) -> URL? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              !trimmed.hasPrefix("$("),
              let url = URL(string: trimmed),
              url.host != nil else {
            return nil
        }

        if url.scheme?.lowercased() == "https" {
            return url
        }

        #if DEBUG
        if url.scheme?.lowercased() == "http",
           ["localhost", "127.0.0.1"].contains(url.host?.lowercased() ?? "") {
            return url
        }
        #endif

        return nil
    }

    private static func secureURL(
        _ value: String?,
        fallback: URL,
        allowLocalHTTP: Bool = false
    ) -> URL {
        if allowLocalHTTP,
           let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
           let url = URL(string: trimmed),
           url.host != nil,
           ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
            return url
        }
        return validAPIURL(value) ?? fallback
    }
}
