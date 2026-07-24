import SwiftUI

struct OnboardingFlow: View {
    @Binding var hasCompletedOnboarding: Bool
    @State private var currentPage = 0
    @State private var showAuth = false

    private let pages: [(title: String, subtitle: String, icon: String, color: Color)] = [
        ("Welcome to Archon", "Build apps with AI — just describe what you want and watch it come to life.", "sparkles", Color(hex: 0x00E8CA)),
        ("AI-Powered Builder", "Our AI agent breaks down your idea into tasks, writes code, and builds your app step by step.", "brain.head.profile", Color(hex: 0x5BA4F5)),
        ("Live Code Editor", "Browse, edit, and save generated code with syntax highlighting and file management.", "chevron.left.forwardslash.chevron.right", Color(hex: 0xE5C241)),
        ("Preview & Deploy", "See your app running in real-time with live preview, then share it with the world.", "globe", Color(hex: 0x23D18B))
    ]

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            VStack(spacing: 0) {
                TabView(selection: $currentPage) {
                    ForEach(Array(pages.enumerated()), id: \.offset) { index, page in
                        OnboardingPageView(
                            title: page.title,
                            subtitle: page.subtitle,
                            icon: page.icon,
                            color: page.color
                        )
                        .tag(index)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .animation(.easeInOut, value: currentPage)

                // Page indicators
                HStack(spacing: 8) {
                    ForEach(0..<pages.count, id: \.self) { index in
                        Circle()
                            .fill(index == currentPage ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
                            .frame(width: index == currentPage ? 8 : 6,
                                   height: index == currentPage ? 8 : 6)
                            .animation(.easeInOut(duration: 0.2), value: currentPage)
                    }
                }
                .padding(.bottom, 32)

                // Buttons
                VStack(spacing: 16) {
                    Button {
                        if currentPage < pages.count - 1 {
                            withAnimation { currentPage += 1 }
                        } else {
                            showAuth = true
                            hasCompletedOnboarding = true
                        }
                    } label: {
                        Text(currentPage < pages.count - 1 ? "Next" : "Get Started")
                            .font(.headline)
                            .foregroundStyle(DesignSystem.Colors.base)
                            .frame(maxWidth: .infinity, minHeight: 50)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(DesignSystem.Colors.accent)
                    .padding(.horizontal, 32)
                    .dsTouchTarget()

                    Button("Skip") {
                        hasCompletedOnboarding = true
                    }
                    .font(.subheadline)
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .dsTouchTarget()
                }
                .padding(.bottom, 48)
            }
        }
        .dynamicTypeSize(.xSmall ... .accessibility3)
    }
}

struct OnboardingPageView: View {
    let title: String
    let subtitle: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                Circle()
                    .fill(color.opacity(0.15))
                    .frame(width: 140, height: 140)

                Image(systemName: icon)
                    .font(.system(size: 56, weight: .light))
                    .foregroundStyle(color)
            }
            .accessibilityHidden(true)

            VStack(spacing: 12) {
                Text(title)
                    .font(.system(.largeTitle, design: .rounded).weight(.bold))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)

                Text(subtitle)
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Spacer()
            Spacer()
        }
        .padding()
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    OnboardingFlow(hasCompletedOnboarding: .constant(false))
}
