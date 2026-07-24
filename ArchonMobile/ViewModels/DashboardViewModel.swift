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

    private let apiClient: ProjectsClientProtocol
    private var activeLoadID: UUID?

    init(apiClient: ProjectsClientProtocol = SupabaseProjectsClient()) {
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
        let loadID = UUID()
        activeLoadID = loadID
        isLoading = true
        errorMessage = nil
        defer {
            if activeLoadID == loadID {
                isLoading = false
                activeLoadID = nil
            }
        }

        do {
            let loadedProjects = try await apiClient.fetchProjects()
            guard activeLoadID == loadID else { return }
            projects = loadedProjects
        } catch is CancellationError {
            // SwiftUI routinely cancels an older task when a newer refresh starts.
        } catch {
            guard activeLoadID == loadID else { return }
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

    @discardableResult
    func deleteProject(_ project: ArchonProject) async -> Bool {
        do {
            try await apiClient.deleteProject(id: project.id)
            projects.removeAll { $0.id == project.id }
            if selectedProject?.id == project.id {
                selectedProject = nil
            }
            return true
        } catch {
            errorMessage = "Failed to delete project: \(error.localizedDescription)"
            return false
        }
    }
}
