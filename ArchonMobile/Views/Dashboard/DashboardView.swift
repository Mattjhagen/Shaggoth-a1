import SwiftUI

struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    @EnvironmentObject var authManager: AuthManager
    @State private var showSettings = false
    private let onProjectSelected: (ArchonProject) -> Void
    private let onProjectDeleted: (ArchonProject) -> Void

    init(
        onProjectSelected: @escaping (ArchonProject) -> Void = { _ in },
        onProjectDeleted: @escaping (ArchonProject) -> Void = { _ in }
    ) {
        self.onProjectSelected = onProjectSelected
        self.onProjectDeleted = onProjectDeleted
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                if viewModel.isLoading && viewModel.projects.isEmpty {
                    loadingView
                } else if viewModel.projects.isEmpty && viewModel.errorMessage == nil {
                    emptyStateView
                } else {
                    contentView
                }
            }
            .navigationTitle("Projects")
            .searchable(text: $viewModel.searchText, prompt: "Search projects")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        viewModel.showCreateSheet = true
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .foregroundStyle(DesignSystem.Colors.accent)
                    }
                    .accessibilityLabel("Create new project")
                    .dsTouchTarget()
                }
            }
            .refreshable {
                await viewModel.loadProjects()
            }
            .task {
                await viewModel.loadProjects()
            }
            .sheet(isPresented: $viewModel.showCreateSheet) {
                createProjectSheet
            }
            .alert("Error", isPresented: .constant(viewModel.errorMessage != nil)) {
                Button("OK") { viewModel.errorMessage = nil }
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
        }
    }

    // MARK: - Content

    private var contentView: some View {
        ScrollView {
            LazyVStack(spacing: DesignSystem.Spacing.md) {
                if !viewModel.activeProjects.isEmpty {
                    sectionHeader(title: "Active", count: viewModel.activeProjects.count)
                    ForEach(viewModel.activeProjects) { project in
                        ProjectCardView(project: project) {
                            viewModel.selectedProject = project
                            onProjectSelected(project)
                        } onDelete: {
                            delete(project)
                        }
                    }
                }

                if !viewModel.draftProjects.isEmpty {
                    sectionHeader(title: "Drafts", count: viewModel.draftProjects.count)
                    ForEach(viewModel.draftProjects) { project in
                        ProjectCardView(project: project) {
                            viewModel.selectedProject = project
                            onProjectSelected(project)
                        } onDelete: {
                            delete(project)
                        }
                    }
                }

                if !viewModel.archivedProjects.isEmpty {
                    sectionHeader(title: "Archived", count: viewModel.archivedProjects.count)
                    ForEach(viewModel.archivedProjects) { project in
                        ProjectCardView(project: project) {
                            viewModel.selectedProject = project
                            onProjectSelected(project)
                        } onDelete: {
                            delete(project)
                        }
                    }
                }
            }
            .padding(.horizontal, DesignSystem.Spacing.lg)
            .padding(.top, DesignSystem.Spacing.sm)
        }
    }

    private func delete(_ project: ArchonProject) {
        Task {
            if await viewModel.deleteProject(project) {
                onProjectDeleted(project)
            }
        }
    }

    // MARK: - Section Header

    private func sectionHeader(title: String, count: Int) -> some View {
        HStack {
            Text(title)
                .font(.system(.headline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)
                .accessibilityAddTraits(.isHeader)

            Text("\(count)")
                .font(.system(.caption, design: .rounded).weight(.medium))
                .foregroundStyle(DesignSystem.Colors.textMuted)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(DesignSystem.Colors.elevated)
                .clipShape(Capsule())

            Spacer()
        }
        .padding(.top, DesignSystem.Spacing.sm)
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Spacer()

            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.1))
                    .frame(width: 100, height: 100)

                Image(systemName: "folder.badge.plus")
                    .font(.system(size: 40))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }
            .accessibilityHidden(true)

            VStack(spacing: 8) {
                Text("No Projects Yet")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .accessibilityAddTraits(.isHeader)

                Text("Create your first project to start building with AI")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button {
                viewModel.showCreateSheet = true
            } label: {
                Label("Create Project", systemImage: "plus")
                    .font(.headline)
                    .foregroundStyle(DesignSystem.Colors.base)
                    .frame(maxWidth: .infinity, minHeight: 50)
            }
            .buttonStyle(.borderedProminent)
            .tint(DesignSystem.Colors.accent)
            .padding(.horizontal, 48)
            .dsTouchTarget()

            Spacer()
        }
        .padding()
        .accessibilityElement(children: .combine)
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)
            Text("Loading projects...")
                .font(.system(.subheadline, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Loading projects")
    }

    // MARK: - Create Sheet

    private var createProjectSheet: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                VStack(spacing: 20) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Project Name")
                            .font(.system(.subheadline, design: .rounded).weight(.medium))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)

                        TextField("My Awesome App", text: $viewModel.newProjectName)
                            .textFieldStyle(.plain)
                            .padding(14)
                            .background(DesignSystem.Colors.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                    }
                    .padding(.horizontal, 20)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Description (optional)")
                            .font(.system(.subheadline, design: .rounded).weight(.medium))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)

                        TextField("What are you building?", text: $viewModel.newProjectDescription, axis: .vertical)
                            .textFieldStyle(.plain)
                            .lineLimit(3...6)
                            .padding(14)
                            .background(DesignSystem.Colors.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                    }
                    .padding(.horizontal, 20)

                    Spacer()
                }
                .padding(.top, 20)
            }
            .navigationTitle("New Project")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        viewModel.showCreateSheet = false
                    }
                    .dsTouchTarget()
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await viewModel.createProject() }
                    } label: {
                        if viewModel.isCreating {
                            ProgressView()
                        } else {
                            Text("Create")
                                .fontWeight(.semibold)
                        }
                    }
                    .disabled(viewModel.newProjectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isCreating)
                    .dsTouchTarget()
                }
            }
        }
    }
}

