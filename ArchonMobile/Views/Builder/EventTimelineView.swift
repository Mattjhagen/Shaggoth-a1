import SwiftUI

struct EventTimelineView: View {
    let events: [TaskEvent]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if events.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.system(size: 28))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                    Text("No activity yet")
                        .font(.system(.subheadline, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textSecondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 40)
                .accessibilityElement(children: .combine)
            } else {
                ForEach(Array(events.enumerated()), id: \.element.id) { index, event in
                    timelineRow(event: event, isLast: index == events.count - 1)
                }
            }
        }
    }

    @ViewBuilder
    private func timelineRow(event: TaskEvent, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 14) {
            // Timeline line and dot
            VStack(spacing: 0) {
                Image(systemName: event.type.icon)
                    .font(.system(size: 10))
                    .foregroundStyle(dotColor(for: event.type))
                    .frame(width: 28, height: 28)
                    .background(dotColor(for: event.type).opacity(0.15))
                    .clipShape(Circle())
                    .padding(.top, 2)

                if !isLast {
                    Rectangle()
                        .fill(DesignSystem.Colors.surfaceBorder)
                        .frame(width: 2)
                        .frame(minHeight: 20)
                }
            }

            // Content
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(event.type.displayCategory)
                        .font(.system(.caption2, design: .rounded).weight(.semibold))
                        .foregroundStyle(dotColor(for: event.type))

                    Spacer()

                    Text(event.timestamp, style: .relative)
                        .font(.system(.caption2, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }

                Text(event.content)
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                if let metadata = event.metadata, !metadata.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(Array(metadata.keys.sorted()), id: \.self) { key in
                            if let value = metadata[key]?.value as? String {
                                Text("\(key): \(value)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(DesignSystem.Colors.surface)
                                    .clipShape(Capsule())
                            }
                        }
                    }
                }
            }
            .padding(.bottom, 16)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(event.type.displayCategory): \(event.content). \(event.timestamp.formatted(date: .abbreviated, time: .shortened)).")
    }

    private func dotColor(for type: TaskEvent.EventType) -> Color {
        switch type {
        case .planning: return DesignSystem.Colors.info
        case .modelCall: return .purple
        case .toolCall: return DesignSystem.Colors.warning
        case .toolResult: return DesignSystem.Colors.accent
        case .verification: return DesignSystem.Colors.success
        case .completion: return DesignSystem.Colors.success
        case .blocker: return DesignSystem.Colors.warning
        case .error: return DesignSystem.Colors.danger
        case .fileEdit: return .orange
        case .message: return DesignSystem.Colors.accent
        }
    }
}

#Preview {
    ScrollView {
        EventTimelineView(events: [
            TaskEvent(id: "1", taskId: "t1", sequence: 1, timestamp: Date().addingTimeInterval(-300), type: .planning, content: "Analyzing project structure", metadata: nil),
            TaskEvent(id: "2", taskId: "t1", sequence: 2, timestamp: Date().addingTimeInterval(-200), type: .toolCall, content: "Reading source files", metadata: ["tool": AnyCodable("file_read")]),
            TaskEvent(id: "3", taskId: "t1", sequence: 3, timestamp: Date().addingTimeInterval(-100), type: .fileEdit, content: "Creating new component", metadata: ["file": AnyCodable("src/Component.swift")]),
            TaskEvent(id: "4", taskId: "t1", sequence: 4, timestamp: Date(), type: .completion, content: "Build completed successfully", metadata: nil)
        ])
        .padding()
    }
}
