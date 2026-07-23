import XCTest
@testable import ArchonMobile

final class ModelTests: XCTestCase {

    // MARK: - TaskStatus

    func testTaskStatusIsActive() {
        XCTAssertTrue(TaskStatus.queued.isActive)
        XCTAssertTrue(TaskStatus.planning.isActive)
        XCTAssertTrue(TaskStatus.running.isActive)
        XCTAssertTrue(TaskStatus.verifying.isActive)
        XCTAssertTrue(TaskStatus.cancelling.isActive)

        XCTAssertFalse(TaskStatus.completed.isActive)
        XCTAssertFalse(TaskStatus.blocked.isActive)
        XCTAssertFalse(TaskStatus.failed.isActive)
        XCTAssertFalse(TaskStatus.cancelled.isActive)
    }

    func testTaskStatusDisplayIcons() {
        XCTAssertEqual(TaskStatus.queued.displayIcon, "clock")
        XCTAssertEqual(TaskStatus.completed.displayIcon, "checkmark.circle.fill")
        XCTAssertEqual(TaskStatus.failed.displayIcon, "xmark.circle.fill")
    }

    func testTaskStatusAllCases() {
        XCTAssertEqual(TaskStatus.allCases.count, 9)
    }

    // MARK: - ReasoningEffort

    func testReasoningEffortDisplayNames() {
        XCTAssertEqual(ReasoningEffort.low.displayName, "Low")
        XCTAssertEqual(ReasoningEffort.medium.displayName, "Medium")
        XCTAssertEqual(ReasoningEffort.high.displayName, "High")
    }

    func testReasoningEffortAllCases() {
        XCTAssertEqual(ReasoningEffort.allCases.count, 3)
    }

    // MARK: - TaskEvent.EventType

    func testEventTypeDisplayCategories() {
        XCTAssertEqual(TaskEvent.EventType.planning.displayCategory, "Planning")
        XCTAssertEqual(TaskEvent.EventType.modelCall.displayCategory, "Thinking")
        XCTAssertEqual(TaskEvent.EventType.toolCall.displayCategory, "Using Tool")
        XCTAssertEqual(TaskEvent.EventType.completion.displayCategory, "Finished")
        XCTAssertEqual(TaskEvent.EventType.error.displayCategory, "Error")
        XCTAssertEqual(TaskEvent.EventType.fileEdit.displayCategory, "Editing File")
        XCTAssertEqual(TaskEvent.EventType.message.displayCategory, "Message")
    }

    func testEventTypeIcons() {
        XCTAssertEqual(TaskEvent.EventType.planning.icon, "brain.head.profile")
        XCTAssertEqual(TaskEvent.EventType.completion.icon, "checkmark.circle.fill")
        XCTAssertEqual(TaskEvent.EventType.error.icon, "xmark.octagon")
    }

    // MARK: - FileNode

    func testFileNodeInit() {
        let node = FileNode(name: "test.swift", type: .file, content: "code")
        XCTAssertEqual(node.name, "test.swift")
        XCTAssertEqual(node.type, .file)
        XCTAssertEqual(node.content, "code")
        XCTAssertNil(node.children)
    }

    func testFileNodeExpandable() {
        let folder = FileNode(name: "src", type: .folder, children: [])
        let file = FileNode(name: "App.swift", type: .file)

        XCTAssertTrue(folder.isExpandable)
        XCTAssertFalse(file.isExpandable)
        XCTAssertTrue(file.isLeaf)
        XCTAssertFalse(folder.isLeaf)
    }

    func testFileNodeIconName() {
        let swiftFile = FileNode(name: "App.swift", type: .file)
        XCTAssertEqual(swiftFile.iconName, "swift")

        let jsFile = FileNode(name: "app.js", type: .file)
        XCTAssertEqual(jsFile.iconName, "curlybraces")

        let htmlFile = FileNode(name: "index.html", type: .file)
        XCTAssertEqual(htmlFile.iconName, "globe")

        let folder = FileNode(name: "src", type: .folder)
        XCTAssertEqual(folder.iconName, "folder.fill")
    }

    func testFileNodeMockData() {
        let mock = FileNode.mock()
        XCTAssertFalse(mock.isEmpty)
        // Should have nested files
        let srcFolder = mock.first { $0.name == "src" }
        XCTAssertNotNil(srcFolder)
        XCTAssertNotNil(srcFolder?.children)
        XCTAssertFalse(srcFolder?.children?.isEmpty ?? true)
    }

    func testFileNodeSaveAndLoad() {
        let nodes = FileNode.mock()
        FileNode.save(nodes)
        let loaded = FileNode.load()
        XCTAssertEqual(loaded.count, nodes.count)
    }

    // MARK: - ArchonProject

    func testArchonProjectStatusAllCases() {
        XCTAssertEqual(ArchonProject.ProjectStatus.allCases.count, 3)
    }

    // MARK: - ChatMessage

    func testChatMessageInit() {
        let msg = ChatMessage(role: .user, content: "Hello")
        XCTAssertEqual(msg.role, .user)
        XCTAssertEqual(msg.content, "Hello")
        XCTAssertNotNil(msg.id)
    }

    func testChatMessageEquality() {
        let id = UUID()
        let msg1 = ChatMessage(id: id, role: .user, content: "Hello")
        let msg2 = ChatMessage(id: id, role: .user, content: "Different content")
        XCTAssertEqual(msg1, msg2, "Messages with same ID should be equal")
    }

    // MARK: - AnyCodable

    func testAnyCodableInt() throws {
        let value = AnyCodable(42)
        XCTAssertEqual(value.value as? Int, 42)
    }

    func testAnyCodableString() throws {
        let value = AnyCodable("hello")
        XCTAssertEqual(value.value as? String, "hello")
    }

    func testAnyCodableBool() throws {
        let value = AnyCodable(true)
        XCTAssertEqual(value.value as? Bool, true)
    }

    func testAnyCodableDouble() throws {
        let value = AnyCodable(3.14)
        XCTAssertEqual(value.value as? Double, 3.14)
    }

    func testAnyCodableRoundTrip() throws {
        let original = AnyCodable(["key": AnyCodable("value"), "num": AnyCodable(42)])
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AnyCodable.self, from: data)
        let dict = decoded.value as? [String: Any]
        XCTAssertEqual(dict?["key"] as? String, "value")
        XCTAssertEqual(dict?["num"] as? Int, 42)
    }
}
