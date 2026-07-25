import XCTest
@testable import ArchonMobile

@MainActor
final class TodoViewModelTests: XCTestCase {
    
    func testLoadTodos() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        let date = Date()
        
        mockClient.todos = [
            TodoItem(id: UUID(), title: "Task 1", isCompleted: false, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date),
            TodoItem(id: UUID(), title: "Task 2", isCompleted: true, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date),
            TodoItem(id: UUID(), title: "Task 3", isCompleted: false, projectId: "p2", userId: "u1", createdAt: date, updatedAt: date)
        ]
        
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        XCTAssertEqual(vm.todos.count, 2)
        XCTAssertEqual(vm.completedCount, 1)
        XCTAssertEqual(vm.pendingCount, 1)
        XCTAssertEqual(vm.progress, 0.5)
    }

    func testAddTodo() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        vm.newTodoTitle = "New Task"
        await vm.addTodo()
        
        XCTAssertEqual(vm.todos.count, 1)
        XCTAssertEqual(vm.todos.first?.title, "New Task")
        XCTAssertEqual(vm.newTodoTitle, "")
    }

    func testAddTodoEmptyTitle() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        vm.newTodoTitle = "   "
        await vm.addTodo()
        
        XCTAssertEqual(vm.todos.count, 0)
    }

    func testToggleTodo() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        let date = Date()
        let todoId = UUID()
        let todo = TodoItem(id: todoId, title: "Task", isCompleted: false, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date)
        mockClient.todos = [todo]
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        await vm.toggleTodo(vm.todos[0])
        
        XCTAssertEqual(vm.todos[0].isCompleted, true)
        XCTAssertEqual(mockClient.todos[0].isCompleted, true)
    }

    func testDeleteTodo() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        let date = Date()
        let todo = TodoItem(id: UUID(), title: "Task", isCompleted: false, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date)
        mockClient.todos = [todo]
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        await vm.deleteTodo(vm.todos[0])
        
        XCTAssertEqual(vm.todos.count, 0)
        XCTAssertEqual(mockClient.todos.count, 0)
    }

    func testClearCompleted() async {
        let mockClient = MockTodoClient()
        let vm = TodoViewModel(todoClient: mockClient)
        let date = Date()
        mockClient.todos = [
            TodoItem(id: UUID(), title: "Task 1", isCompleted: true, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date),
            TodoItem(id: UUID(), title: "Task 2", isCompleted: false, projectId: "p1", userId: "u1", createdAt: date, updatedAt: date)
        ]
        await vm.loadTodos(projectId: "p1", userId: "u1")
        
        await vm.clearCompleted()
        
        XCTAssertEqual(vm.todos.count, 1)
        XCTAssertEqual(vm.todos[0].title, "Task 2")
        XCTAssertEqual(mockClient.todos.count, 1)
    }
}
