import SwiftUI

/// Collapsible raw-output log tucked beneath friendly timeline entries —
/// hidden by default, one tap away for the curious.
struct TerminalPullOut: View {
    let rawOutput: String
    let metadata: [String: AnyCodable]?

    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: {
                withAnimation(DesignSystem.Animation.fluid) {
                    isExpanded.toggle()
                }
            }) {
                HStack(spacing: 6) {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10, weight: .bold))
                    Text("Under the hood")
                        .font(.system(.caption, design: .monospaced))
                        .fontWeight(.semibold)
                    Spacer()
                }
                .foregroundStyle(DesignSystem.Colors.textSecondary)
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(DesignSystem.Colors.elevated)
            }
            .buttonStyle(.plain)

            if isExpanded {
                VStack(alignment: .leading, spacing: 8) {
                    Text(rawOutput)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(DesignSystem.Colors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)

                    if let metadata = metadata, !metadata.isEmpty {
                        Divider().overlay(DesignSystem.Colors.borderFaint)
                        ForEach(Array(metadata.keys.sorted()), id: \.self) { key in
                            if let value = metadata[key]?.value as? String {
                                HStack(alignment: .top, spacing: 4) {
                                    Text("\(key):")
                                        .foregroundStyle(DesignSystem.Colors.textMuted)
                                    Text(value)
                                        .foregroundStyle(DesignSystem.Colors.info)
                                }
                                .font(.system(.caption2, design: .monospaced))
                            }
                        }
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.black.opacity(0.2))
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(DesignSystem.Colors.borderFaint, lineWidth: 1)
        )
    }
}
