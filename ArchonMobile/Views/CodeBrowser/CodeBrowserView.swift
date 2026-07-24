import SwiftUI

struct CodeBrowserView: View {
    @StateObject private var viewModel = CodeBrowserViewModel()
    @Environment(\.horizontalSizeClass) private var hSizeClass
    @EnvironmentObject var authManager: AuthManager
    @State private var selectedCodeTab: CodeTab = .code

    enum CodeTab: String, CaseIterable {
        case code
        case todo

        var label: String {
            switch self {
            case .code: return "Code"
            case .todo: return "Tasks"
            }
        }

        var icon: String {
            switch self {
            case .code: return "chevron.left.forwardslash.chevron.right"
            case .todo: return "checklist"
            }
        }
    }

    var body: some View {
        Group {
            if hSizeClass == .regular {
                splitLayout
            } else {
                compactLayout
            }
        }
        .environmentObject(viewModel)
        .tint(DesignSystem.Colors.accent)
        .preferredColorScheme(.dark)
    }

    // MARK: - iPad Layout

    private var splitLayout: some View {
        NavigationSplitView {
            fileExplorerColumn
                .navigationSplitViewColumnWidth(min: 200, ideal: 260, max: 340)
        } detail: {
            editorColumn
        }
        .background(DesignSystem.Colors.base)
    }

    // MARK: - iPhone Layout

