import Foundation
import Combine

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var projects: [ArchonProject] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var showCreateSheet = false
    @Published var newProjectName = ""
    @Published var newProjectDescription = ""
    @Published var isCreating = false
    @Published var searchText = ""
    @Published var selectedProject: ArchonProject?

    private let apiClient: APIClientProtocol

    init(apiClient: APIClientProtocol = MockAPIClient()) {
        self.apiClient = apiClient
    }

    var filteredProjects: [ArchonProject] {
        if searchText.isEmpty {
            return projects
        }
        return projects.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            ($0.description?.localizedCaseInsensitiveContains(searchText) ?? false)
        }
    }

    var activeProjects: [ArchonProject] {
        filteredProjects.filter { $0.status == .active }
    }

    var draftProjects: [ArchonProject] {
        filteredProjects.filter { $0.status == .draft }
    }

    var archivedProjects: [ArchonProject] {
        filteredProjects.filter { $0.status == .archived }
    }

    func loadProjects() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            projects = try await apiClient.fetchProjects()
        } catch {
            errorMessage = "Failed to load projects: \(error.localizedDescription)"
        }
    }

    func createProject() async {
        let name = newProjectName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }

        isCreating = true
        defer { isCreating = false }

        do {
            let project = try await apiClient.createProject(
                CreateProjectRequest(name: name, description: newProjectDescription.isEmpty ? nil : newProjectDescription)
            )
            projects.insert(project, at: 0)
            newProjectName = ""
            newProjectDescription = ""
            showCreateSheet = false
        } catch {
            errorMessage = "Failed to create project: \(error.localizedDescription)"
        }
    }

    func deleteProject(_ project: ArchonProject) async {
        do {
            try await apiClient.deleteProject(id: project.id)
            projects.removeAll { $0.id == project.id }
        } catch {
            errorMessage = "Failed to delete project: \(error.localizedDescription)"
        }
    }
}
