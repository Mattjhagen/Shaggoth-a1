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

    var supabaseURL: URL {
        switch self {
        case .development:
            let custom = Bundle.main.infoDictionary?["SUPABASE_URL"] as? String
            return URL(string: custom ?? "http://localhost:54321")!
        case .staging:
            return URL(string: "https://staging.archon.app")!
        case .production:
            let custom = Bundle.main.infoDictionary?["SUPABASE_URL"] as? String
            return URL(string: custom ?? "https://sbbkmdnyzzidywjkdhye.supabase.co")!
        }
    }

    var supabaseAnonKey: String {
        return Bundle.main.infoDictionary?["SUPABASE_ANON_KEY"] as? String ?? "MOCK_ANON_KEY"
    }

    var apiBaseURL: URL {
        let custom = Bundle.main.infoDictionary?["API_BASE_URL"] as? String
        return URL(string: custom ?? "https://app.relayapp.pro/api")!
    }
}
