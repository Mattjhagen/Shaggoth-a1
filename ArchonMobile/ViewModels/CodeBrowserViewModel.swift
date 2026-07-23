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

    init() {
        self.fileTree = FileNode.load()
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

    func saveEdits() {
        guard let file = selectedFile else { return }
        updateFileContent(id: file.id, newContent: editingContent)
        isEditing = false
    }

    func cancelEdits() {
        isEditing = false
        editingContent = selectedFile?.content ?? ""
    }

    private func updateFileContent(id: UUID, newContent: String) {
        func update(nodes: inout [FileNode]) -> Bool {
            for i in 0..<nodes.count {
                if nodes[i].id == id {
                    nodes[i].content = newContent
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
            FileNode.save(fileTree)
        }

        if selectedFile?.id == id {
            selectedFile?.content = newContent
        }

        if let index = openFiles.firstIndex(where: { $0.id == id }) {
            openFiles[index].content = newContent
        }
    }

    func togglePreview() {
        showPreview.toggle()
    }

    var isPreviewableFile: Bool {
        guard let name = selectedFile?.name else { return false }
        return name.hasSuffix(".html") || name.hasSuffix(".htm")
    }
}
