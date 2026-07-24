import Foundation
import Combine

@MainActor
final class CodeBrowserViewModel: ObservableObject {
    @Published var fileTree: [FileNode] = []
    @Published var selectedFile: FileNode?
    @Published var openFiles: [FileNode] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isEditing = false
    @Published var editingContent = ""
    @Published var showSaveConfirmation = false
    @Published var searchQuery = ""
    @Published var showPreview = false

    private let filesClient: ProjectFilesClientProtocol
    private var projectId: String?

    init(filesClient: ProjectFilesClientProtocol = SupabaseProjectFilesClient()) {
        self.filesClient = filesClient
    }

    func loadProject(_ project: ArchonProject) async {
        projectId = project.id
        isLoading = true
        errorMessage = nil
        selectedFile = nil
        openFiles = []
        defer { isLoading = false }

        do {
            var files = try await filesClient.fetchFiles(projectId: project.id)
            if files.isEmpty {
                files = try await filesClient.createStarterFiles(projectId: project.id)
            }
            fileTree = files.map(Self.fileNode)
            if let first = fileTree.first {
                selectFile(first)
            }
        } catch {
            fileTree = []
            errorMessage = "Could not load project files: \(error.localizedDescription)"
        }
    }

    func clearProject() {
        projectId = nil
        fileTree = []
        selectedFile = nil
        openFiles = []
        errorMessage = nil
    }

    var filteredTree: [FileNode] {
        guard !searchQuery.isEmpty else { return fileTree }
        return fileTree.filter { matchesSearch($0, query: searchQuery) }
    }

    private func matchesSearch(_ node: FileNode, query: String) -> Bool {
        if node.name.localizedCaseInsensitiveContains(query) {
            return true
        }
        if let children = node.children {
            return children.contains { matchesSearch($0, query: query) }
        }
        return false
    }

    func selectFile(_ file: FileNode) {
        guard file.type == .file else { return }

        if !openFiles.contains(where: { $0.id == file.id }) {
            openFiles.append(file)
        }
        selectedFile = file
        editingContent = file.content ?? ""
        isEditing = false
    }

    func closeFile(id: UUID) {
        openFiles.removeAll { $0.id == id }
        if selectedFile?.id == id {
            selectedFile = openFiles.last
            editingContent = selectedFile?.content ?? ""
        }
    }

    func startEditing() {
        guard let file = selectedFile else { return }
        editingContent = file.content ?? ""
        isEditing = true
    }

    func saveEdits() async {
        guard let file = selectedFile else { return }
        let newContent = editingContent
        do {
            let updated = try await filesClient.updateFile(id: file.id, content: newContent)
            updateFileContent(id: updated.id, newContent: updated.content, updatedAt: updated.updatedAt)
            isEditing = false
            errorMessage = nil
        } catch {
            errorMessage = "Could not save file: \(error.localizedDescription)"
        }
    }

    func cancelEdits() {
        isEditing = false
        editingContent = selectedFile?.content ?? ""
    }

    private func updateFileContent(id: UUID, newContent: String, updatedAt: Date) {
        func update(nodes: inout [FileNode]) -> Bool {
            for i in 0..<nodes.count {
                if nodes[i].id == id {
                    nodes[i].content = newContent
                    nodes[i].updatedAt = updatedAt
                    return true
                }
                if nodes[i].children != nil {
                    var children = nodes[i].children!
                    if update(nodes: &children) {
                        nodes[i].children = children
                        return true
                    }
                }
            }
            return false
        }

        var newTree = fileTree
        if update(nodes: &newTree) {
            fileTree = newTree
        }

        if selectedFile?.id == id {
            selectedFile?.content = newContent
            selectedFile?.updatedAt = updatedAt
        }

        if let index = openFiles.firstIndex(where: { $0.id == id }) {
            openFiles[index].content = newContent
            openFiles[index].updatedAt = updatedAt
        }
    }

    private static func fileNode(_ file: CloudProjectFile) -> FileNode {
        FileNode(
            id: file.id,
            name: file.path,
            type: .file,
            content: file.content,
            size: Int64(file.content.utf8.count),
            updatedAt: file.updatedAt
        )
    }

    func togglePreview() {
        showPreview.toggle()
    }

    var isPreviewableFile: Bool {
        guard let name = selectedFile?.name else { return false }
        return name.hasSuffix(".html") || name.hasSuffix(".htm")
    }

    var previewHTML: String {
        guard var html = selectedFile?.content else { return "" }

        if let css = fileTree.first(where: { $0.name == "style.css" })?.content {
            let style = "<style>\n\(css)\n</style>"
            if html.range(of: "</head>", options: .caseInsensitive) != nil {
                html = html.replacingOccurrences(
                    of: "</head>",
                    with: "\(style)\n</head>",
                    options: .caseInsensitive
                )
            } else {
                html = "\(style)\n\(html)"
            }
        }

        if let javascript = fileTree.first(where: { $0.name == "app.js" })?.content {
            let script = "<script>\n\(javascript)\n</script>"
            if html.range(of: "</body>", options: .caseInsensitive) != nil {
                html = html.replacingOccurrences(
                    of: "</body>",
                    with: "\(script)\n</body>",
                    options: .caseInsensitive
                )
            } else {
                html += "\n\(script)"
            }
        }

        return html
    }
}
