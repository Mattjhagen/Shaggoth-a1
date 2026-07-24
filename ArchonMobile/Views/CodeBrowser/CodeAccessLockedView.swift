import SwiftUI

/// Replaces the code browser in the main tab bar: full codebase access will
/// be an in-app purchase, so the code stays behind a friendly locked door.
/// The CodeBrowser module remains intact underneath for when it unlocks.
struct CodeAccessLockedView: View {
    @State private var showComingSoon = false
    @State private var glowPulse = false

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                VStack(spacing: 24) {
                    Spacer()

                    ZStack {
                        Circle()
                            .fill(
                                AngularGradient(
                                    colors: DesignSystem.Colors.gemGlowColors,
                                    center: .center
                                )
                            )
                            .frame(width: 120, height: 120)
                            .blur(radius: 38)
                            .opacity(glowPulse ? 0.5 : 0.25)
                            .scaleEffect(glowPulse ? 1.06 : 0.92)

                        Circle()
                            .fill(DesignSystem.Colors.accent.opacity(0.12))
                            .frame(width: 88, height: 88)

                        Image(systemName: "lock.fill")
                            .font(.system(size: 34, weight: .light))
                            .foregroundStyle(DesignSystem.Colors.accent)
                            .dsGlow(radius: 14, opacity: 0.5)
                    }
                    .accessibilityHidden(true)
                    .onAppear {
                        withAnimation(.easeInOut(duration: 2.6).repeatForever(autoreverses: true)) {
                            glowPulse = true
                        }
                    }

                    VStack(spacing: 10) {
                        Text("Your code, yours to keep")
                            .font(DesignSystem.Typography.title2)
                            .foregroundStyle(DesignSystem.Colors.textPrimary)

                        Text("Everything Archon builds for you has real code behind it. Soon you'll be able to unlock it all — browse it, download it, and take it anywhere.")
                            .font(DesignSystem.Typography.subhead)
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 36)
                    }

                    Button {
                        showComingSoon = true
                    } label: {
                        Label("Unlock Full Code Access", systemImage: "sparkles")
                    }
                    .buttonStyle(DSProminentButtonStyle())
                    .padding(.horizontal, 36)

                    Spacer()
                    Spacer()
                }
            }
            .navigationTitle("Code")
            .navigationBarTitleDisplayMode(.inline)
            .alert("Coming soon 🚧", isPresented: $showComingSoon) {
                Button("Can't wait!", role: .cancel) {}
            } message: {
                Text("Full code access is on its way. You'll be able to unlock your entire codebase right here.")
            }
        }
    }
}

#Preview {
    CodeAccessLockedView()
        .preferredColorScheme(.dark)
}
