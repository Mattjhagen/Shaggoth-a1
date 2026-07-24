import Foundation
import Combine

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var appearance: AppearanceMode = .dark
    @Published var apiEndpoint: String = ""
    @Published var showResetAlert = false
    @Published var showDeleteAlert = false
    @Published var isSigningOut = false
    @Published var appVersion: String = "1.0.0"

    enum AppearanceMode: String, CaseIterable {
        case light
        case dark
        case glass
        case system

        var displayName: String {
            switch self {
            case .light: return "Light"
            case .dark: return "Dark"
            case .glass: return "Glass"
            case .system: return "System"
            }
        }

        var icon: String {
            switch self {
            case .light: return "sun.max.fill"
            case .dark: return "moon.fill"
            case .glass: return "circle.hexagongrid.fill"
            case .system: return "circle.lefthalf.filled"
            }
        }
    }

    init() {
        if let saved = UserDefaults.standard.string(forKey: "appearance"),
           let mode = AppearanceMode(rawValue: saved) {
            self.appearance = mode
        }
        self.apiEndpoint = UserDefaults.standard.string(forKey: "apiEndpoint") ?? Environment.current.apiBaseURL.absoluteString

        if let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String {
            self.appVersion = version
        }
    }

    func saveAppearance(_ mode: AppearanceMode) {
        appearance = mode
        UserDefaults.standard.set(mode.rawValue, forKey: "appearance")
    }

    func saveAPIEndpoint(_ url: String) {
        apiEndpoint = url
        UserDefaults.standard.set(url, forKey: "apiEndpoint")
    }

    func signOut() async {
        isSigningOut = true
        defer { isSigningOut = false }
        await AuthManager.shared.signOut()
    }
}
