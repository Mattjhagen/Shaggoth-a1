import XCTest
@testable import ArchonMobile

@MainActor
final class DashboardViewModelTests: XCTestCase {

    func testLoadProjects() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "Project 1", description: nil, status: .active, createdAt: Date(), updatedAt: Date()),
            ArchonProject(id: "p2", name: "Project 2", description: nil, status: .active, createdAt: Date(), updatedAt: Date())
        ]
        let vm = DashboardViewModel(apiClient: spy)
        
        await vm.loadProjects()
        
        XCTAssertEqual(vm.projects.count, 2)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.errorMessage)
    }

    func testCreateProject() async {
        let spy = SpyAPIClient()
        let vm = DashboardViewModel(apiClient: spy)
        
        vm.newProjectName = "New Project"
        vm.newProjectDescription = "Test"
        await vm.createProject()
        
        XCTAssertEqual(vm.projects.count, 1)
        XCTAssertEqual(vm.projects.first?.name, "New Project")
    }

    func testEmptyMessageNotCreated() async {
        let spy = SpyAPIClient()
        let vm = DashboardViewModel(apiClient: spy)
        
        vm.newProjectName = "   "
        vm.newProjectDescription = ""
        await vm.createProject()
        XCTAssertTrue(vm.projects.isEmpty)
    }

    func testFilterProjects() async {
        let spy = SpyAPIClient()
        spy.projects = [
            ArchonProject(id: "p1", name: "Alpha", description: nil, status: .active, createdAt: Date(), updatedAt: Date()),
            ArchonProject(id: "p2", name: "Beta", description: nil, status: .active, createdAt: Date(), updatedAt: Date())
        ]
        let vm = DashboardViewModel(apiClient: spy)
        await vm.loadProjects()
        
        vm.searchText = "lph"
        XCTAssertEqual(vm.filteredProjects.count, 1)
        XCTAssertEqual(vm.filteredProjects.first?.name, "Alpha")
    }

    func testDeleteProject() async {
        let p1 = ArchonProject(id: "p1", name: "Alpha", description: nil, status: .active, createdAt: Date(), updatedAt: Date())
        let spy = SpyAPIClient()
        spy.projects = [p1]
        let vm = DashboardViewModel(apiClient: spy)
        await vm.loadProjects()
        XCTAssertEqual(vm.projects.count, 1)
        
        await vm.deleteProject(p1)
        XCTAssertTrue(vm.projects.isEmpty)
    }
}
