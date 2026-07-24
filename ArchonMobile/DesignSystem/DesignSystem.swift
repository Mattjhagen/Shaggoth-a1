import SwiftUI

// MARK: - Archon Mobile Design System

/// Centralized design tokens for the entire app.
/// Dark-mode-first with a high-contrast light appearance.
enum DesignSystem {

    // MARK: - Colors

    enum Colors {
        private static var isGlass: Bool {
            UserDefaults.standard.string(forKey: "appearance") == "glass"
        }

        // Brand
        static let accent        = Color(dynamicLight: 0x007F73, dark: 0x00E8CA)
        static let accentDeep    = Color(dynamicLight: 0x00665D, dark: 0x009A8C)
        static var accentDim: Color {
            isGlass
                ? Color(dynamicLight: 0xCFF8EF, dark: 0x17413F).opacity(0.72)
                : Color(dynamicLight: 0xD8F4EF, dark: 0x102D31)
        }

        // Surfaces
        static var base: Color {
            isGlass
                ? Color(dynamicLight: 0xF7FBFF, dark: 0x080B16).opacity(0.62)
                : Color(dynamicLight: 0xF7F8FC, dark: 0x0A0A14)
        }
        static var surface: Color {
            isGlass
                ? Color(dynamicLight: 0xFFFFFF, dark: 0x151A2E).opacity(0.68)
                : Color(dynamicLight: 0xFFFFFF, dark: 0x14142A)
        }
        static var elevated: Color {
            isGlass
                ? Color(dynamicLight: 0xFFFFFF, dark: 0x252A42).opacity(0.72)
                : Color(dynamicLight: 0xECEEF6, dark: 0x1E1E3A)
        }
        static var surfaceBorder: Color {
            isGlass
                ? Color(dynamicLight: 0xFFFFFF, dark: 0xAAB4D8).opacity(0.42)
                : Color(dynamicLight: 0xD6D9E6, dark: 0x2A2A50)
        }
        static var borderFaint: Color {
            isGlass
                ? Color(dynamicLight: 0xD5E0EA, dark: 0x7180A5).opacity(0.28)
                : Color(dynamicLight: 0xE5E7EF, dark: 0x1A1A32)
        }

        // Text
        static let textPrimary   = Color(dynamicLight: 0x171724, dark: 0xEEEEF8)
        static let textSecondary = Color(dynamicLight: 0x55566B, dark: 0x8888AA)
        static let textMuted     = Color(dynamicLight: 0x85879A, dark: 0x505070)

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

        // Gradients
        /// Primary brand gradient: teal flowing into azure. Legible with
        /// `onAccent` text in both appearances.
        static let accentGradient = LinearGradient(
            colors: [accent, Color(dynamicLight: 0x1E6FD9, dark: 0x38B6FF)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        /// Text/icon color that stays legible on top of `accentGradient`.
        static let onAccent = Color(dynamicLight: 0xFFFFFF, dark: 0x0A0A14)

        /// Iridescent sweep used for ambient glows behind hero elements.
        static let gemGlowColors: [Color] = [
            Color(hex: 0x00E8CA),
            Color(hex: 0x5BA4F5),
            Color(hex: 0x9B8CFF),
            Color(hex: 0x00E8CA)
        ]
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
        /// Signature motion: a touch of bounce for content arriving on screen.
        static let fluid = SwiftUI.Animation.spring(response: 0.45, dampingFraction: 0.72)
        /// Tight spring for press feedback and small state flips.
        static let snappy = SwiftUI.Animation.spring(response: 0.28, dampingFraction: 0.85)
        /// Slow, calm spring for ambient/breathing effects.
        static let gentle = SwiftUI.Animation.spring(response: 0.6, dampingFraction: 0.9)
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

    init(dynamicLight lightHex: UInt32, dark darkHex: UInt32) {
        self.init(UIColor { traits in
            UIColor(
                hex: traits.userInterfaceStyle == .dark ? darkHex : lightHex
            )
        })
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
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
            .overlay(
                RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                    .strokeBorder(DesignSystem.Colors.borderFaint, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.12), radius: 14, x: 0, y: 6)
            .archonLiquidGlass(cornerRadius: Radius.md)
    }

    /// Soft colored halo used to make hero elements feel luminous.
    func dsGlow(
        _ color: Color = DesignSystem.Colors.accent,
        radius: CGFloat = 12,
        opacity: Double = 0.35
    ) -> some View {
        shadow(color: color.opacity(opacity), radius: radius, x: 0, y: 0)
    }

    /// Scale-and-fade press feedback for any custom button label.
    func dsPressable() -> some View {
        buttonStyle(DSPressableButtonStyle())
    }

    func archonLiquidGlass(cornerRadius: CGFloat, interactive: Bool = false) -> some View {
        modifier(ArchonLiquidGlassModifier(cornerRadius: cornerRadius, interactive: interactive))
    }
}

// MARK: - Button Styles

struct DSPressableButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(DesignSystem.Animation.snappy, value: configuration.isPressed)
    }
}

/// Primary call-to-action: brand gradient, luminous halo, springy press.
struct DSProminentButtonStyle: ButtonStyle {
    @SwiftUI.Environment(\.isEnabled) private var isEnabled: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DesignSystem.Typography.headline)
            .foregroundStyle(DesignSystem.Colors.onAccent)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(DesignSystem.Colors.accentGradient)
            .clipShape(RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.18), lineWidth: 1)
            )
            .dsGlow(
                DesignSystem.Colors.accent,
                radius: configuration.isPressed ? 6 : 14,
                opacity: isEnabled ? 0.35 : 0
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(isEnabled ? 1 : 0.45)
            .animation(DesignSystem.Animation.snappy, value: configuration.isPressed)
    }
}

private struct ArchonLiquidGlassModifier: ViewModifier {
    let cornerRadius: CGFloat
    let interactive: Bool
    @AppStorage("appearance") private var appearance = "dark"

    @ViewBuilder
    func body(content: Content) -> some View {
        if appearance == "glass" {
            if #available(iOS 26.0, *) {
                content.glassEffect(
                    .regular
                        .tint(DesignSystem.Colors.accent.opacity(0.08))
                        .interactive(interactive),
                    in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                )
            } else {
                content
                    .background(.ultraThinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            }
        } else {
            content
        }
    }
}

typealias Spacing = DesignSystem.Spacing
typealias Radius = DesignSystem.Radius
