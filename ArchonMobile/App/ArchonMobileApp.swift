import SwiftUI

@main
struct ArchonMobileApp: App {
    @StateObject private var authManager = AuthManager.shared
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

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
        }
    }
}
