import SwiftUI

struct TodoView: View {
    @StateObject private var viewModel = TodoViewModel()
    @EnvironmentObject var authManager: AuthManager
    let projectId: String
    let projectName: String

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                if viewModel.isLoading && viewModel.todos.isEmpty {
                    loadingView
                } else if viewModel.todos.isEmpty {
                    emptyStateView
                } else {
                    contentView
                }
            }
            .navigationTitle(projectName)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(role: .destructive) {
                            Task { await viewModel.clearCompleted() }
                        } label: {
                            Label("Clear Completed", systemImage: "trash")
                        }
                        .disabled(viewModel.completedCount == 0)
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                    }
                    .dsTouchTarget()
                }
            }
            .task {
                if let userId = authManager.user?.id {
                    await viewModel.loadTodos(projectId: projectId, userId: userId)
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Content

    private var contentView: some View {
        VStack(spacing: 0) {
            progressHeader
            Divider().background(DesignSystem.Colors.surfaceBorder)
            todoList
            Divider().background(DesignSystem.Colors.surfaceBorder)
            addTodoBar
        }
    }

    // MARK: - Progress Header

    private var progressHeader: some View {
        VStack(spacing: 8) {
            HStack {
                Text("\(viewModel.completedCount) of \(viewModel.todos.count) completed")
                    .font(.system(.caption, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)

                Spacer()

                Text("\(Int(viewModel.progress * 100))%")
                    .font(.system(.caption, design: .monospaced).weight(.medium))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(DesignSystem.Colors.surface)
                        .frame(height: 6)

                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [DesignSystem.Colors.accent, DesignSystem.Colors.accentDeep],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * viewModel.progress, height: 6)
                        .animation(.easeInOut(duration: 0.3), value: viewModel.progress)
                }
            }
            .frame(height: 6)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Todo List

    private var todoList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(viewModel.todos) { todo in
                    TodoRowView(todo: todo) {
                        Task { await viewModel.toggleTodo(todo) }
                    } onDelete: {
                        Task { await viewModel.deleteTodo(todo) }
                    } onEdit: { newTitle in
                        Task { await viewModel.updateTodoTitle(todo, newTitle: newTitle) }
                    }

                    if todo.id != viewModel.todos.last?.id {
                        Divider()
                            .background(DesignSystem.Colors.surfaceBorder)
                            .padding(.leading, 52)
                    }
                }
            }
        }
    }

    // MARK: - Add Todo Bar

    private var addTodoBar: some View {
        HStack(alignment: .bottom, spacing: 12) {
            TextField("Add a task...", text: $viewModel.newTodoTitle)
                .textFieldStyle(.plain)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(DesignSystem.Colors.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .onSubmit {
                    Task { await viewModel.addTodo() }
                }

            Button {
                Task { await viewModel.addTodo() }
            } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 32))
                    .foregroundStyle(
                        viewModel.newTodoTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        ? DesignSystem.Colors.textMuted
                        : DesignSystem.Colors.accent
                    )
            }
            .disabled(viewModel.newTodoTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .dsTouchTarget()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(DesignSystem.Colors.surface)
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Spacer()

            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "checklist")
                    .font(.system(size: 32))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }

            VStack(spacing: 8) {
                Text("No Tasks Yet")
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("Add your first task to get started")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
            }

            Spacer()
        }
        .padding()
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)
            Text("Loading tasks...")
                .font(.system(.subheadline, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        }
    }
}

// MARK: - Todo Row

struct TodoRowView: View {
    let todo: TodoItem
    let onToggle: () -> Void
    let onDelete: () -> Void
    let onEdit: (String) -> Void

    @State private var isEditing = false
    @State private var editTitle = ""

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onToggle) {
                Image(systemName: todo.isCompleted ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundStyle(
                        todo.isCompleted ? DesignSystem.Colors.success : DesignSystem.Colors.textMuted
                    )
            }
            .dsTouchTarget()

            if isEditing {
                TextField("Task title", text: $editTitle)
                    .textFieldStyle(.plain)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .onSubmit {
                        onEdit(editTitle)
                        isEditing = false
                    }
            } else {
                Text(todo.title)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(
                        todo.isCompleted ? DesignSystem.Colors.textMuted : DesignSystem.Colors.textPrimary
                    )
                    .strikethrough(todo.isCompleted, color: DesignSystem.Colors.textMuted)
            }

            Spacer()

            if !isEditing {
                Button {
                    editTitle = todo.title
                    isEditing = true
                } label: {
                    Image(systemName: "pencil")
                        .font(.system(size: 12))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }
                .dsTouchTarget()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(DesignSystem.Colors.base)
        .contextMenu {
            Button {
                editTitle = todo.title
                isEditing = true
            } label: {
                Label("Edit", systemImage: "pencil")
            }

            Button(role: .destructive) {
                onDelete()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }
}

#Preview {
    TodoView(projectId: "preview", projectName: "My Todo App")
        .environmentObject(AuthManager.shared)
}
