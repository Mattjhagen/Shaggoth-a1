import SwiftUI

struct HistoryView: View {
    let onSelectSession: (UUID) -> Void
    @State private var sessions: [ChatSession] = []
    @State private var isLoading = false
    
    var body: some View {
        NavigationStack {
            List(sessions) { session in
                Button {
                    onSelectSession(session.id)
                } label: {
                    VStack(alignment: .leading) {
                        Text(session.title)
                            .font(DesignSystem.Typography.body.bold())
                            .foregroundStyle(DesignSystem.Colors.textPrimary)
                        Text(session.createdAt.formatted(date: .abbreviated, time: .shortened))
                            .font(DesignSystem.Typography.caption)
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                    }
                }
            }
            .navigationTitle("History")
            .background(DesignSystem.Colors.base)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: createNewSession) {
                        Image(systemName: "square.and.pencil")
                    }
                }
            }
            .task {
                await loadSessions()
            }
        }
    }
    
    private func loadSessions() async {
        isLoading = true
        do {
            let client = SupabaseChatMemoryClient()
            self.sessions = try await client.fetchSessions()
        } catch {
            print("Error loading sessions: \(error)")
        }
        isLoading = false
    }
    
    private func createNewSession() {
        Task {
            do {
                let client = SupabaseChatMemoryClient()
                let session = try await client.createSession(title: "New Chat", providerId: "shaggoth", modelId: "shaggoth-a1", projectId: nil)
                self.sessions.insert(session, at: 0)
                onSelectSession(session.id)
            } catch {
                print("Error creating session: \(error)")
            }
        }
    }
}
