import SwiftUI

struct ChatView: View {
    let sessionId: UUID
    @StateObject private var viewModel: ChatViewModel
    @State private var inputText: String = ""
    
    init(sessionId: UUID) {
        self.sessionId = sessionId
        self._viewModel = StateObject(wrappedValue: ChatViewModel(sessionId: sessionId))
    }
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    LazyVStack(spacing: Spacing.md) {
                        ForEach(viewModel.messages) { message in
                            MessageRow(message: message)
                        }
                        if viewModel.isLoading {
                            ProgressView()
                                .padding()
                        }
                    }
                    .padding()
                }
                
                VStack(spacing: 0) {
                    Divider()
                        .background(DesignSystem.Colors.borderFaint)
                    
                    HStack(alignment: .bottom) {
                        TextField("Message Shaggoth...", text: $inputText, axis: .vertical)
                            .lineLimit(1...5)
                            .padding(Spacing.md)
                            .background(DesignSystem.Colors.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                            .overlay(
                                RoundedRectangle(cornerRadius: Radius.md)
                                    .strokeBorder(DesignSystem.Colors.borderFaint, lineWidth: 1)
                            )
                        
                        Button {
                            let text = inputText
                            inputText = ""
                            Task {
                                await viewModel.sendMessage(text)
                            }
                        } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .resizable()
                                .frame(width: 32, height: 32)
                                .foregroundStyle(
                                    inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                    ? DesignSystem.Colors.textMuted
                                    : DesignSystem.Colors.accent
                                )
                        }
                        .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)
                        .padding(.leading, Spacing.sm)
                        .padding(.bottom, Spacing.sm)
                    }
                    .padding(Spacing.md)
                    .background(DesignSystem.Colors.base)
                }
            }
            .background(DesignSystem.Colors.base)
            .navigationTitle("Shaggoth")
            .navigationBarTitleDisplayMode(.inline)
            .task {
                await viewModel.loadHistory()
            }
        }
    }
}

struct MessageRow: View {
    let message: ChatMessage
    
    var isUser: Bool {
        message.role == .user
    }
    
    var body: some View {
        HStack {
            if isUser { Spacer() }
            
            Text(message.content)
                .font(DesignSystem.Typography.body)
                .padding(Spacing.md)
                .background(isUser ? DesignSystem.Colors.accentDeep : DesignSystem.Colors.elevated)
                .foregroundStyle(isUser ? Color.white : DesignSystem.Colors.textPrimary)
                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.md)
                        .strokeBorder(isUser ? Color.clear : DesignSystem.Colors.borderFaint, lineWidth: 1)
                )
            
            if !isUser { Spacer() }
        }
    }
}
