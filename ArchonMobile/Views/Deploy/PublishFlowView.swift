import SwiftUI

/// One-click publishing: pick a name, watch the collider work, land on a
/// confetti celebration with a shareable live link.
struct PublishFlowView: View {
    let project: ArchonProject
    var client: PublishClientProtocol = PublishClient()

    @SwiftUI.Environment(\.dismiss) private var dismiss: DismissAction
    @SwiftUI.Environment(\.openURL) private var openURL: OpenURLAction

    @State private var siteName: String
    @State private var availability: SiteNameAvailability?
    @State private var isChecking = false
    @State private var checkTask: Task<Void, Never>?
    @State private var phase: Phase = .naming
    @State private var errorMessage: String?

    private enum Phase: Equatable {
        case naming
        case publishing
        case live(url: String)
    }

    init(project: ArchonProject, client: PublishClientProtocol = PublishClient()) {
        self.project = project
        self.client = client
        _siteName = State(initialValue: Self.suggestedName(from: project.name))
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                switch phase {
                case .naming: namingScreen
                case .publishing: publishingScreen
                case .live(let url): liveScreen(url: url)
                }
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if phase != .publishing {
                        Button("Close") { dismiss() }
                            .dsTouchTarget()
                    }
                }
            }
        }
        .preferredColorScheme(.dark)
        .interactiveDismissDisabled(phase == .publishing)
        .animation(DesignSystem.Animation.fluid, value: phase)
    }

    // MARK: - Step 1: Pick a name

    private var namingScreen: some View {
        VStack(spacing: 28) {
            Spacer()

            VStack(spacing: 10) {
                Image(systemName: "globe")
                    .font(.system(size: 40, weight: .light))
                    .foregroundStyle(DesignSystem.Colors.accent)
                    .dsGlow(radius: 14, opacity: 0.5)

                Text("Name your site")
                    .font(DesignSystem.Typography.title1)
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("This becomes your free web address —\nyou can share it with anyone, anywhere.")
                    .font(DesignSystem.Typography.subhead)
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            VStack(spacing: 10) {
                HStack(spacing: 4) {
                    TextField("your-site-name", text: $siteName)
                        .font(.system(.body, design: .monospaced))
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .multilineTextAlignment(.trailing)
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                        .onChange(of: siteName) { _, newValue in
                            let cleaned = Self.cleaned(newValue)
                            if cleaned != newValue { siteName = cleaned }
                            scheduleAvailabilityCheck()
                        }

                    Text(".vibecodes.space")
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                        .lineLimit(1)
                        .layoutPriority(1)
                }
                .padding(16)
                .background(DesignSystem.Colors.elevated)
                .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous)
                        .strokeBorder(availabilityBorderColor, lineWidth: 1)
                )

                availabilityLabel
                    .frame(minHeight: 20)
            }
            .padding(.horizontal, 28)

            if let errorMessage {
                Text(errorMessage)
                    .font(DesignSystem.Typography.caption)
                    .foregroundStyle(DesignSystem.Colors.danger)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 28)
            }

            Button {
                publish()
            } label: {
                Text("Put my site online")
            }
            .buttonStyle(DSProminentButtonStyle())
            .disabled(!(availability?.available ?? false))
            .padding(.horizontal, 28)

            Spacer()
            Spacer()
        }
        .onAppear { scheduleAvailabilityCheck() }
    }

    @ViewBuilder
    private var availabilityLabel: some View {
        if isChecking {
            HStack(spacing: 6) {
                ProgressView().controlSize(.mini)
                Text("Checking…")
            }
            .font(DesignSystem.Typography.caption)
            .foregroundStyle(DesignSystem.Colors.textMuted)
        } else if let availability {
            HStack(spacing: 6) {
                Image(systemName: availability.available ? "checkmark.circle.fill" : "xmark.circle.fill")
                Text(availability.available ? "It's yours!" : (availability.reason ?? "That name won't work"))
            }
            .font(DesignSystem.Typography.caption)
            .foregroundStyle(availability.available ? DesignSystem.Colors.success : DesignSystem.Colors.danger)
        }
    }

    private var availabilityBorderColor: Color {
        guard let availability, !isChecking else { return DesignSystem.Colors.borderFaint }
        return availability.available
            ? DesignSystem.Colors.success.opacity(0.5)
            : DesignSystem.Colors.danger.opacity(0.5)
    }

    // MARK: - Step 2: Publishing

    private var publishingScreen: some View {
        VStack(spacing: 28) {
            Spacer()

            ColliderLoadingView(size: 150)

            VStack(spacing: 8) {
                Text("Putting your site online…")
                    .font(DesignSystem.Typography.title3)
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("\(siteName).vibecodes.space")
                    .font(.system(.subheadline, design: .monospaced))
                    .foregroundStyle(DesignSystem.Colors.accent)
            }

            Spacer()
        }
    }

    // MARK: - Step 3: Live!

    private func liveScreen(url: String) -> some View {
        VStack(spacing: 24) {
            Spacer()

            Text("🎉")
                .font(.system(size: 64))

            VStack(spacing: 8) {
                Text("You're live!")
                    .font(DesignSystem.Typography.largeTitle)
                    .foregroundStyle(DesignSystem.Colors.textPrimary)

                Text("Your site is on the internet right now.\nAnyone with the link can visit it.")
                    .font(DesignSystem.Typography.subhead)
                    .foregroundStyle(DesignSystem.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Text(url.replacingOccurrences(of: "https://", with: ""))
                .font(.system(.subheadline, design: .monospaced).weight(.semibold))
                .foregroundStyle(DesignSystem.Colors.accent)
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
                .background(DesignSystem.Colors.accent.opacity(0.12))
                .clipShape(Capsule())
                .dsGlow(radius: 12, opacity: 0.3)

            VStack(spacing: 12) {
                if let liveURL = URL(string: url) {
                    ShareLink(item: liveURL) {
                        Label("Share my site", systemImage: "square.and.arrow.up")
                    }
                    .buttonStyle(DSProminentButtonStyle())

                    Button {
                        openURL(liveURL)
                    } label: {
                        Label("See it in Safari", systemImage: "safari")
                            .font(DesignSystem.Typography.headline)
                            .foregroundStyle(DesignSystem.Colors.accent)
                            .frame(maxWidth: .infinity, minHeight: 52)
                    }
                    .dsPressable()
                }
            }
            .padding(.horizontal, 28)

            Spacer()
        }
        .overlay(ConfettiView().allowsHitTesting(false))
        .onAppear {
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
    }

    // MARK: - Actions

    private func scheduleAvailabilityCheck() {
        checkTask?.cancel()
        availability = nil
        errorMessage = nil
        let name = siteName
        guard name.count >= 3 else { return }
        isChecking = true
        checkTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            let result = try? await client.checkName(name)
            guard !Task.isCancelled, name == siteName else { return }
            availability = result
            isChecking = false
        }
    }

    private func publish() {
        errorMessage = nil
        phase = .publishing
        Task {
            do {
                let site = try await client.publish(projectId: project.id, siteName: siteName)
                phase = .live(url: site.url)
            } catch {
                phase = .naming
                errorMessage = (error as? APIError)?.message
                    ?? "We couldn't publish just now. Give it another try."
            }
        }
    }

    // MARK: - Name helpers

    static func suggestedName(from projectName: String) -> String {
        // Project names are often full sentences from the build prompt —
        // pick out the couple of words that actually name the thing.
        let fillers: Set<String> = [
            "build", "make", "create", "design", "a", "an", "the", "my", "me",
            "for", "with", "and", "that", "website", "site", "web", "app", "page"
        ]
        let words = projectName
            .lowercased()
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init)
        let meaningful = words.filter { !fillers.contains($0) }
        let chosen = (meaningful.isEmpty ? words : meaningful).prefix(2)
        let name = cleaned(chosen.joined(separator: "-"))
        return name.isEmpty ? "my-site" : String(name.prefix(30))
    }

    static func cleaned(_ raw: String) -> String {
        var result = ""
        var lastWasDash = false
        for character in raw.lowercased() {
            if character.isLetter && character.isASCII || character.isNumber && character.isASCII {
                result.append(character)
                lastWasDash = false
            } else if !lastWasDash && !result.isEmpty {
                result.append("-")
                lastWasDash = true
            }
        }
        while result.hasSuffix("-") { result.removeLast() }
        return String(result.prefix(63))
    }
}

