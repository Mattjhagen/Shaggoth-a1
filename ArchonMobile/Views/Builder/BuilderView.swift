import SwiftUI
import UIKit

struct BuilderView: View {
    let project: ArchonProject?
    let homeRequestToken: UUID
    @StateObject private var viewModel = BuilderViewModel()
    @State private var inputText = ""
    @State private var showModelPicker = false
    @State private var showNewSessionConfirmation = false
    @FocusState private var isComposerFocused: Bool

    init(project: ArchonProject? = nil, homeRequestToken: UUID = UUID()) {
        self.project = project
        self.homeRequestToken = homeRequestToken
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                VStack(spacing: 0) {
                    if viewModel.isShowingConversation {
                        modelSelectorBar
                        Divider().overlay(DesignSystem.Colors.borderFaint)
                        chatContent

                        if let error = viewModel.errorMessage {
                            errorBanner(error)
                        }

                        Divider().overlay(DesignSystem.Colors.borderFaint)
                        composerBar
                    } else {
                        conversationHome
                    }
                }
            }
            .navigationTitle(viewModel.isShowingConversation ? (viewModel.currentSession?.title ?? "New App") : "Conversations")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if viewModel.isShowingConversation {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            isComposerFocused = false
                            Task { await viewModel.showConversationList() }
                        } label: {
                            Label("Chats", systemImage: "chevron.left")
                                .labelStyle(.titleAndIcon)
                        }
                        .foregroundStyle(DesignSystem.Colors.accent)
                        .accessibilityLabel("Return to conversations")
                        .dsTouchTarget()
                    }
                }

                ToolbarItem(placement: .topBarTrailing) {
                    HStack(spacing: 8) {
                        Button {
                            isComposerFocused = false
                            showNewSessionConfirmation = true
                        } label: {
                            Image(systemName: "square.and.pencil")
                                .foregroundStyle(DesignSystem.Colors.accent)
                        }
                        .accessibilityLabel("Start new session")
                        .dsTouchTarget()

                        if viewModel.isShowingConversation {
                            Button {
                                isComposerFocused = false
                                viewModel.showEventTimeline.toggle()
                            } label: {
                                Image(systemName: "list.bullet.rectangle")
                                    .foregroundStyle(viewModel.showEventTimeline ? DesignSystem.Colors.accent : DesignSystem.Colors.textSecondary)
                            }
                            .accessibilityLabel("Toggle event timeline")
                            .dsTouchTarget()
                        }
                    }
                }

                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") {
                        isComposerFocused = false
                    }
                }
            }
            .confirmationDialog(
                "Start a new session?",
                isPresented: $showNewSessionConfirmation,
                titleVisibility: .visible
            ) {
                Button("New Session") {
                    inputText = ""
                    viewModel.startNewSession()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Your existing messages remain saved in Supabase.")
            }
            .sheet(isPresented: $viewModel.showEventTimeline) {
                eventTimelineSheet
            }
            .sheet(isPresented: $showModelPicker) {
                modelPickerSheet
            }
            .task {
                await viewModel.loadInitialState()
            }
            .onChange(of: homeRequestToken) { _, _ in
                isComposerFocused = false
                Task { await viewModel.showConversationList() }
            }
            .onDisappear {
                viewModel.stopPolling()
            }
        }
    }

    // MARK: - Conversation Home

    private var conversationHome: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("What do you want to build?")
                        .font(.system(.title2, design: .rounded).weight(.bold))
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                    Text("Start fresh with a suggestion or reopen a saved conversation.")
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                }
                .padding(.bottom, 4)

                quickStartCard("A todo app with categories and due dates", icon: "checklist")
                quickStartCard("A weather dashboard with animated icons", icon: "cloud.sun")
                quickStartCard("A recipe finder with search and filters", icon: "fork.knife")

                if let project {
                    HStack(spacing: 8) {
                        Image(systemName: "folder.fill")
                            .foregroundStyle(DesignSystem.Colors.accent)
                        Text("Building in \(project.name)")
                            .font(.system(.caption, design: .rounded).weight(.semibold))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                    }
                    .padding(.top, 4)
                }

                if !viewModel.sessions.isEmpty {
                    Text("Recent Conversations")
                        .font(.system(.headline, design: .rounded).weight(.semibold))
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                        .padding(.top, 12)

                    ForEach(viewModel.sessions) { session in
                        Button {
                            Task { await viewModel.openSession(session) }
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "bubble.left.and.bubble.right")
                                    .foregroundStyle(DesignSystem.Colors.accent)
                                    .frame(width: 28)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(session.title)
                                        .font(.system(.body, design: .rounded).weight(.medium))
                                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                                        .lineLimit(2)
                                    Text(session.updatedAt, style: .relative)
                                        .font(.system(.caption, design: .rounded))
                                        .foregroundStyle(DesignSystem.Colors.textMuted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                            }
                            .padding(14)
                            .background(DesignSystem.Colors.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md, interactive: true)
                        }
                        .buttonStyle(.plain)
                    }
                }

                if let error = viewModel.errorMessage {
                    errorBanner(error)
                }
            }
            .padding(20)
        }
        .refreshable {
            await viewModel.showConversationList()
        }
    }

    private func quickStartCard(_ prompt: String, icon: String) -> some View {
        Button {
            viewModel.startNewSession()
            inputText = prompt
            isComposerFocused = true
        } label: {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .foregroundStyle(DesignSystem.Colors.accent)
                    .frame(width: 28)
                Text(prompt)
                    .font(.system(.subheadline, design: .rounded).weight(.medium))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .multilineTextAlignment(.leading)
                Spacer()
                Image(systemName: "arrow.up.right")
                    .font(.caption)
                    .foregroundStyle(DesignSystem.Colors.textMuted)
            }
            .padding(14)
            .background(DesignSystem.Colors.elevated)
            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md, interactive: true)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Model Selector

    private var modelSelectorBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button {
                    showModelPicker = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "cpu")
                            .font(.caption2)
                        Text(selectedModelLabel)
                            .font(.system(.caption, design: .rounded).weight(.medium))
                            .lineLimit(1)
                        Image(systemName: "chevron.up.chevron.down")
                            .font(.system(size: 8))
                    }
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(DesignSystem.Colors.elevated)
                    .clipShape(Capsule())
                }
                .accessibilityLabel("Select model. Current: \(selectedModelLabel)")
                .dsTouchTarget()

                if viewModel.isTaskActive {
                    HStack(spacing: 4) {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text(viewModel.currentTask?.status.rawValue.capitalized ?? "Working...")
                            .font(.system(.caption, design: .rounded).weight(.medium))
                    }
                    .foregroundStyle(DesignSystem.Colors.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(DesignSystem.Colors.accentDim)
                    .clipShape(Capsule())
                    .accessibilityLabel("Task status: \(viewModel.currentTask?.status.rawValue ?? "unknown")")
                }

                if let task = viewModel.currentTask, task.status.isActive == false {
                    statusChip(task.status)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        }
        .background(DesignSystem.Colors.surface)
    }

    private var selectedModelLabel: String {
        guard let provider = viewModel.selectedProvider else { return "Select Model" }
        let model = provider.models.first { $0.id == viewModel.selectedModelId }
        return model.map { "\(provider.name) · \($0.name)" } ?? provider.name
    }

    private func statusChip(_ status: TaskStatus) -> some View {
        Text(status.rawValue.capitalized)
            .font(.system(.caption2, design: .rounded).weight(.semibold))
            .foregroundStyle(statusColor(status))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor(status).opacity(0.15))
            .clipShape(Capsule())
            .accessibilityLabel("Status: \(status.rawValue)")
    }

    private func statusColor(_ status: TaskStatus) -> Color {
        switch status {
        case .completed: return DesignSystem.Colors.success
        case .failed, .cancelled: return DesignSystem.Colors.danger
        case .blocked, .cancelling: return DesignSystem.Colors.warning
        default: return DesignSystem.Colors.accent
        }
    }

    // MARK: - Chat Content

    private var chatContent: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: DesignSystem.Spacing.md) {
                    if viewModel.messages.isEmpty {
                        emptyChatState
                    } else {
                        ForEach(viewModel.messages) { message in
                            ChatBubbleView(message: message)
                                .id(message.id)
                        }

                        if viewModel.isStreaming {
                            HStack {
                                TypingIndicator()
                                Spacer()
                            }
                            .padding(.horizontal, DesignSystem.Spacing.lg)
                            .id("typing")
                        }
                    }
                }
                .padding(.vertical, DesignSystem.Spacing.md)
            }
            .onChange(of: viewModel.messages.count) { _, _ in
                withAnimation {
                    let target = viewModel.messages.last.map { AnyHashable($0.id) } ?? AnyHashable("typing")
                    proxy.scrollTo(target, anchor: .bottom)
                }
            }
        }
    }

    // MARK: - Empty State

    private var emptyChatState: some View {
        VStack(spacing: 16) {
            Spacer()
                .frame(minHeight: 80)

            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "sparkles")
                    .font(.system(size: 32))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }
            .accessibilityHidden(true)

            VStack(spacing: 8) {
                Text("What do you want to build?")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .accessibilityAddTraits(.isHeader)

                Text("Describe your app idea and I'll build it for you")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            // Quick prompts
            VStack(spacing: 10) {
                quickPrompt("A todo app with categories and due dates")
                quickPrompt("A weather dashboard with animated icons")
                quickPrompt("A recipe finder with search and filters")
            }
            .padding(.horizontal, 32)
            .padding(.top, 8)

            Spacer()
        }
        .accessibilityElement(children: .combine)
    }

    private func quickPrompt(_ text: String) -> some View {
        Button {
            inputText = text
        } label: {
            HStack {
                Image(systemName: "bubble.left")
                    .font(.caption)
                Text(text)
                    .font(.system(.subheadline, design: .rounded))
                    .lineLimit(1)
                Spacer()
                Image(systemName: "arrow.up.circle")
                    .font(.caption)
            }
            .foregroundStyle(DesignSystem.Colors.textSecondary)
            .padding(12)
            .background(DesignSystem.Colors.elevated)
            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.sm, interactive: true)
        }
        .buttonStyle(.plain)
        .dsTouchTarget()
        .accessibilityLabel("Quick prompt: \(text)")
    }

    // MARK: - Composer

    private var composerBar: some View {
        VStack(spacing: 0) {
            HStack(alignment: .bottom, spacing: 10) {
                TextField("Describe your app...", text: $inputText, axis: .vertical)
                    .focused($isComposerFocused)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .lineLimit(1...5)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(DesignSystem.Colors.elevated)
                    .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                    .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md, interactive: true)

                if viewModel.isTaskActive {
                    Button {
                        Task { await viewModel.cancelActiveTask() }
                    } label: {
                        Image(systemName: "stop.circle.fill")
                            .font(.title2)
                            .foregroundStyle(DesignSystem.Colors.danger)
                    }
                    .accessibilityLabel("Cancel running task")
                    .dsTouchTarget()
                } else {
                    Button {
                        let text = inputText
                        inputText = ""
                        Task { await viewModel.send(message: text, projectId: project?.id) }
                    } label: {
                        if viewModel.isStreaming {
                            ProgressView()
                                .frame(width: 36, height: 36)
                        } else {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.title2)
                                .foregroundStyle(canSend ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                        }
                    }
                    .disabled(!canSend || viewModel.isStreaming)
                    .accessibilityLabel("Send message")
                    .dsTouchTarget()
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
        .background(DesignSystem.Colors.surface)
    }

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && viewModel.selectedProviderId != nil
    }

    // MARK: - Error Banner

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(DesignSystem.Colors.warning)

            Text(message)
                .font(.system(.caption, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textPrimary)
                .lineLimit(2)

            Spacer()

            Button {
                viewModel.errorMessage = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(DesignSystem.Colors.textMuted)
            }
            .accessibilityLabel("Dismiss error")
            .dsTouchTarget()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(DesignSystem.Colors.warning.opacity(0.12))
    }

    // MARK: - Sheets

    private var eventTimelineSheet: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                if viewModel.taskEvents.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "list.bullet.rectangle")
                            .font(.system(size: 32))
                            .foregroundStyle(DesignSystem.Colors.textMuted)
                        Text("No events yet")
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                    }
                    .accessibilityElement(children: .combine)
                } else {
                    EventTimelineView(events: viewModel.taskEvents)
                        .padding()
                }
            }
            .navigationTitle("Activity Timeline")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        viewModel.showEventTimeline = false
                    }
                    .dsTouchTarget()
                }
            }
        }
    }

    private var modelPickerSheet: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                List {
                    ForEach(viewModel.usableProviders) { provider in
                        Section(provider.name) {
                            ForEach(provider.models, id: \.id) { model in
                                Button {
                                    viewModel.selectedProviderId = provider.id
                                    viewModel.selectedModelId = model.id
                                    showModelPicker = false
                                } label: {
                                    HStack {
                                        Text(model.name)
                                            .font(.system(.body, design: .rounded))
                                            .foregroundStyle(DesignSystem.Colors.textPrimary)

                                        Spacer()

                                        if viewModel.selectedModelId == model.id {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundStyle(DesignSystem.Colors.accent)
                                        }
                                    }
                                }
                                .dsTouchTarget()
                            }
                        }
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Select Model")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        showModelPicker = false
                    }
                    .dsTouchTarget()
                }
            }
        }
    }
}

