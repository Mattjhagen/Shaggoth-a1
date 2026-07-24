import SwiftUI
import PhotosUI
import UIKit

struct SettingsView: View {
    @StateObject private var viewModel = SettingsViewModel()
    @EnvironmentObject var authManager: AuthManager
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var profileImageData: Data?
    @State private var profilePhotoError: String?
    @AppStorage("keepScreenAwake") private var keepScreenAwake = false

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                Form {
                    // Account Section
                    Section {
                        accountRow
                        if profileImageData != nil {
                            Button("Remove Profile Photo", role: .destructive) {
                                removeProfilePhoto()
                            }
                        }
                    } header: {
                        Text("Account")
                    }

                    // Appearance Section
                    Section {
                        appearancePicker
                        Toggle(isOn: $keepScreenAwake) {
                            Label("Keep Screen Awake", systemImage: "sun.max")
                                .foregroundStyle(DesignSystem.Colors.textPrimary)
                        }
                        .tint(DesignSystem.Colors.accent)
                        .listRowBackground(DesignSystem.Colors.elevated)
                    } header: {
                        Text("Appearance")
                    } footer: {
                        Text("Prevents the iPhone display from turning off while Archon is open. This can use more battery.")
                            .font(.system(.caption2, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textMuted)
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

                    Section {
                        NavigationLink {
                            CreditsAndBillingView()
                        } label: {
                            HStack {
                                Label("Credits & Billing", systemImage: "creditcard.fill")
                                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                                Spacer()
                                Text("Coming Soon")
                                    .font(.system(.caption2, design: .rounded).weight(.semibold))
                                    .foregroundStyle(DesignSystem.Colors.accent)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(DesignSystem.Colors.accent.opacity(0.12))
                                    .clipShape(Capsule())
                            }
                        }
                        .listRowBackground(DesignSystem.Colors.elevated)
                    } header: {
                        Text("Credits")
                    } footer: {
                        Text("In-app credit purchases will be added through Apple’s secure purchase system.")
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

                    // Account management
                    Section {
                        NavigationLink {
                            AccountManagementView(viewModel: viewModel)
                        } label: {
                            Label("Account & Privacy", systemImage: "person.crop.circle.badge.checkmark")
                                .foregroundStyle(DesignSystem.Colors.textPrimary)
                        }
                        .listRowBackground(DesignSystem.Colors.elevated)
                    } header: {
                        Text("Account Management")
                    }
                }
                .scrollContentBackground(.hidden)
                .navigationTitle("Settings")
            }
            .task {
                profileImageData = ProfilePhotoStore.load()
            }
            .onChange(of: selectedPhoto) { _, newPhoto in
                guard let newPhoto else { return }
                Task { await saveSelectedPhoto(newPhoto) }
            }
            .alert("Profile Photo", isPresented: Binding(
                get: { profilePhotoError != nil },
                set: { if !$0 { profilePhotoError = nil } }
            )) {
                Button("OK") { profilePhotoError = nil }
            } message: {
                Text(profilePhotoError ?? "")
            }
        }
    }

    // MARK: - Account

