import XCTest
@testable import ArchonMobile

@MainActor
final class CodeBrowserViewModelTests: XCTestCase {

    func testInitialFileTreeIsEmptyUntilProjectLoads() {
        let vm = CodeBrowserViewModel()
        XCTAssertTrue(vm.fileTree.isEmpty)
    }

    func testSelectFile() {
        let vm = CodeBrowserViewModel()
        let mockTree = FileNode.mock()
        let file = mockTree[0].children![0] // src/main.swift

        vm.selectFile(file)

        XCTAssertEqual(vm.selectedFile?.id, file.id)
        XCTAssertTrue(vm.openFiles.contains(where: { $0.id == file.id }))
        XCTAssertEqual(vm.editingContent, file.content)
    }

    func testSelectFolderDoesNothing() {
        let vm = CodeBrowserViewModel()
        let mockTree = FileNode.mock()
        let folder = mockTree[0] // src folder

        vm.selectFile(folder)

        XCTAssertNil(vm.selectedFile)
    }

    func testCloseFile() {
        let vm = CodeBrowserViewModel()
        let mockTree = FileNode.mock()
        let file1 = mockTree[0].children![0]
        let file2 = mockTree[0].children![1]

        vm.selectFile(file1)
        vm.selectFile(file2)
        XCTAssertEqual(vm.openFiles.count, 2)

        vm.closeFile(id: file1.id)
        XCTAssertEqual(vm.openFiles.count, 1)
        XCTAssertFalse(vm.openFiles.contains(where: { $0.id == file1.id }))
    }

    func testCloseSelectedFileSelectsLastOpen() {
        let vm = CodeBrowserViewModel()
        let mockTree = FileNode.mock()
        let file1 = mockTree[0].children![0]
        let file2 = mockTree[0].children![1]

        vm.selectFile(file1)
        vm.selectFile(file2)
        vm.closeFile(id: file2.id)

        XCTAssertEqual(vm.selectedFile?.id, file1.id)
    }

    func testStartAndCancelEditing() {
        let vm = CodeBrowserViewModel()
        let mockTree = FileNode.mock()
        let file = mockTree[0].children![0]

        vm.selectFile(file)
        XCTAssertFalse(vm.isEditing)

        vm.startEditing()
        XCTAssertTrue(vm.isEditing)
        XCTAssertEqual(vm.editingContent, file.content)

        vm.editingContent = "Modified content"
        vm.cancelEdits()
        XCTAssertFalse(vm.isEditing)
        XCTAssertEqual(vm.editingContent, file.content)
    }

    func testSaveEdits() async {
        let mockTree = FileNode.mock()
        let file = mockTree[0].children![0]
        let files = TestProjectFilesClient(file: file)
        let vm = CodeBrowserViewModel(filesClient: files)

        vm.selectFile(file)
        vm.startEditing()
        vm.editingContent = "Modified content"
        await vm.saveEdits()

        XCTAssertFalse(vm.isEditing)
        XCTAssertEqual(vm.selectedFile?.content, "Modified content")
    }

    func testTogglePreview() {
        let vm = CodeBrowserViewModel()
        XCTAssertFalse(vm.showPreview)

        vm.togglePreview()
        XCTAssertTrue(vm.showPreview)

        vm.togglePreview()
        XCTAssertFalse(vm.showPreview)
    }

    func testIsPreviewableFile() {
        let vm = CodeBrowserViewModel()

        let htmlFile = FileNode(name: "index.html", type: .file, content: "<html></html>")
        vm.selectedFile = htmlFile
        XCTAssertTrue(vm.isPreviewableFile)

        let swiftFile = FileNode(name: "App.swift", type: .file, content: "import SwiftUI")
        vm.selectedFile = swiftFile
        XCTAssertFalse(vm.isPreviewableFile)
    }

    func testSearchFiltering() {
        let vm = CodeBrowserViewModel()
        vm.fileTree = FileNode.mock()

        vm.searchQuery = "README"
        let results = vm.filteredTree
        // Should find README.md in the mock tree
        let found = results.contains { $0.name == "README.md" || ($0.children?.contains(where: { $0.name == "README.md" }) ?? false) }
        XCTAssertTrue(found, "Search should find README.md")

        vm.searchQuery = ""
    }
}

private final class TestProjectFilesClient: ProjectFilesClientProtocol {
    private let file: FileNode

    init(file: FileNode) {
        self.file = file
    }

    func fetchFiles(projectId: String) async throws -> [CloudProjectFile] { [] }
    func createStarterFiles(projectId: String) async throws -> [CloudProjectFile] { [] }

    func updateFile(id: UUID, content: String) async throws -> CloudProjectFile {
        CloudProjectFile(
            id: file.id,
            path: file.name,
            content: content,
            mimeType: "text/plain",
            updatedAt: Date()
        )
    }

    func upsertGeneratedFiles(_ files: [GeneratedProjectFile], projectId: String) async throws {}
}
