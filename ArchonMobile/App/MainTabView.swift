import SwiftUI

struct MainTabView: View {
    @State private var selectedTab: Tab = .chat
    @State private var sessionId: UUID = UUID()

    enum Tab: String {
        case chat
        case history
        case settings
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ChatView(sessionId: sessionId)
                .tabItem {
                    Label("Chat", systemImage: "bubble.left.and.bubble.right.fill")
                }
                .tag(Tab.chat)

            HistoryView(onSelectSession: { newSessionId in
                self.sessionId = newSessionId
                self.selectedTab = .chat
            })
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }
                .tag(Tab.history)

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
                .tag(Tab.settings)
        }
        .tint(DesignSystem.Colors.accent)
    }
}
