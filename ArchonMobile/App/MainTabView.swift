import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var selectedTab: Tab = .dashboard

    enum Tab: String {
        case dashboard
        case builder
        case code
        case settings
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView()
                .tabItem {
                    Label("Projects", systemImage: "folder.fill")
                }
                .tag(Tab.dashboard)

            BuilderView()
                .tabItem {
                    Label("Builder", systemImage: "sparkles")
                }
                .tag(Tab.builder)

            CodeBrowserView()
                .tabItem {
                    Label("Code", systemImage: "chevron.left.forwardslash.chevron.right")
                }
                .tag(Tab.code)

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
                .tag(Tab.settings)
        }
        .tint(DesignSystem.Colors.accent)
    }
}
