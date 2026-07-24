import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authManager: AuthManager
    @ObservedObject private var quickActions = ArchonQuickActionCenter.shared
    @State private var selectedTab: Tab = .dashboard
    @State private var selectedProject: ArchonProject?
    @State private var builderHomeRequest = UUID()

    enum Tab: String {
        case dashboard
        case builder
        case code
        case settings
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView(
                onProjectSelected: { project in
                    selectedProject = project
                    builderHomeRequest = UUID()
                    selectedTab = .builder
                },
                onProjectDeleted: { project in
                    guard selectedProject?.id == project.id else { return }
                    selectedProject = nil
                    builderHomeRequest = UUID()
                }
            )
                .tabItem {
                    Label("Projects", systemImage: "folder.fill")
                }
                .tag(Tab.dashboard)

            BuilderView(
                project: selectedProject,
                homeRequestToken: builderHomeRequest,
                onProjectCreated: { project in
                    selectedProject = project
                }
            )
                .tabItem {
                    Label("Builder", systemImage: "sparkles")
                }
                .tag(Tab.builder)

            // Code browsing is a future in-app purchase — the tab shows a
            // locked teaser until then (CodeBrowserView stays in the app).
            CodeAccessLockedView()
                .tabItem {
                    Label("Code", systemImage: "lock")
                }
                .tag(Tab.code)

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
                .tag(Tab.settings)
        }
        .tint(DesignSystem.Colors.accent)
        .onReceive(quickActions.$event.compactMap { $0 }) { event in
            handleQuickAction(event.action)
        }
    }

    private func handleQuickAction(_ action: ArchonQuickAction) {
        switch action {
        case .newBuild, .conversations:
            selectedProject = nil
            builderHomeRequest = UUID()
            selectedTab = .builder
        case .projects:
            selectedTab = .dashboard
        case .code:
            selectedTab = .code
        }
    }
}