// MARK: - Project Card

struct ProjectCardView: View {
    let project: ArchonProject
    let onTap: () -> Void
    let onDelete: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(project.name)
                            .font(.system(.headline, design: .rounded).weight(.semibold))
                            .foregroundStyle(DesignSystem.Colors.textPrimary)
                            .lineLimit(1)

                        if let desc = project.description {
                            Text(desc)
                                .font(.system(.subheadline, design: .rounded))
                                .foregroundStyle(DesignSystem.Colors.textSecondary)
                                .lineLimit(2)
                        }
                    }

                    Spacer()

                    statusBadge
                }

                HStack(spacing: 16) {
                    Label(project.updatedAt.formatted(.relative(presentation: .named)), systemImage: "clock")
                        .font(.system(.caption2, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textMuted)

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }
            }
            .padding(DesignSystem.Spacing.lg)
            .background(DesignSystem.Colors.elevated)
            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md, interactive: true)
            .overlay(
                RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous)
                    .stroke(DesignSystem.Colors.surfaceBorder.opacity(0.5), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .dsTouchTarget()
        .contextMenu {
            Button(role: .destructive) {
                onDelete()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(project.name). \(project.status.rawValue). Last updated \(project.updatedAt.formatted(.relative(presentation: .named))) ago.")
        .accessibilityHint("Double tap to open project")
    }

    private var statusBadge: some View {
        Text(project.status.rawValue.capitalized)
            .font(.system(.caption2, design: .rounded).weight(.semibold))
            .foregroundStyle(statusColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor.opacity(0.15))
            .clipShape(Capsule())
    }

    private var statusColor: Color {
        switch project.status {
        case .active: return DesignSystem.Colors.success
        case .draft: return DesignSystem.Colors.warning
        case .archived: return DesignSystem.Colors.textMuted
        }
    }
}

#Preview {
    DashboardView()
        .environmentObject(AuthManager.shared)
}