// MARK: - Chat Bubble

struct ChatBubbleView: View {
    let message: ChatMessage
    @State private var copied = false

    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 48)
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(message.role == .user ? DesignSystem.Colors.base : DesignSystem.Colors.textPrimary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(bubbleBackground)
                    .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))

                HStack(spacing: 8) {
                    Text(message.timestamp, style: .time)
                        .font(.system(.caption2, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textMuted)

                    Button {
                        UIPasteboard.general.string = message.content
                        copied = true
                        Task {
                            try? await Task.sleep(nanoseconds: 1_500_000_000)
                            copied = false
                        }
                    } label: {
                        Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                            .font(.system(.caption2, design: .rounded).weight(.medium))
                            .foregroundStyle(copied ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(copied ? "Message copied" : "Copy message")
                }
                .padding(.horizontal, 4)
            }

            if message.role == .assistant {
                Spacer(minLength: 48)
            }
        }
        .padding(.horizontal, DesignSystem.Spacing.lg)
        .contextMenu {
            Button {
                UIPasteboard.general.string = message.content
                copied = true
            } label: {
                Label("Copy Message", systemImage: "doc.on.doc")
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(message.role == .user ? "You" : "Assistant"): \(message.content)")
    }

    private var bubbleBackground: AnyShapeStyle {
        if message.role == .user {
            return AnyShapeStyle(DesignSystem.Colors.accent)
        } else {
            return AnyShapeStyle(DesignSystem.Colors.elevated)
        }
    }
}

// MARK: - Typing Indicator

struct TypingIndicator: View {
    @State private var dotOffsets: [CGFloat] = [0, 0, 0]

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(DesignSystem.Colors.textMuted)
                    .frame(width: 6, height: 6)
                    .offset(y: dotOffsets[index])
                    .animation(
                        .easeInOut(duration: 0.4).repeatForever(autoreverses: true).delay(Double(index) * 0.15),
                        value: dotOffsets[index]
                    )
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(DesignSystem.Colors.elevated)
        .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
        .onAppear {
            dotOffsets = [-4, -4, -4]
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Assistant is typing")
    }
}

#Preview {
    BuilderView()
}