// MARK: - Confetti

/// Lightweight celebratory confetti rendered with Canvas; deterministic per
/// particle index so it needs no stored randomness.
private struct ConfettiView: View {
    private let particleCount = 60
    private let duration: Double = 3.2

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let now = timeline.date.timeIntervalSinceReferenceDate
                let elapsed = now.truncatingRemainder(dividingBy: duration)

                for index in 0..<particleCount {
                    let seed = Double(index)
                    let progress = (elapsed + seed * 0.05).truncatingRemainder(dividingBy: duration) / duration
                    let x = size.width * fraction(seed * 12.9898)
                    let drift = sin((progress * 4 + seed) * .pi) * 24
                    let y = -20 + progress * (size.height + 60)
                    let hue = fraction(seed * 0.61803)
                    let color = Color(hue: hue, saturation: 0.75, brightness: 1)
                    let rotation = Angle.radians(progress * 6 * .pi + seed)
                    let rect = CGRect(x: -4, y: -2.5, width: 8, height: 5)

                    var piece = context
                    piece.translateBy(x: x + drift, y: y)
                    piece.rotate(by: rotation)
                    piece.opacity = 1 - progress * 0.6
                    piece.fill(Path(roundedRect: rect, cornerRadius: 1.5), with: .color(color))
                }
            }
        }
        .ignoresSafeArea()
    }

    private func fraction(_ value: Double) -> Double {
        let scaled = sin(value) * 43758.5453
        return scaled - scaled.rounded(.down)
    }
}

#Preview {
    PublishFlowView(
        project: ArchonProject(
            id: "p1",
            name: "Sarah's Resume",
            description: "Personal resume site",
            status: .active,
            createdAt: Date(),
            updatedAt: Date()
        ),
        client: MockPublishClient()
    )
}

private struct MockPublishClient: PublishClientProtocol {
    func checkName(_ name: String) async throws -> SiteNameAvailability {
        SiteNameAvailability(available: true, reason: nil)
    }

    func publish(projectId: String, siteName: String) async throws -> PublishedSite {
        PublishedSite(id: "d1", slug: siteName, url: "https://\(siteName).vibecodes.space")
    }
}
