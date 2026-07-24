import SwiftUI

struct BuildProgressView: View {
    let progress: Double
    let currentStep: Int
    let maxSteps: Int
    let status: TaskStatus
    let projectName: String

    @State private var animatedProgress: Double = 0
    @State private var showPulse = false
    @State private var particleOffsets: [CGFloat] = Array(repeating: 0, count: 8)
    @State private var rotationAngle: Double = 0

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                VStack(spacing: 32) {
                    Spacer()

                    buildIcon
                        .padding(.top, 20)

                    VStack(spacing: 12) {
                        Text("Building \(projectName)")
                            .font(.system(.title2, design: .rounded).weight(.bold))
                            .foregroundStyle(DesignSystem.Colors.textPrimary)
                            .multilineTextAlignment(.center)

                        statusText
                    }

                    progressBar
                        .padding(.horizontal, 40)

                    stepIndicators
                        .padding(.horizontal, 40)

                    if status == .completed {
                        completedView
                    } else if status == .failed || status == .cancelled {
                        failedView
                    } else {
                        activityLog
                    }

                    Spacer()
                }
            }
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.8)) {
                animatedProgress = progress
            }
            startAnimations()
        }
        .onChange(of: progress) { _, newValue in
            withAnimation(.easeOut(duration: 0.5)) {
                animatedProgress = newValue
            }
        }
    }

    // MARK: - Build Icon

    private var buildIcon: some View {
        ZStack {
            Circle()
                .fill(DesignSystem.Colors.accent.opacity(0.1))
                .frame(width: 120, height: 120)

            Circle()
                .trim(from: 0, to: animatedProgress)
                .stroke(
                    DesignSystem.Colors.accent,
                    style: StrokeStyle(lineWidth: 4, lineCap: .round)
                )
                .frame(width: 120, height: 120)
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 0.8), value: animatedProgress)

            if status == .completed {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(DesignSystem.Colors.success)
                    .transition(.scale.combined(with: .opacity))
            } else if status == .failed {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(DesignSystem.Colors.danger)
                    .transition(.scale.combined(with: .opacity))
            } else {
                ColliderLoadingView(size: 96)
            }

            if showPulse && status.isActive {
                ForEach(0..<8, id: \.self) { i in
                    Circle()
                        .fill(DesignSystem.Colors.accent.opacity(0.3))
                        .frame(width: 6, height: 6)
                        .offset(x: particleOffsets[i])
                        .opacity(showPulse ? 1 : 0)
                }
            }
        }
    }

    // MARK: - Status Text

    @ViewBuilder
    private var statusText: some View {
        switch status {
        case .queued:
            Text("Waiting in line…")
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        case .planning:
            Text("Sketching out your app…")
                .foregroundStyle(DesignSystem.Colors.info)
        case .running:
            Text("Building your app…")
                .foregroundStyle(DesignSystem.Colors.accent)
        case .verifying:
            Text("Double-checking everything…")
                .foregroundStyle(DesignSystem.Colors.warning)
        case .completed:
            Text("All done!")
                .foregroundStyle(DesignSystem.Colors.success)
        case .failed:
            Text("Something didn't work")
                .foregroundStyle(DesignSystem.Colors.danger)
        case .cancelled:
            Text("Build stopped")
                .foregroundStyle(DesignSystem.Colors.textMuted)
        case .cancelling:
            Text("Stopping…")
                .foregroundStyle(DesignSystem.Colors.warning)
        case .blocked:
            Text("Needs your attention")
                .foregroundStyle(DesignSystem.Colors.danger)
        }
    }

    // MARK: - Progress Bar

    private var progressBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Progress")
                    .font(.system(.caption, design: .rounded).weight(.medium))
                    .foregroundStyle(DesignSystem.Colors.textSecondary)

                Spacer()

                if maxSteps > 0 {
                    Text("\(currentStep) / \(maxSteps) steps")
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(DesignSystem.Colors.surface)
                        .frame(height: 8)

                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [DesignSystem.Colors.accent, DesignSystem.Colors.accentDeep],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * animatedProgress, height: 8)
                        .animation(.easeInOut(duration: 0.5), value: animatedProgress)
                }
            }
            .frame(height: 8)
        }
    }

    // MARK: - Step Indicators

    private var stepIndicators: some View {
        HStack(spacing: 12) {
            stepChip(icon: "brain.head.profile", label: "Plan", isActive: status == .planning, isComplete: currentStep > 0)
            stepChip(icon: "hammer.fill", label: "Build", isActive: status == .running, isComplete: currentStep > maxSteps / 2)
            stepChip(icon: "checkmark.shield", label: "Verify", isActive: status == .verifying, isComplete: status == .completed)
        }
    }

    private func stepChip(icon: String, label: String, isActive: Bool, isComplete: Bool) -> some View {
        HStack(spacing: 4) {
            Image(systemName: isComplete ? "checkmark.circle.fill" : icon)
                .font(.system(size: 12))
                .foregroundStyle(isComplete ? DesignSystem.Colors.success : isActive ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)

            Text(label)
                .font(.system(.caption2, design: .rounded).weight(.medium))
                .foregroundStyle(isComplete ? DesignSystem.Colors.success : isActive ? DesignSystem.Colors.accent : DesignSystem.Colors.textMuted)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            (isActive ? DesignSystem.Colors.accent : DesignSystem.Colors.surface).opacity(isActive ? 0.15 : 0.5)
        )
        .clipShape(Capsule())
        .overlay(
            Capsule().stroke(isActive ? DesignSystem.Colors.accent.opacity(0.3) : Color.clear, lineWidth: 1)
        )
    }

    // MARK: - Completed View

    private var completedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 32))
                .foregroundStyle(DesignSystem.Colors.success)

            Text("Your app is ready!")
                .font(.system(.headline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Text("Tap Preview to see your live app")
                .font(.system(.subheadline, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Failed View

    private var failedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 32))
                .foregroundStyle(DesignSystem.Colors.danger)

            Text("Something went wrong")
                .font(.system(.headline, design: .rounded).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.textPrimary)

            Text("Check the AI Agent tab for details")
                .font(.system(.subheadline, design: .rounded))
                .foregroundStyle(DesignSystem.Colors.textSecondary)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Activity Log

    private var activityLog: some View {
        VStack(spacing: 8) {
            HStack(spacing: 6) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(DesignSystem.Colors.accent)
                        .frame(width: 6, height: 6)
                        .scaleEffect(showPulse ? 1.2 : 0.6)
                        .animation(
                            .easeInOut(duration: 0.6)
                            .repeatForever(autoreverses: true)
                            .delay(Double(i) * 0.2),
                            value: showPulse
                        )
                }
            }
            WittyLoadingText()
        }
        .opacity(status.isActive ? 1 : 0)
    }

    // MARK: - Animations

    private func startAnimations() {
        showPulse = true
        withAnimation(.linear(duration: 3).repeatForever(autoreverses: false)) {
            rotationAngle = 360
        }
    }
}

#Preview {
    BuildProgressView(
        progress: 0.6,
        currentStep: 12,
        maxSteps: 20,
        status: .running,
        projectName: "Todo App"
    )
}