    private var accountRow: some View {
        HStack(spacing: 14) {
            PhotosPicker(selection: $selectedPhoto, matching: .images) {
                ZStack(alignment: .bottomTrailing) {
                    Group {
                        if let profileImageData,
                           let image = UIImage(data: profileImageData) {
                            Image(uiImage: image)
                                .resizable()
                                .scaledToFill()
                        } else {
                            ZStack {
                                Circle()
                                    .fill(DesignSystem.Colors.accent.opacity(0.2))
                                Image(systemName: "person.fill")
                                    .font(.title3)
                                    .foregroundStyle(DesignSystem.Colors.accent)
                            }
                        }
                    }
                    .frame(width: 54, height: 54)
                    .clipShape(Circle())
                    .overlay {
                        Circle()
                            .stroke(DesignSystem.Colors.surfaceBorder, lineWidth: 1)
                    }

                    Image(systemName: "camera.fill")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(5)
                        .background(DesignSystem.Colors.accent)
                        .clipShape(Circle())
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel(profileImageData == nil ? "Add profile photo" : "Change profile photo")

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

    private func saveSelectedPhoto(_ item: PhotosPickerItem) async {
        do {
            guard let sourceData = try await item.loadTransferable(type: Data.self),
                  let sourceImage = UIImage(data: sourceData),
                  let preparedData = sourceImage.profilePhotoData else {
                throw ProfilePhotoError.invalidImage
            }
            try ProfilePhotoStore.save(preparedData)
            profileImageData = preparedData
        } catch {
            profilePhotoError = "The selected photo could not be saved. Please choose another image."
        }
        selectedPhoto = nil
    }

    private func removeProfilePhoto() {
        do {
            try ProfilePhotoStore.remove()
            profileImageData = nil
        } catch {
            profilePhotoError = "The profile photo could not be removed."
        }
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
            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.sm, interactive: true)
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
        NavigationLink {
            LicensesView()
        } label: {
            Text("Licenses")
                .font(.system(.body, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textPrimary)
        }
        .listRowBackground(DesignSystem.Colors.elevated)
        .accessibilityHint("Shows open-source acknowledgements")
    }

}

private struct CreditsAndBillingView: View {
    private let futurePacks = [
        ("Starter", "50 credits"),
        ("Builder", "250 credits"),
        ("Studio", "1,000 credits"),
    ]

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 18) {
                    Image(systemName: "creditcard.and.123")
                        .font(.system(size: 42))
                        .foregroundStyle(DesignSystem.Colors.accent)
                        .padding(.top, 28)

                    Text("In-App Credits")
                        .font(.system(.title2, design: .rounded).weight(.bold))
                        .foregroundStyle(DesignSystem.Colors.textPrimary)

                    Text("Secure credit purchases are planned for a future update. Your configured AI providers continue working normally.")
                        .font(.system(.body, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)

                    VStack(spacing: 12) {
                        ForEach(futurePacks, id: \.0) { pack in
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(pack.0)
                                        .font(.system(.body, design: .rounded).weight(.semibold))
                                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                                    Text(pack.1)
                                        .font(.system(.caption, design: .rounded))
                                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                                }
                                Spacer()
                                Text("Later")
                                    .font(.system(.caption, design: .rounded).weight(.semibold))
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                            }
                            .padding(16)
                            .background(DesignSystem.Colors.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                            .archonLiquidGlass(cornerRadius: DesignSystem.Radius.md)
                        }
                    }
                    .padding(.top, 8)

                    Label("Purchases will use Apple StoreKit", systemImage: "checkmark.shield.fill")
                        .font(.system(.caption, design: .rounded).weight(.medium))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                        .padding(.top, 4)
                }
                .padding(20)
            }
        }
        .navigationTitle("Credits & Billing")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct AccountManagementView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @EnvironmentObject var authManager: AuthManager

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            Form {
                Section {
                    Button {
                        Task { await viewModel.signOut() }
                    } label: {
                        HStack {
                            if viewModel.isSigningOut {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                            }
                            Text("Sign Out")
                        }
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                    }
                    .disabled(viewModel.isSigningOut)
                    .listRowBackground(DesignSystem.Colors.elevated)
                    .accessibilityLabel("Sign out of your account")
                } header: {
                    Text("Session")
                } footer: {
                    Text("Signing out keeps your account and cloud data intact.")
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }

                Section {
                    Button(role: .destructive) {
                        viewModel.showDeleteAlert = true
                    } label: {
                        Label("Delete Account", systemImage: "trash")
                            .foregroundStyle(DesignSystem.Colors.danger)
                    }
                    .listRowBackground(DesignSystem.Colors.elevated)
                    .accessibilityLabel("Delete your account permanently")
                } header: {
                    Text("Danger Zone")
                } footer: {
                    Text("Deleting your account permanently removes your projects, conversations, files, and account data.")
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("Account & Privacy")
        .navigationBarTitleDisplayMode(.inline)
        .alert("Delete Account", isPresented: $viewModel.showDeleteAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                Task { await authManager.deleteAccount() }
            }
        } message: {
            Text("This action cannot be undone. All your data will be permanently deleted.")
        }
    }
}

private enum ProfilePhotoError: Error {
    case invalidImage
}

private enum ProfilePhotoStore {
    private static var fileURL: URL? {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("Archon", isDirectory: true)
            .appendingPathComponent("profile-photo.jpg")
    }

