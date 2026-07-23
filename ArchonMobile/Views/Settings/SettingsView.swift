import SwiftUI

struct SettingsView: View {
    @StateObject private var viewModel = SettingsViewModel()
    @EnvironmentObject var authManager: AuthManager

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                Form {
                    // Account Section
                    Section {
                        accountRow
                    } header: {
                        Text("Account")
                    }

                    // Appearance Section
                    Section {
                        appearancePicker
                    } header: {
                        Text("Appearance")
                    }

                    // API Configuration
                    Section {
                        apiEndpointRow
                    } header: {
                        Text("API Configuration")
                    } footer: {
                        Text("Configure the backend API endpoint for production use.")
                            .font(.system(.caption2, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textMuted)
                    }

                    // About Section
                    Section {
                        aboutRow
                        licensesRow
                    } header: {
                        Text("About")
                    }

                    // Danger Zone
                    Section {
                        signOutButton
                        deleteAccountButton
                    } header: {
                        Text("Danger Zone")
                    }
                }
                .scrollContentBackground(.hidden)
                .navigationTitle("Settings")
            }
            .preferredColorScheme(.dark)
        }
    }

    // MARK: - Account

    private var accountRow: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.2))
                    .frame(width: 44, height: 44)

                Image(systemName: "person.fill")
                    .font(.title3)
                    .foregroundStyle(DesignSystem.Colors.accent)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(authManager.currentUser?.displayName ?? "User")
                    .font(.system(.headline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text(authManager.currentUser?.email ?? "Not signed in")
                    .font(.system(.caption, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
            }

            Spacer()
        }
        .listRowBackground(DesignSystem.Colors.elevated)
    }

    // MARK: - Appearance

    private var appearancePicker: some View {
        Picker("Theme", selection: Binding(
            get: { viewModel.appearance },
            set: { viewModel.saveAppearance($0) }
        )) {
            ForEach(SettingsViewModel.AppearanceMode.allCases, id: \.self) { mode in
                HStack {
                    Image(systemName: mode.icon)
                    Text(mode.displayName)
                }
                .tag(mode)
            }
        }
        .listRowBackground(DesignSystem.Colors.elevated)
    }

    // MARK: - API Endpoint

    private var apiEndpointRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("API Endpoint")
                .font(.system(.subheadline, design: .rounded).weight(.medium))
                .foregroundStyle(DesignSystem.Colors.textSecondary)

            TextField("https://api.example.com", text: Binding(
                get: { viewModel.apiEndpoint },
                set: { viewModel.saveAPIEndpoint($0) }
            ))
            .textFieldStyle(.plain)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(DesignSystem.Colors.textPrimary)
            .padding(10)
            .background(DesignSystem.Colors.surface)
            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
            .autocorrectionDisabled()
            .textInputAutocapitalization(.never)
        }
        .listRowBackground(DesignSystem.Colors.elevated)
    }

    // MARK: - About

    private var aboutRow: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Archon Mobile")
                    .font(.system(.body, design: .rounded).weight(.medium))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("Version \(viewModel.appVersion)")
                    .font(.system(.caption, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
            }

            Spacer()
        }
        .listRowBackground(DesignSystem.Colors.elevated)
    }

    private var licensesRow: some View {
        HStack {
            Text("Licenses")
                .font(.system(.body, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(DesignSystem.Colors.textMuted)
        }
        .listRowBackground(DesignSystem.Colors.elevated)
    }

    // MARK: - Danger Zone

    private var signOutButton: some View {
        Button {
            Task { await viewModel.signOut() }
        } label: {
            HStack {
                if viewModel.isSigningOut {
                    ProgressView()
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .foregroundStyle(DesignSystem.Colors.danger)
                }
                Text("Sign Out")
                    .foregroundStyle(DesignSystem.Colors.danger)
            }
        }
        .disabled(viewModel.isSigningOut)
        .listRowBackground(DesignSystem.Colors.elevated)
        .accessibilityLabel("Sign out of your account")
    }

    private var deleteAccountButton: some View {
        Button {
            viewModel.showDeleteAlert = true
        } label: {
            HStack {
                Image(systemName: "trash")
                    .foregroundStyle(DesignSystem.Colors.danger)
                Text("Delete Account")
                    .foregroundStyle(DesignSystem.Colors.danger)
            }
        }
        .alert("Delete Account", isPresented: $viewModel.showDeleteAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                Task { await authManager.deleteAccount() }
            }
        } message: {
            Text("This action cannot be undone. All your data will be permanently deleted.")
        }
        .listRowBackground(DesignSystem.Colors.elevated)
        .accessibilityLabel("Delete your account permanently")
    }
}

#Preview {
    SettingsView()
        .environmentObject(AuthManager.shared)
}
