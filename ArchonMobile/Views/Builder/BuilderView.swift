import SwiftUI
import UIKit

struct BuilderView: View {
    let project: ArchonProject?
    let homeRequestToken: UUID
    let onProjectCreated: (ArchonProject) -> Void
    @StateObject private var viewModel = BuilderViewModel()
    @State private var inputText = ""
    @State private var preselectedTemplate: IdeaTemplate?
    @State private var showBuildScreen = false
    @State private var showNewSessionConfirmation = false
    @FocusState private var isComposerFocused: Bool

    init(
        project: ArchonProject? = nil,
        homeRequestToken: UUID = UUID(),
        onProjectCreated: @escaping (ArchonProject) -> Void = { _ in }
    ) {
        self.project = project
        self.homeRequestToken = homeRequestToken
        self.onProjectCreated = onProjectCreated
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
                .animation(DesignSystem.Animation.fluid, value: viewModel.isShowingConversation)
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
            .fullScreenCover(isPresented: $showBuildScreen) {
                BuildScreenView(viewModel: viewModel)
            }
            .task {
                viewModel.useProject(project)
                await viewModel.loadInitialState()
            }
            .onChange(of: project) { _, newProject in
                viewModel.useProject(newProject)
            }
            .onChange(of: viewModel.activeProject) { _, newProject in
                if let newProject, newProject.id != project?.id {
                    onProjectCreated(newProject)
                }
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
                    Text("What do you want to make?")
                        .font(.system(.title2, design: .rounded).weight(.bold))
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                    Text("Pick a starting point or continue where you left off.")
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                }
                .padding(.bottom, 4)

                ForEach(IdeaTemplate.allCases) { template in
                    templateCard(template)
                }
                templateCard(nil)

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

    /// A template shortcut card; `nil` is the "something else" free-form entry.
    private func templateCard(_ template: IdeaTemplate?) -> some View {
        Button {
            preselectedTemplate = template
            viewModel.startNewSession()
        } label: {
            HStack(spacing: 12) {
                Image(systemName: template?.icon ?? "lightbulb")
                    .foregroundStyle(DesignSystem.Colors.accent)
                    .frame(width: 28)
                Text(template?.title ?? "Something else — describe it your way")
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

    // MARK: - Status Bar

    // The system decides which AI serves each request — no model picker.
    // The choice is visible per-reply in each message's "under the hood" log.
    private var modelSelectorBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
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
                            HStack(spacing: 10) {
                                TypingIndicator()
                                WittyLoadingText()
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
        VStack(spacing: 20) {
            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.1))
                    .frame(width: 72, height: 72)

                Image(systemName: "sparkles")
                    .font(.system(size: 28))
                    .foregroundStyle(DesignSystem.Colors.accent)
                    .dsGlow(radius: 12, opacity: 0.4)
            }
            .accessibilityHidden(true)
            .padding(.top, 20)

            VStack(spacing: 6) {
                Text("Let's make something!")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .accessibilityAddTraits(.isHeader)

                Text("Answer a couple of quick questions —\nwe'll take care of the rest.")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            IdeaCaptureView(preselectedTemplate: preselectedTemplate) { prompt in
                preselectedTemplate = nil
                Task {
                    await viewModel.send(
                        message: prompt,
                        projectId: project?.id ?? viewModel.activeProject?.id
                    )
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        showBuildScreen = true
                    }
                }
            }
            .padding(.horizontal, 24)
        }
    }

    // MARK: - Composer

    private var composerBar: some View {
        VStack(spacing: 0) {
            if !viewModel.pendingAttachments.isEmpty {
                AttachmentTray(viewModel: viewModel)
            }

            if !viewModel.queuedMessages.isEmpty {
                queuedMessagesRow
            } else if !viewModel.followUpSuggestions.isEmpty {
                suggestionsRow
            }

            HStack(alignment: .bottom, spacing: 10) {
                AttachmentPickerButton(viewModel: viewModel)
                TextField("Describe your app...", text: $inputText, axis: .vertical)
                    .focused($isComposerFocused)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .lineLimit(1...5)
                    .focused($isComposerFocused)
                    .onAppear {
                        isComposerFocused = true
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(DesignSystem.Colors.elevated)
                    .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                    .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md, interactive: true)

                if viewModel.isTaskActive {
                    Button {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            showBuildScreen = true
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 14))
                            Text("View Build")
                                .font(.system(.caption, design: .rounded).weight(.semibold))
                        }
                        .foregroundStyle(DesignSystem.Colors.onAccent)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(DesignSystem.Colors.accentGradient)
                        .clipShape(Capsule())
                    }
                    .accessibilityLabel("View build progress")
                    .dsTouchTarget()
                }

                // Sending never interrupts a build — while the AI is busy,
                // new messages join the queue instead.
                Button {
                    let text = inputText
                    inputText = ""
                    Task {
                        let sentNow = await viewModel.submit(
                            message: text,
                            projectId: project?.id ?? viewModel.activeProject?.id
                        )
                        if sentNow {
                            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                                showBuildScreen = true
                            }
                        }
                    }
                } label: {
                    Image(systemName: viewModel.isStreaming ? "text.append" : "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(canSend ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                }
                .disabled(!canSend)
                .accessibilityLabel(viewModel.isStreaming ? "Add message to queue" : "Send message")
                .dsTouchTarget()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
        .background(DesignSystem.Colors.surface)
    }

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && viewModel.selectedProviderId != nil
    }

