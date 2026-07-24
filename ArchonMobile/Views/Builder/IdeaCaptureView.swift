import SwiftUI

/// Guided idea capture: three friendly questions and tappable templates that
/// quietly compose a high-quality build prompt. Replaces the intimidating
/// blank text box for first-time and non-technical users.
struct IdeaCaptureView: View {
    var preselectedTemplate: IdeaTemplate?
    var onLaunch: (String) -> Void

    @State private var selectedTemplate: IdeaTemplate?
    @State private var customIdea = ""
    @State private var audience: String?
    @State private var vibe: String?
    @FocusState private var isIdeaFieldFocused: Bool

    private static let audiences = ["Just me", "My business", "A client", "Friends & family"]
    private static let vibes = ["Clean & simple", "Bold & colorful", "Warm & friendly", "Sleek & professional", "Playful"]

    init(preselectedTemplate: IdeaTemplate? = nil, onLaunch: @escaping (String) -> Void) {
        self.preselectedTemplate = preselectedTemplate
        self.onLaunch = onLaunch
        _selectedTemplate = State(initialValue: preselectedTemplate)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            // Q1: What are you making?
            VStack(alignment: .leading, spacing: 12) {
                questionLabel("What are you making?")

                FlowChips(items: IdeaTemplate.allCases.map(\.title)) { title in
                    let template = IdeaTemplate.allCases.first { $0.title == title }
                    chip(
                        title,
                        icon: template?.icon,
                        isSelected: selectedTemplate?.title == title
                    ) {
                        selectedTemplate = selectedTemplate?.title == title ? nil : template
                        if selectedTemplate != nil { customIdea = "" }
                    }
                }

                TextField("…or describe it your own way", text: $customIdea, axis: .vertical)
                    .font(.system(.subheadline, design: .rounded))
                    .lineLimit(1...3)
                    .focused($isIdeaFieldFocused)
                    .padding(12)
                    .background(DesignSystem.Colors.elevated)
                    .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
                    .onChange(of: customIdea) { _, newValue in
                        if !newValue.isEmpty { selectedTemplate = nil }
                    }
            }

            // Q2: Who's it for?
            VStack(alignment: .leading, spacing: 12) {
                questionLabel("Who's it for?")
                FlowChips(items: Self.audiences) { option in
                    chip(option, isSelected: audience == option) {
                        audience = audience == option ? nil : option
                    }
                }
            }

            // Q3: Pick a vibe
            VStack(alignment: .leading, spacing: 12) {
                questionLabel("Pick a vibe")
                FlowChips(items: Self.vibes) { option in
                    chip(option, isSelected: vibe == option) {
                        vibe = vibe == option ? nil : option
                    }
                }
            }

            Button {
                isIdeaFieldFocused = false
                onLaunch(composedPrompt)
            } label: {
                Text("Let's build it ✨")
            }
            .buttonStyle(DSProminentButtonStyle())
            .disabled(!canLaunch)
        }
        .animation(DesignSystem.Animation.snappy, value: selectedTemplate)
        .animation(DesignSystem.Animation.snappy, value: audience)
        .animation(DesignSystem.Animation.snappy, value: vibe)
    }

    private var canLaunch: Bool {
        selectedTemplate != nil || !customIdea.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// The quiet part: the friendly answers become a thorough build prompt.
    private var composedPrompt: String {
        let idea = selectedTemplate?.prompt
            ?? customIdea.trimmingCharacters(in: .whitespacesAndNewlines)

        var parts = [idea]
        if let audience {
            parts.append("It's for \(audience.lowercased()).")
        }
        if let vibe {
            parts.append("The look and feel should be \(vibe.lowercased()).")
        }
        parts.append(
            "Make it beautiful, phone-friendly, and complete with realistic example content, so it feels finished the moment it loads."
        )
        return parts.joined(separator: " ")
    }

    private func questionLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(.headline, design: .rounded).weight(.semibold))
            .foregroundStyle(DesignSystem.Colors.textPrimary)
    }

    private func chip(
        _ title: String,
        icon: String? = nil,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let icon {
                    Image(systemName: icon)
                        .font(.caption)
                }
                Text(title)
                    .font(.system(.subheadline, design: .rounded).weight(.medium))
            }
            .foregroundStyle(isSelected ? DesignSystem.Colors.onAccent : DesignSystem.Colors.textPrimary)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background {
                if isSelected {
                    Capsule().fill(DesignSystem.Colors.accentGradient)
                } else {
                    Capsule().fill(DesignSystem.Colors.elevated)
                }
            }
            .overlay(
                Capsule().strokeBorder(
                    isSelected ? Color.clear : DesignSystem.Colors.borderFaint,
                    lineWidth: 1
                )
            )
            .dsGlow(radius: 8, opacity: isSelected ? 0.3 : 0)
        }
        .dsPressable()
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

// MARK: - Templates

enum IdeaTemplate: String, CaseIterable, Identifiable {
    case resume
    case smallBusiness
    case onlineStore
    case pos
    case portfolio

    var id: String { rawValue }

    var title: String {
        switch self {
        case .resume: return "Resume site"
        case .smallBusiness: return "Small business"
        case .onlineStore: return "Online store"
        case .pos: return "POS system"
        case .portfolio: return "Portfolio"
        }
    }

    var icon: String {
        switch self {
        case .resume: return "person.text.rectangle"
        case .smallBusiness: return "storefront"
        case .onlineStore: return "cart"
        case .pos: return "creditcard"
        case .portfolio: return "photo.on.rectangle.angled"
        }
    }

    var prompt: String {
        switch self {
        case .resume:
            return "Build a personal resume website with a warm introduction, work history, skills, and an easy way to get in touch."
        case .smallBusiness:
            return "Build a small business website with a welcoming home page, services, opening hours, photos, and a contact section."
        case .onlineStore:
            return "Build an online store with a product gallery, product detail pages, a shopping cart, and a simple checkout."
        case .pos:
            return "Build a point-of-sale system with a product grid, a running order total, quick checkout, and a daily sales summary."
        case .portfolio:
            return "Build a portfolio website that shows off projects with big images, short descriptions, and a personal about page."
        }
    }
}

// MARK: - Flow layout for chips

/// Wraps chips onto multiple lines like text.
struct FlowChips<Content: View>: View {
    let items: [String]
    @ViewBuilder let content: (String) -> Content

    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(items, id: \.self) { item in
                content(item)
            }
        }
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        let height = rows.map { $0.height }.reduce(0, +) + spacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: proposal.width ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var y = bounds.minY
        for row in rows {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(
                    at: CGPoint(x: x, y: y),
                    proposal: ProposedViewSize(size)
                )
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var indices: [Int] = []
        var height: CGFloat = 0
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [Row] {
        let maxWidth = proposal.width ?? .infinity
        var rows: [Row] = []
        var current = Row()
        var x: CGFloat = 0

        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, !current.indices.isEmpty {
                rows.append(current)
                current = Row()
                x = 0
            }
            current.indices.append(index)
            current.height = max(current.height, size.height)
            x += size.width + spacing
        }
        if !current.indices.isEmpty {
            rows.append(current)
        }
        return rows
    }
}

#Preview {
    ZStack {
        Color(hex: 0x0A0A14).ignoresSafeArea()
        ScrollView {
            IdeaCaptureView { prompt in
                print(prompt)
            }
            .padding(24)
        }
    }
    .preferredColorScheme(.dark)
}
