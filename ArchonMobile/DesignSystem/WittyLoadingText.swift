import SwiftUI

/// Rotating lighthearted status lines shown while the AI works — the loading
/// experience should make people smile, not stare at "Processing…".
struct WittyLoadingText: View {
    var font: Font = .system(.caption, design: .rounded)
    var color: Color = DesignSystem.Colors.textMuted

    private static let quotes: [String] = [
        "Convincing the pixels to line up…",
        "Sprinkling a little magic dust ✨",
        "Teaching the robots some manners…",
        "Assembling tiny building blocks…",
        "Warming up the idea engine…",
        "Asking the internet very politely…",
        "Untangling the wires…",
        "Making it pretty…",
        "Herding electrons into place…",
        "Polishing the corners…",
        "Brewing something good ☕️",
        "Double-checking the shiny bits…",
        "Drawing outside the lines (on purpose)…",
        "Giving your idea a pep talk…",
        "Stacking ones and zeros neatly…",
        "Adding the finishing sparkle…"
    ]

    var body: some View {
        TimelineView(.periodic(from: .distantPast, by: 3.0)) { timeline in
            let tick = Int(timeline.date.timeIntervalSinceReferenceDate / 3.0)
            let quote = Self.quotes[tick % Self.quotes.count]

            Text(quote)
                .font(font)
                .foregroundStyle(color)
                .id(quote)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
                .animation(DesignSystem.Animation.gentle, value: quote)
        }
        .accessibilityLabel("Working on it")
    }
}

#Preview {
    ZStack {
        Color(hex: 0x0A0A14).ignoresSafeArea()
        WittyLoadingText()
    }
}