    // MARK: - Suggestions & Queue Rows

    private var suggestionsRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.followUpSuggestions, id: \.self) { suggestion in
                    Button {
                        Task {
                            await viewModel.submit(
                                message: suggestion,
                                projectId: project?.id ?? viewModel.activeProject?.id
                            )
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "sparkle")
                                .font(.system(size: 9))
                            Text(suggestion)
                                .font(.system(.caption, design: .rounded).weight(.medium))
                                .lineLimit(1)
                        }
                        .foregroundStyle(DesignSystem.Colors.accent)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .background(DesignSystem.Colors.accent.opacity(0.1))
                        .clipShape(Capsule())
                        .overlay(
                            Capsule().strokeBorder(DesignSystem.Colors.accent.opacity(0.25), lineWidth: 1)
                        )
                    }
                    .dsPressable()
                    .accessibilityLabel("Suggestion: \(suggestion)")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        }
        .background(DesignSystem.Colors.surface)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }

    private var queuedMessagesRow: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Waiting in line — sends when the AI is free")
                .font(.system(.caption2, design: .rounded).weight(.medium))
                .foregroundStyle(DesignSystem.Colors.textMuted)
                .padding(.horizontal, 14)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(viewModel.queuedMessages) { queued in
                        HStack(spacing: 6) {
                            Image(systemName: "hourglass")
                                .font(.system(size: 9))
                            Text(queued.text)
                                .font(.system(.caption, design: .rounded))
                                .lineLimit(1)
                                .frame(maxWidth: 180, alignment: .leading)

                            Button {
                                viewModel.cancelQueuedMessage(queued.id)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                            }
                            .accessibilityLabel("Remove from queue")
                        }
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(DesignSystem.Colors.elevated)
                        .clipShape(Capsule())
                    }
                }
                .padding(.horizontal, 14)
            }
        }
        .padding(.vertical, 8)
        .background(DesignSystem.Colors.surface)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
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

}

// MARK: - Chat Bubble

struct ChatBubbleView: View {
    let message: ChatMessage
    @State private var copied = false
    @State private var showDetails = false

    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 48)
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                if let imageDatas = message.localImageData, !imageDatas.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(Array(imageDatas.enumerated()), id: \.offset) { _, data in
                            if let image = UIImage(data: data) {
                                Image(uiImage: image)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 88, height: 88)
                                    .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
                            }
                        }
                    }
                    .accessibilityLabel("\(imageDatas.count) attached image\(imageDatas.count == 1 ? "" : "s")")
                }

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

                    if message.role == .assistant, message.details != nil {
                        Button {
                            withAnimation(DesignSystem.Animation.snappy) {
                                showDetails.toggle()
                            }
                        } label: {
                            HStack(spacing: 3) {
                                Image(systemName: "wrench.and.screwdriver")
                                    .font(.system(size: 9))
                                Text("Under the hood")
                                    .font(.system(.caption2, design: .rounded).weight(.medium))
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 8, weight: .bold))
                                    .rotationEffect(.degrees(showDetails ? 180 : 0))
                            }
                            .foregroundStyle(showDetails ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(showDetails ? "Hide technical details" : "Show technical details")
                    }
                }
                .padding(.horizontal, 4)

                if showDetails, let details = message.details {
                    underTheHoodLog(details)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
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

    /// The technical log tucked beneath friendly replies — which AI served
    /// the request, token counts, and timing, for the curious.
    private func underTheHoodLog(_ details: ChatMessage.BuildDetails) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            logRow("AI", "\(details.provider) · \(details.model)")
            if let input = details.inputTokens, let output = details.outputTokens {
                logRow("Tokens", "\(input) in · \(output) out")
            }
            if let seconds = details.elapsedSeconds {
                logRow("Time", String(format: "%.1fs", seconds))
            }
        }
        .padding(10)
        .background(DesignSystem.Colors.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous)
                .strokeBorder(DesignSystem.Colors.borderFaint, lineWidth: 1)
        )
    }

    private func logRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.system(.caption2, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textMuted)
                .frame(width: 44, alignment: .leading)
            Text(value)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
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
