import Foundation
import SwiftUI

@MainActor
class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String? = nil
    
    private let shaggothClient = ShaggothClient.shared
    private let dbClient = SupabaseChatMemoryClient()
    private let sessionId: UUID
    
    init(sessionId: UUID) {
        self.sessionId = sessionId
    }
    
    func loadHistory() async {
        isLoading = true
        errorMessage = nil
        do {
            self.messages = try await dbClient.fetchMessages(sessionId: sessionId, limit: 100)
        } catch {
            print("Failed to load history from Supabase: \(error)")
            self.errorMessage = "Failed to load history."
        }
        isLoading = false
    }
    
    func sendMessage(_ text: String) async {
        isLoading = true
        errorMessage = nil
        
        do {
            // Save user message to Supabase
            let userMessage = ChatMessage(role: .user, content: text)
            try await dbClient.saveMessage(userMessage, sessionId: sessionId, providerId: "shaggoth", modelId: "shaggoth-a1", projectId: nil)
            self.messages.append(userMessage)
            
            // Send to Shaggoth
            let response = try await shaggothClient.sendMessage(text, sessionId: sessionId.uuidString)
            
            // Save AI reply to Supabase
            let botMessage = ChatMessage(role: .assistant, content: response.reply)
            try await dbClient.saveMessage(botMessage, sessionId: sessionId, providerId: "shaggoth", modelId: "shaggoth-a1", projectId: nil)
            self.messages.append(botMessage)
            
        } catch {
            self.errorMessage = "Failed to send message: \(error.localizedDescription)"
            print(error)
        }
        
        isLoading = false
    }
}