    private var compactLayout: some View {
        NavigationStack {
            editorColumn
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        NavigationLink {
                            fileExplorerSheet
                        } label: {
                            Image(systemName: "sidebar.left")
                        }
                        .accessibilityLabel("Show file explorer")
                        .dsTouchTarget()
                    }

                    ToolbarItem(placement: .principal) {
                        Text(viewModel.selectedFile?.name ?? "Code")
                            .font(.system(.subheadline, design: .rounded).weight(.semibold))
                            .foregroundStyle(DesignSystem.Colors.textPrimary)
                            .lineLimit(1)
                            .accessibilityAddTraits(.isHeader)
                    }

                    if viewModel.isPreviewableFile {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                viewModel.togglePreview()
                            } label: {
                                Image(systemName: viewModel.showPreview ? "eye.slash" : "eye")
                            }
                            .accessibilityLabel(viewModel.showPreview ? "Hide preview" : "Show preview")
                            .dsTouchTarget()
                        }
                    }
                }
        }
    }

    // MARK: - File Explorer

    private var fileExplorerColumn: some View {
        List(viewModel.filteredTree, children: \.children) { node in
            Button {
                viewModel.selectFile(node)
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: node.iconName)
                        .font(.subheadline)
                        .foregroundStyle(node.iconColor)
                        .frame(width: 20)

                    Text(node.name)
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(
                            viewModel.selectedFile?.id == node.id
                                ? DesignSystem.Colors.accent
                                : DesignSystem.Colors.textPrimary
                        )
                        .lineLimit(1)

                    Spacer()

                    if let size = node.size {
                        Text(ByteCountFormatter.string(fromByteCount: size, countStyle: .file))
                            .font(.system(.caption2, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textMuted)
                    }
                }
                .frame(minHeight: 44)
                .accessibilityElement(children: .combine)
                .accessibilityLabel(
                    node.type == .folder ? "Folder, \(node.name)" : "File, \(node.name)"
                )
            }
            .disabled(node.type == .folder)
            .listRowBackground(
                viewModel.selectedFile?.id == node.id
                    ? DesignSystem.Colors.accentDim
                    : Color.clear
            )
        }
        .navigationTitle("Explorer")
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(DesignSystem.Colors.surface)
        .searchable(text: $viewModel.searchQuery, prompt: "Search files")
    }

    private var fileExplorerSheet: some View {
        NavigationStack {
            fileExplorerColumn
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") {
                            // Dismiss
                        }
                        .dsTouchTarget()
                    }
                }
        }
        .preferredColorScheme(.dark)
        .tint(DesignSystem.Colors.accent)
    }

    // MARK: - Editor

    private var editorColumn: some View {
        VStack(spacing: 0) {
            codeTabBar
            Divider().background(DesignSystem.Colors.surfaceBorder)

            if selectedCodeTab == .todo {
                TodoView(projectId: "current", projectName: "Tasks")
                    .environmentObject(authManager)
            } else {
                if let file = viewModel.selectedFile {
                    if !viewModel.openFiles.isEmpty {
                        tabBar
                        Divider().overlay(DesignSystem.Colors.borderFaint)
                    }

                    VStack(spacing: 0) {
                        if viewModel.showPreview && viewModel.isPreviewableFile {
                            GeometryReader { geo in
                                VStack(spacing: 0) {
                                    syntaxEditor
                                        .frame(height: geo.size.height * 0.55)

                                    Divider().overlay(DesignSystem.Colors.borderFaint)

                                    PreviewPaneView(htmlContent: file.content ?? "")
                                        .frame(minHeight: 100)
                                }
                            }
                        } else {
                            syntaxEditor
                        }
                    }

                    if viewModel.isEditing {
                        editBar
                    }
                } else {
                    emptyEditorState
                }
            }
        }
        .background(DesignSystem.Colors.base)
    }

    // MARK: - Code/Todo Tab Bar

    private var codeTabBar: some View {
        HStack(spacing: 0) {
            ForEach(CodeTab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        selectedCodeTab = tab
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: tab.icon)
                            .font(.system(size: 12, weight: .semibold))
                        Text(tab.label)
                            .font(.system(.caption, design: .rounded).weight(.semibold))
                    }
                    .foregroundStyle(selectedCodeTab == tab ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .background(DesignSystem.Colors.surface)
    }

    private var syntaxEditor: some View {
        SyntaxEditorView(
            text: $viewModel.editingContent,
            language: determineLanguage(filename: viewModel.selectedFile?.name ?? ""),
            isEditing: viewModel.isEditing
        )
        .background(DesignSystem.Colors.base)
    }

    private var emptyEditorState: some View {
        VStack(spacing: 16) {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .font(.system(size: 48))
                .foregroundStyle(DesignSystem.Colors.textMuted)

            Text("Select a file to edit")
                .font(.system(.headline, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DesignSystem.Colors.base)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("No file selected. Open the file explorer to choose a file.")
    }

    // MARK: - Tab Bar

    private var tabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(viewModel.openFiles) { file in
                    editorTab(for: file)
                }
            }
            .padding(.horizontal, 8)
        }
        .frame(minHeight: 40)
        .background(DesignSystem.Colors.surface)
    }

    private func editorTab(for file: FileNode) -> some View {
        let isActive = viewModel.selectedFile?.id == file.id
        return HStack(spacing: 6) {
            Image(systemName: file.iconName)
                .font(.system(size: 10))
                .foregroundStyle(file.iconColor)

            Text(file.name)
                .font(.system(.caption, design: .rounded).weight(.bold))
                .foregroundStyle(isActive ? DesignSystem.Colors.textPrimary : DesignSystem.Colors.textSecondary)
                .lineLimit(1)

            Button {
                viewModel.closeFile(id: file.id)
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 8, weight: .heavy))
                    .foregroundStyle(DesignSystem.Colors.textMuted)
                    .frame(width: 20, height: 20)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel("Close \(file.name)")
        }
        .padding(.leading, 10)
        .padding(.trailing, 4)
        .frame(minHeight: 32)
        .background(isActive ? DesignSystem.Colors.elevated : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay(alignment: .bottom) {
            if isActive {
                Rectangle()
                    .fill(DesignSystem.Colors.accent)
                    .frame(height: 2)
                    .padding(.horizontal, 6)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            viewModel.selectFile(file)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(file.name), tab\(isActive ? ", selected" : "")")
        .accessibilityAddTraits(isActive ? [.isSelected] : [])
    }

    // MARK: - Edit Bar

    private var editBar: some View {
        HStack {
            Button("Cancel") {
                viewModel.cancelEdits()
            }
            .foregroundStyle(DesignSystem.Colors.textSecondary)

            Spacer()

            Text("Editing")
                .font(.system(.caption, design: .rounded).weight(.medium))
                .foregroundStyle(DesignSystem.Colors.warning)

            Spacer()

            Button("Save") {
                viewModel.saveEdits()
            }
            .font(.system(.subheadline, design: .rounded).weight(.semibold))
            .foregroundStyle(DesignSystem.Colors.accent)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
        .overlay(alignment: .top) {
            Divider().overlay(DesignSystem.Colors.borderFaint)
        }
    }

    // MARK: - Helpers

    private func determineLanguage(filename: String) -> SyntaxEditorView.Language {
        if filename.hasSuffix(".swift") { return .swift }
        if filename.hasSuffix(".js") || filename.hasSuffix(".jsx") { return .javascript }
        if filename.hasSuffix(".ts") || filename.hasSuffix(".tsx") { return .typescript }
        if filename.hasSuffix(".html") || filename.hasSuffix(".htm") { return .html }
        if filename.hasSuffix(".css") { return .css }
        if filename.hasSuffix(".json") || filename.hasSuffix(".yml") || filename.hasSuffix(".yaml") { return .json }
        return .plaintext
    }
}

// MARK: - FileNode Extensions

extension FileNode {
    private var ext: String {
        (name as NSString).pathExtension.lowercased()
    }

    var iconName: String {
        guard type == .file else { return "folder.fill" }
        switch ext {
        case "swift":                return "swift"
        case "js", "jsx":            return "curlybraces"
        case "ts", "tsx":            return "curlybraces"
        case "json", "yaml", "yml":  return "gearshape.2.fill"
        case "md":                   return "doc.text.fill"
        case "html", "htm":          return "globe"
        case "css":                  return "paintbrush.pointed.fill"
        case "png", "jpg", "jpeg", "svg", "gif": return "photo.fill"
        case "sh":                   return "terminal.fill"
        default:                     return "doc.text"
        }
    }

    var iconColor: Color {
        guard type == .file else { return DesignSystem.Colors.warning }
        switch ext {
        case "swift":                return Color(.sRGB, red: 1, green: 0.42, blue: 0.21, opacity: 1)
        case "js", "jsx":            return DesignSystem.Colors.warning
        case "ts", "tsx":            return Color(.sRGB, red: 0, green: 0.48, blue: 0.8, opacity: 1)
        case "json", "yaml", "yml":  return DesignSystem.Colors.textSecondary
        case "html", "htm":          return Color(.sRGB, red: 0.89, green: 0.31, blue: 0.15, opacity: 1)
        case "css":                  return Color(.sRGB, red: 0.48, green: 0.41, blue: 0.93, opacity: 1)
        case "sh":                   return DesignSystem.Colors.success
        default:                     return DesignSystem.Colors.textSecondary
        }
    }
}

#Preview {
    CodeBrowserView()
}