    static func load() -> Data? {
        guard let fileURL else { return nil }
        return try? Data(contentsOf: fileURL)
    }

    static func save(_ data: Data) throws {
        guard let fileURL else { return }
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: fileURL, options: .atomic)
    }

    static func remove() throws {
        guard let fileURL, FileManager.default.fileExists(atPath: fileURL.path) else { return }
        try FileManager.default.removeItem(at: fileURL)
    }
}

private extension UIImage {
    var profilePhotoData: Data? {
        let maximumDimension: CGFloat = 512
        let scale = min(maximumDimension / size.width, maximumDimension / size.height, 1)
        let targetSize = CGSize(width: size.width * scale, height: size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: targetSize)
        let resized = renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: targetSize))
        }
        return resized.jpegData(compressionQuality: 0.82)
    }
}

private struct LicenseAcknowledgement: Identifiable {
    let name: String
    let version: String
    let license: String
    let licenseURL: URL

    var id: String { name }
}

private struct LicensesView: View {
    private let acknowledgements = [
        LicenseAcknowledgement(
            name: "Supabase Swift",
            version: "2.53.0",
            license: "MIT License",
            licenseURL: URL(string: "https://github.com/supabase/supabase-swift/blob/main/LICENSE")!
        ),
        LicenseAcknowledgement(
            name: "Swift Crypto",
            version: "4.5.1",
            license: "Apache License 2.0",
            licenseURL: URL(string: "https://github.com/apple/swift-crypto/blob/main/LICENSE.txt")!
        ),
        LicenseAcknowledgement(
            name: "Swift ASN.1",
            version: "1.7.1",
            license: "Apache License 2.0",
            licenseURL: URL(string: "https://github.com/apple/swift-asn1/blob/main/LICENSE.txt")!
        ),
        LicenseAcknowledgement(
            name: "Swift HTTP Types",
            version: "1.6.0",
            license: "Apache License 2.0",
            licenseURL: URL(string: "https://github.com/apple/swift-http-types/blob/main/LICENSE.txt")!
        ),
        LicenseAcknowledgement(
            name: "Swift Clocks",
            version: "1.1.0",
            license: "MIT License",
            licenseURL: URL(string: "https://github.com/pointfreeco/swift-clocks/blob/main/LICENSE")!
        ),
        LicenseAcknowledgement(
            name: "Swift Concurrency Extras",
            version: "1.4.0",
            license: "MIT License",
            licenseURL: URL(string: "https://github.com/pointfreeco/swift-concurrency-extras/blob/main/LICENSE")!
        ),
        LicenseAcknowledgement(
            name: "XCTest Dynamic Overlay",
            version: "1.11.0",
            license: "MIT License",
            licenseURL: URL(string: "https://github.com/pointfreeco/xctest-dynamic-overlay/blob/main/LICENSE")!
        )
    ]

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            List {
                Section {
                    Text("Archon Mobile is built with the following open-source software. Select a package to view its source and complete license notice.")
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                        .listRowBackground(DesignSystem.Colors.elevated)
                }

                Section("Open-Source Acknowledgements") {
                    ForEach(acknowledgements) { item in
                        Link(destination: item.licenseURL) {
                            HStack(spacing: 12) {
                                Image(systemName: "shippingbox")
                                    .foregroundStyle(DesignSystem.Colors.accent)
                                    .frame(width: 24)

                                VStack(alignment: .leading, spacing: 3) {
                                    Text(item.name)
                                        .font(.system(.body, design: .rounded).weight(.medium))
                                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                                    Text("\(item.version) · \(item.license)")
                                        .font(.system(.caption, design: .rounded))
                                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                                }

                                Spacer()

                                Image(systemName: "arrow.up.right.square")
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                            }
                        }
                        .listRowBackground(DesignSystem.Colors.elevated)
                        .accessibilityHint("Opens the package repository and license notice")
                    }
                }
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("Licenses")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    SettingsView()
        .environmentObject(AuthManager.shared)
}
