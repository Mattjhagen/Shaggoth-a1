import SwiftUI

// MARK: - Archon Mobile Design System

/// Centralized design tokens for the entire app.
/// Dark-mode-first with automatic light-mode adaptation.
enum DesignSystem {

    // MARK: - Colors

    enum Colors {
        // Brand
        static let accent        = Color("AccentColor")
        static let accentDeep    = Color(hex: 0x009A8C)
        static let accentDim     = Color(hex: 0x00E8CA).opacity(0.12)

        // Surfaces
        static let base          = Color(hex: 0x0A0A14)
        static let surface       = Color(hex: 0x14142A)
        static let elevated      = Color(hex: 0x1E1E3A)
        static let surfaceBorder = Color(hex: 0x2A2A50)
        static let borderFaint   = Color(hex: 0x1A1A32)

        // Text
        static let textPrimary   = Color(hex: 0xEEEEF8)
        static let textSecondary = Color(hex: 0x8888AA)
        static let textMuted     = Color(hex: 0x505070)

        // Semantic
        static let success       = Color(hex: 0x23D18B)
        static let danger        = Color(hex: 0xF14C4C)
        static let warning       = Color(hex: 0xE5C241)
        static let info          = Color(hex: 0x5BA4F5)

        // Adaptive (light + dark)
        static let adaptiveBackground = Color(.systemBackground)
        static let adaptiveSecondaryBg = Color(.secondarySystemBackground)
        static let adaptiveSeparator   = Color(.separator)
        static let adaptiveLabel       = Color(.label)
        static let adaptiveSecondaryLabel = Color(.secondaryLabel)
    }

    // MARK: - Typography

    enum Typography {
        static let largeTitle = Font.system(.largeTitle, design: .rounded).weight(.bold)
        static let title1     = Font.system(.title, design: .rounded).weight(.bold)
        static let title2     = Font.system(.title2, design: .rounded).weight(.semibold)
        static let title3     = Font.system(.title3, design: .rounded).weight(.semibold)
        static let headline   = Font.system(.headline, design: .rounded).weight(.semibold)
        static let body       = Font.system(.body, design: .rounded)
        static let callout    = Font.system(.callout, design: .rounded)
        static let subhead    = Font.system(.subheadline, design: .rounded)
        static let caption    = Font.system(.caption, design: .rounded)
        static let caption2   = Font.system(.caption2, design: .rounded)
        static let mono       = Font.system(.caption, design: .monospaced)
        static let monoBody   = Font.system(.body, design: .monospaced)
    }

    // MARK: - Spacing

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
        static let xxxl: CGFloat = 48
    }

    // MARK: - Corner Radius

    enum Radius {
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 20
        static let pill: CGFloat = 999
    }

    // MARK: - Animation

    enum Animation {
        static let quick = SwiftUI.Animation.easeOut(duration: 0.15)
        static let standard = SwiftUI.Animation.easeInOut(duration: 0.25)
        static let slow = SwiftUI.Animation.easeInOut(duration: 0.4)
        static let spring = SwiftUI.Animation.spring(response: 0.35, dampingFraction: 0.8)
    }
}

// MARK: - Color Hex Init

extension Color {
    init(hex: UInt32, opacity: Double = 1.0) {
        self.init(.sRGB,
                  red:   Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue:  Double(hex & 0xFF) / 255,
                  opacity: opacity)
    }
}

// MARK: - View Helpers

extension View {
    func dsTouchTarget() -> some View {
        frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
    }

    func dsCardStyle() -> some View {
        padding(Spacing.lg)
            .background(DesignSystem.Colors.elevated)
            .clipShape(RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
    }
}

typealias Spacing = DesignSystem.Spacing
typealias Radius = DesignSystem.Radius
