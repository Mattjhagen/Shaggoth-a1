import SwiftUI

struct DeployOptionsView: View {
    let projectName: String
    let projectDescription: String?
    let onDeploy: (DeployPlatform) -> Void
    @Environment(\.dismiss) private var dismiss

    enum DeployPlatform: String, CaseIterable, Identifiable {
        case fly
        case render
        case netlify
        case githubPages

        var id: String { rawValue }

        var label: String {
            switch self {
            case .fly: return "Fly.io"
            case .render: return "Render"
            case .netlify: return "Netlify"
            case .githubPages: return "GitHub Pages"
            }
        }

        var icon: String {
            switch self {
            case .fly: return "cloud.fill"
            case .render: return "square.and.arrow.up.fill"
            case .netlify: return "globe.americas.fill"
            case .githubPages: return "chevron.left.forwardslash.chevron.right"
            }
        }

        var color: Color {
            switch self {
            case .fly: return Color(.sRGB, red: 0.44, green: 0.36, blue: 0.96, opacity: 1)
            case .render: return Color(.sRGB, red: 0.13, green: 0.59, blue: 0.95, opacity: 1)
            case .netlify: return Color(.sRGB, red: 0.0, green: 0.81, blue: 0.79, opacity: 1)
            case .githubPages: return Color(.sRGB, red: 0.44, green: 0.44, blue: 0.44, opacity: 1)
            }
        }

        var description: String {
            switch self {
            case .fly: return "Deploy globally with edge computing. Great for full-stack apps."
            case .render: return "Automatic deploys from Git. Free tier available for static sites."
            case .netlify: return "Perfect for static sites and JAMstack. Instant deploys."
            case .githubPages: return "Free hosting directly from your GitHub repository."
            }
        }

        var features: [String] {
            switch self {
            case .fly:
                return ["Global edge network", "Auto-scaling", "Built-in Postgres", "Custom domains"]
            case .render:
                return ["Auto-deploy from Git", "Free static sites", "Managed databases", "Custom domains"]
            case .netlify:
                return ["Instant deploys", "Serverless functions", "Forms & identity", "Custom domains"]
            case .githubPages:
                return ["Free hosting", "Jekyll support", "Custom domains", "HTTPS by default"]
            }
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        headerSection

                        ForEach(DeployPlatform.allCases) { platform in
                            deployCard(for: platform)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 16)
                    .padding(.bottom, 32)
                }
            }
            .navigationTitle("Deploy Options")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .dsTouchTarget()
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.1))
                    .frame(width: 60, height: 60)

                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }

            VStack(spacing: 4) {
                Text("Deploy \(projectName)")
                    .font(.system(.title3, design: .rounded).weight(.bold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                if let desc = projectDescription {
                    Text(desc)
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                        .multilineTextAlignment(.center)
                }
            }
        }
        .padding(.bottom, 8)
    }

    // MARK: - Deploy Card

    private func deployCard(for platform: DeployPlatform) -> some View {
        Button {
            onDeploy(platform)
            dismiss()
        } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: platform.icon)
                        .font(.system(size: 20))
                        .foregroundStyle(platform.color)
                        .frame(width: 40, height: 40)
                        .background(platform.color.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(platform.label)
                            .font(.system(.headline, design: .rounded).weight(.semibold))
                            .foregroundStyle(DesignSystem.Colors.textPrimary)

                        Text(platform.description)
                            .font(.system(.caption, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                            .lineLimit(2)
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }

                HStack(spacing: 8) {
                    ForEach(platform.features, id: \.self) { feature in
                        Text(feature)
                            .font(.system(.caption2, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textMuted)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(DesignSystem.Colors.surface)
                            .clipShape(Capsule())
                    }
                }
            }
            .padding(16)
            .background(DesignSystem.Colors.elevated)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(DesignSystem.Colors.surfaceBorder.opacity(0.5), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .dsTouchTarget()
    }
}

#Preview {
    DeployOptionsView(
        projectName: "My App",
        projectDescription: "A beautiful todo app",
        onDeploy: { _ in }
    )
}
