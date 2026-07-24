import SwiftUI
import UIKit

@main
struct ArchonMobileApp: App {
    @UIApplicationDelegateAdaptor(ArchonAppDelegate.self) private var appDelegate
    @StateObject private var authManager = AuthManager.shared
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false
    @AppStorage("appearance") private var appearance = SettingsViewModel.AppearanceMode.dark.rawValue
    @AppStorage("keepScreenAwake") private var keepScreenAwake = false

    var body: some Scene {
        WindowGroup {
            Group {
                if !hasCompletedOnboarding {
                    OnboardingFlow(hasCompletedOnboarding: $hasCompletedOnboarding)
                } else if authManager.isAuthenticated {
                    MainTabView()
                } else {
                    AuthView()
                }
            }
            .animation(.easeInOut(duration: 0.3), value: authManager.isAuthenticated)
            .animation(.easeInOut(duration: 0.3), value: hasCompletedOnboarding)
            .environmentObject(authManager)
            .tint(DesignSystem.Colors.accent)
            .preferredColorScheme(preferredColorScheme)
            .background {
                if appearance == SettingsViewModel.AppearanceMode.glass.rawValue {
                    GlassAtmosphere()
                        .ignoresSafeArea()
                }
            }
            .onAppear {
                updateScreenTimeout()
            }
            .onChange(of: keepScreenAwake) { _, _ in
                updateScreenTimeout()
            }
        }
    }

    private func updateScreenTimeout() {
        UIApplication.shared.isIdleTimerDisabled = keepScreenAwake
    }

    private var preferredColorScheme: ColorScheme? {
        switch SettingsViewModel.AppearanceMode(rawValue: appearance) ?? .dark {
        case .light: return .light
        case .dark: return .dark
        case .glass: return nil
        case .system: return nil
        }
    }
}

enum ArchonQuickAction: String {
    case newBuild = "com.matthagen.archon.new-build"
    case conversations = "com.matthagen.archon.conversations"
    case projects = "com.matthagen.archon.projects"
    case code = "com.matthagen.archon.code"
}

struct ArchonQuickActionEvent {
    let id = UUID()
    let action: ArchonQuickAction
}

final class ArchonQuickActionCenter: ObservableObject {
    static let shared = ArchonQuickActionCenter()
    @Published private(set) var event: ArchonQuickActionEvent?

    private init() {}

    func open(_ shortcutItem: UIApplicationShortcutItem) -> Bool {
        guard let action = ArchonQuickAction(rawValue: shortcutItem.type) else { return false }
        event = ArchonQuickActionEvent(action: action)
        return true
    }
}

final class ArchonAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        if let shortcutItem = options.shortcutItem {
            _ = ArchonQuickActionCenter.shared.open(shortcutItem)
        }
        return UISceneConfiguration(name: nil, sessionRole: connectingSceneSession.role)
    }

    func application(
        _ application: UIApplication,
        performActionFor shortcutItem: UIApplicationShortcutItem,
        completionHandler: @escaping (Bool) -> Void
    ) {
        completionHandler(ArchonQuickActionCenter.shared.open(shortcutItem))
    }
}

private struct GlassAtmosphere: View {
    @SwiftUI.Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ZStack {
            Color(colorScheme == .dark ? .black : .systemGroupedBackground)

            LinearGradient(
                colors: colorScheme == .dark
                    ? [Color(hex: 0x11152B), Color(hex: 0x092A2A), Color(hex: 0x1B1028)]
                    : [Color(hex: 0xE8F4FF), Color(hex: 0xE3FFF8), Color(hex: 0xF3EAFE)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            Circle()
                .fill(DesignSystem.Colors.accent.opacity(0.18))
                .frame(width: 330, height: 330)
                .blur(radius: 70)
                .offset(x: 130, y: -250)
        }
    }
}
