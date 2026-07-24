import SwiftUI

struct BuildScreenView: View {
    @ObservedObject var viewModel: BuilderViewModel
    @StateObject private var codeViewModel = CodeBrowserViewModel()
    @State private var selectedTab: BuildTab = .preview
    @State private var showFullPreview = false
    @State private var previewScale: CGFloat = 1.0
    @State private var dragOffset: CGFloat = 0
    @State private var isPreviewFullScreen = false
    @FocusState private var isAgentFocused: Bool
    @State private var showDeployOptions = false
    @State private var inputText = ""
    @Environment(\.dismiss) var dismiss: DismissAction

    init(viewModel: BuilderViewModel) {
        self.viewModel = viewModel
    }

    // The Code tab is intentionally absent: full codebase access will be a
    // paid unlock later (the CodeBrowser module stays in the app for that).
    enum BuildTab: String, CaseIterable {
        case preview
        case agent

        var label: String {
            switch self {
            case .preview: return "Preview"
            case .agent: return "AI Agent"
            }
        }

        var icon: String {
            switch self {
            case .preview: return "eye.fill"
            case .agent: return "sparkles"
            }
        }
    }

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            VStack(spacing: 0) {
                headerBar
                tabBar
                divider
                content
            }
        }
        .preferredColorScheme(.dark)
        .fullScreenCover(isPresented: $showFullPreview) {
            fullPreviewSheet
        }
        .sheet(isPresented: $showDeployOptions) {
            if let project = viewModel.activeProject {
                PublishFlowView(project: project)
            }
        }
    }

    // MARK: - Header Bar

    private var headerBar: some View {
        HStack {
            Button {
                dismiss()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 14, weight: .semibold))
                    Text("Back")
                        .font(.system(.subheadline, design: .rounded).weight(.medium))
                }
                .foregroundStyle(DesignSystem.Colors.textSecondary)
            }
            .dsTouchTarget()

            Spacer()

            if viewModel.currentTask?.status == .completed {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(DesignSystem.Colors.success)
                    Text("Live")
                        .font(.system(.caption, design: .rounded).weight(.semibold))
                        .foregroundStyle(DesignSystem.Colors.success)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(DesignSystem.Colors.success.opacity(0.1))
                .clipShape(Capsule())
            }

            Spacer()

            if viewModel.currentTask?.status == .completed {
                Button {
                    showDeployOptions = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "globe")
                            .font(.system(size: 12, weight: .semibold))
                        Text("Publish")
                            .font(.system(.caption, design: .rounded).weight(.semibold))
                    }
                    .foregroundStyle(DesignSystem.Colors.onAccent)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(DesignSystem.Colors.accentGradient)
                    .clipShape(Capsule())
                    .dsGlow(radius: 8, opacity: 0.35)
                }
                .dsTouchTarget()
            }

            Spacer()

            if let task = viewModel.currentTask, task.status.isActive {
                Button {
                    Task { await viewModel.cancelActiveTask() }
                } label: {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(DesignSystem.Colors.danger)
                }
                .dsTouchTarget()
            } else {
                Color.clear.frame(width: 44, height: 44)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Tab Bar

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(BuildTab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        selectedTab = tab
                    }
                } label: {
                    VStack(spacing: 4) {
                        HStack(spacing: 6) {
                            Image(systemName: tab.icon)
                                .font(.system(size: 13, weight: .semibold))
                            Text(tab.label)
                                .font(.system(.subheadline, design: .rounded).weight(.semibold))
                        }
                        .foregroundStyle(selectedTab == tab ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)

                        RoundedRectangle(cornerRadius: 2)
                            .fill(selectedTab == tab ? DesignSystem.Colors.accent : Color.clear)
                            .frame(height: 3)
                            .frame(maxWidth: .infinity)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                }
                .buttonStyle(.plain)
            }
        }
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Divider

    private var divider: some View {
        Rectangle()
            .fill(DesignSystem.Colors.surfaceBorder)
            .frame(height: 1)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        // The Code and AI Agent tabs must always honor the tab selection —
        // only the Preview tab reflects build progress states.
        switch selectedTab {
        case .preview:
            if let task = viewModel.currentTask, task.status == .completed {
                previewTab(withProgress: false)
            } else if let task = viewModel.currentTask, task.status.isActive {
                previewTab(withProgress: true)
            } else {
                buildProgressPlaceholder
            }
        case .agent:
            agentTab
        }
    }

    // MARK: - Build Progress Placeholder

    private var buildProgressPlaceholder: some View {
        VStack(spacing: 24) {
            Spacer()

            ColliderLoadingView(size: 140)

            VStack(spacing: 8) {
                Text("Getting everything ready…")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("Your app is being set up. Feel free to look around —\nwe'll let you know the moment it's done.")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()
        }
    }

    // MARK: - Preview Tab

    private func previewTab(withProgress showProgress: Bool) -> some View {
        VStack(spacing: 0) {
            if showProgress, let task = viewModel.currentTask {
                BuildProgressView(
                    progress: task.maxSteps > 0 ? Double(task.currentStep) / Double(task.maxSteps) : 0,
                    currentStep: task.currentStep,
                    maxSteps: task.maxSteps,
                    status: task.status,
                    projectName: viewModel.activeProject?.name ?? "Your App"
                )
                .frame(maxHeight: .infinity)
            } else {
                previewWebView
            }
        }
    }

    // MARK: - Preview Web View

    private var previewWebView: some View {
        VStack(spacing: 0) {
            previewToolbar

            GeometryReader { geo in
                ZStack {
                    DesignSystem.Colors.base

                    PreviewPaneView(htmlContent: generatedHTML)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .padding(12)
                        .offset(y: dragOffset)
                        .scaleEffect(previewScale)
                        .gesture(
                            DragGesture(minimumDistance: 20)
                                .onChanged { value in
                                    let translation = value.translation.height
                                    if translation < 0 {
                                        dragOffset = translation * 0.5
                                        previewScale = 1.0 + min(abs(translation) / 500, 0.1)
                                    }
                                }
                                .onEnded { value in
                                    if value.translation.height < -100 {
                                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                                            showFullPreview = true
                                            dragOffset = 0
                                            previewScale = 1.0
                                        }
                                    } else {
                                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                            dragOffset = 0
                                            previewScale = 1.0
                                        }
                                    }
                                }
                        )

                    VStack {
                        Spacer()
                        dragHandle
                    }
                }
            }
        }
    }

    // MARK: - Preview Toolbar

    private var previewToolbar: some View {
        HStack {
            Image(systemName: "eye.fill")
                .foregroundStyle(DesignSystem.Colors.accent)
            Text("Live Preview")
                .font(.system(.subheadline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Spacer()

            Button {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    showFullPreview = true
                }
            } label: {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
            }
            .dsTouchTarget()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Drag Handle

    private var dragHandle: some View {
        VStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2)
                .fill(DesignSystem.Colors.textMuted.opacity(0.5))
                .frame(width: 36, height: 4)
                .padding(.top, 8)

            Text("Swipe up for full screen")
                .font(.system(.caption2, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textMuted)
        }
        .padding(.bottom, 8)
    }

    // MARK: - Code Tab

    private var codeTab: some View {
        VStack(spacing: 0) {
            codeToolbar
            Divider().background(DesignSystem.Colors.surfaceBorder)

            CodeBrowserView(project: viewModel.activeProject)
                .environmentObject(codeViewModel)
        }
    }

    // MARK: - Code Toolbar

    private var codeToolbar: some View {
        HStack {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .foregroundStyle(DesignSystem.Colors.accent)
            Text("Source Code")
                .font(.system(.subheadline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Spacer()

            if let file = codeViewModel.selectedFile {
                Text(file.name)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(DesignSystem.Colors.textMuted)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(DesignSystem.Colors.elevated)
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Agent Tab

    private var agentTab: some View {
        VStack(spacing: 0) {
            agentToolbar
            Divider().background(DesignSystem.Colors.surfaceBorder)

            agentChatContent

            Divider().background(DesignSystem.Colors.surfaceBorder)
            agentComposer
        }
    }

    // MARK: - Agent Toolbar

    private var agentToolbar: some View {
        HStack {
            Image(systemName: "sparkles")
                .foregroundStyle(DesignSystem.Colors.accent)
            Text("AI Agent")
                .font(.system(.subheadline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Spacer()

            if let task = viewModel.currentTask {
                HStack(spacing: 4) {
                    Circle()
                        .fill(task.status.isActive ? DesignSystem.Colors.accent : DesignSystem.Colors.success)
                        .frame(width: 6, height: 6)
                    Text(task.status.rawValue.capitalized)
                        .font(.system(.caption2, design: .rounded).weight(.medium))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(DesignSystem.Colors.elevated)
                .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Agent Chat Content

    private var agentChatContent: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
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
                        .id("typing")
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .onChange(of: viewModel.messages.count) { _, _ in
                withAnimation {
                    if let last = viewModel.messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    } else if viewModel.isStreaming {
                        proxy.scrollTo("typing", anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Agent Composer

    private var agentComposer: some View {
        VStack(spacing: 0) {
            if !viewModel.pendingAttachments.isEmpty {
                AttachmentTray(viewModel: viewModel)
            }

            if !viewModel.queuedMessages.isEmpty {
                queuedBanner
            } else if !viewModel.followUpSuggestions.isEmpty {
                agentSuggestionsRow
            }

            agentComposerField
        }
    }

    private var agentSuggestionsRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.followUpSuggestions, id: \.self) { suggestion in
                    Button {
                        Task {
                            await viewModel.submit(
                                message: suggestion,
                                projectId: viewModel.activeProject?.id
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
                    }
                    .dsPressable()
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .background(DesignSystem.Colors.surface)
    }

    private var queuedBanner: some View {
        HStack(spacing: 6) {
            Image(systemName: "hourglass")
                .font(.system(size: 10))
            Text("\(viewModel.queuedMessages.count) message\(viewModel.queuedMessages.count == 1 ? "" : "s") waiting — sends when the AI is free")
                .font(.system(.caption2, design: .rounded).weight(.medium))
            Spacer()
        }
        .foregroundStyle(DesignSystem.Colors.textMuted)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(DesignSystem.Colors.surface)
    }

    private var agentComposerField: some View {
        HStack(alignment: .bottom, spacing: 12) {
            AttachmentPickerButton(viewModel: viewModel)

            TextField("Ask for anything...", text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .focused($isAgentFocused)
                .onAppear {
                    isAgentFocused = true
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(DesignSystem.Colors.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .stroke(DesignSystem.Colors.surfaceBorder, lineWidth: 1)
                )

            if viewModel.isStreaming || viewModel.currentTask?.status.isActive == true {
                Button {
                    Task { await viewModel.cancelActiveTask() }
                } label: {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(DesignSystem.Colors.danger)
                }
                .accessibilityLabel("Stop the build")
                .dsTouchTarget()
            }

            // Never interrupts the build — while the AI is busy, new
            // messages wait in the queue.
            Button {
                let text = inputText
                inputText = ""
                Task {
                    await viewModel.submit(message: text, projectId: viewModel.activeProject?.id)
                }
            } label: {
                Image(systemName: viewModel.isStreaming ? "text.append" : "arrow.up.circle.fill")
                    .font(.system(size: viewModel.isStreaming ? 26 : 32))
                    .foregroundStyle(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? DesignSystem.Colors.textMuted : DesignSystem.Colors.accent)
            }
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .accessibilityLabel(viewModel.isStreaming ? "Add message to queue" : "Send message")
            .dsTouchTarget()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Full Preview Sheet

    private var fullPreviewSheet: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                VStack(spacing: 0) {
                    dragHandleFull
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 30)
                                .onEnded { value in
                                    if value.translation.height > 60 {
                                        showFullPreview = false
                                    }
                                }
                        )
                    PreviewPaneView(htmlContent: generatedHTML)
                }
            }
            .navigationTitle("Preview: \(viewModel.activeProject?.name ?? "App")")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        showFullPreview = false
                    } label: {
                        Text("Done")
                            .fontWeight(.semibold)
                    }
                    .dsTouchTarget()
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Full Preview Drag Handle

    private var dragHandleFull: some View {
        VStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2)
                .fill(DesignSystem.Colors.textMuted.opacity(0.5))
                .frame(width: 36, height: 4)
                .padding(.top, 8)

            Text("Pull down to close")
                .font(.system(.caption2, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textMuted)
        }
        .padding(.bottom, 8)
    }

    // MARK: - Generated HTML

    private var generatedHTML: String {
        if let project = viewModel.activeProject {
            let projectName = project.name
            let description = project.description ?? "Built with Archon"
            return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <title>\(projectName)</title>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
                        background: linear-gradient(135deg, #0A0A14 0%, #14142A 50%, #1E1E3A 100%);
                        min-height: 100vh;
                        color: #EEEF8;
                        padding: 24px;
                        padding-top: env(safe-area-inset-top, 24px);
                    }
                    .container {
                        max-width: 480px;
                        margin: 0 auto;
                        padding: 20px 0;
                    }
                    h1 {
                        font-size: 28px;
                        font-weight: 700;
                        margin-bottom: 8px;
                        background: linear-gradient(135deg, #00E8CA, #009A8C);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                    }
                    p {
                        font-size: 16px;
                        color: #8888AA;
                        margin-bottom: 24px;
                        line-height: 1.5;
                    }
                    .card {
                        background: rgba(30, 30, 58, 0.8);
                        border: 1px solid rgba(42, 42, 80, 0.5);
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 16px;
                        backdrop-filter: blur(10px);
                    }
                    .status {
                        display: inline-block;
                        padding: 4px 12px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: 600;
                        background: rgba(0, 232, 202, 0.15);
                        color: #00E8CA;
                    }
                    .btn {
                        display: block;
                        width: 100%;
                        padding: 14px;
                        border: none;
                        border-radius: 12px;
                        font-size: 16px;
                        font-weight: 600;
                        cursor: pointer;
                        background: linear-gradient(135deg, #009A8C, #00E8CA);
                        color: #0A0A14;
                        margin-top: 16px;
                        transition: transform 0.2s, opacity 0.2s;
                    }
                    .btn:active { transform: scale(0.98); opacity: 0.9; }
                    .timestamp { font-size: 12px; color: #505070; margin-top: 12px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>\(projectName)</h1>
                    <p>\(description)</p>
                    <div class="card">
                        <span class="status">Live</span>
                        <div class="timestamp">Built with Archon AI</div>
                    </div>
                    <button class="btn" onclick="alert('App is live!')">Open App</button>
                </div>
            </body>
            </html>
            """
        } else {
            return """
            <!DOCTYPE html>
            <html>
            <head><style>
                body { font-family: sans-serif; text-align: center; padding: 50px; background: #0A0A14; color: #EEEF8; }
                h1 { color: #00E8CA; }
            </style></head>
            <body>
                <h1>No Project Selected</h1>
                <p>Select a project to preview</p>
            </body>
            </html>
            """
        }
    }
}

#Preview {
    BuildScreenView(viewModel: BuilderViewModel())
}
