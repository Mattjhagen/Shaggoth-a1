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
                        .transition(.asymmetric(
                            insertion: .move(edge: .bottom).combined(with: .opacity),
                            removal: .opacity
                        ))
                }
            }
        }
        .animation(DesignSystem.Animation.fluid, value: events.count)
    }

    @ViewBuilder
    private func timelineRow(event: TaskEvent, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 14) {
            // Timeline line and dot
            VStack(spacing: 0) {
                ZStack {
                    if isLast && event.type.isLive {
                        PulsingHalo(color: dotColor(for: event.type))
                            .frame(width: 30, height: 30)
                    }

                    Image(systemName: event.type.icon)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(dotColor(for: event.type))
                        .frame(width: 30, height: 30)
                        .background(
                            Circle().fill(
                                RadialGradient(
                                    colors: [
                                        dotColor(for: event.type).opacity(0.30),
                                        dotColor(for: event.type).opacity(0.08)
                                    ],
                                    center: .center,
                                    startRadius: 2,
                                    endRadius: 16
                                )
                            )
                        )
                        .overlay(
                            Circle().strokeBorder(
                                dotColor(for: event.type).opacity(0.35),
                                lineWidth: 1
                            )
                        )
                        .dsGlow(
                            dotColor(for: event.type),
                            radius: isLast ? 10 : 0,
                            opacity: isLast ? 0.4 : 0
                        )
                }
                .padding(.top, 2)

                if !isLast {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(
                            LinearGradient(
                                colors: [
                                    dotColor(for: event.type).opacity(0.45),
                                    DesignSystem.Colors.surfaceBorder.opacity(0.6)
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .frame(width: 2)
                        .frame(minHeight: 20)
                }
            }

            // Content
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(event.type.displayCategory)
                        .font(.system(.caption, design: .rounded).weight(.semibold))
                        .foregroundStyle(dotColor(for: event.type))

                    Spacer()

                    Text(event.timestamp, style: .relative)
                        .font(.system(.caption2, design: .rounded))
                        .foregroundStyle(DesignSystem.Colors.textMuted)
                }

                Text(friendlySummary(for: event))
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundStyle(DesignSystem.Colors.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                // Advanced Terminal view for raw outputs and metadata
                if (event.metadata != nil && event.metadata?.isEmpty == false) || event.content.count > 100 {
                     TerminalPullOut(rawOutput: event.content, metadata: event.metadata)
                         .padding(.top, 4)
                }
            }
            .padding(.bottom, 16)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(event.type.displayCategory): \(friendlySummary(for: event)). \(event.timestamp.formatted(date: .abbreviated, time: .shortened)).")
    }

    private func friendlySummary(for event: TaskEvent) -> String {
        // If content is very long, it's likely a raw prompt/response. Show a short summary instead.
        if event.content.count > 100 {
            switch event.type {
            case .modelCall: return "Generating response..."
            case .toolCall: return "Running command..."
            case .fileEdit: return "Writing code to files..."
            case .error: return "An error occurred during execution."
            default: return "Processing task..."
            }
        }
        return event.content
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

private extension TaskEvent.EventType {
    /// Events that represent work still in flight get a breathing pulse.
    var isLive: Bool {
        switch self {
        case .completion, .error: return false
        default: return true
        }
    }
}

/// Expanding ring that radiates from the newest live event's dot.
private struct PulsingHalo: View {
    let color: Color
    @State private var expanded = false

    var body: some View {
        Circle()
            .stroke(color.opacity(expanded ? 0 : 0.5), lineWidth: 2)
            .scaleEffect(expanded ? 1.9 : 1)
            .onAppear {
                withAnimation(.easeOut(duration: 1.6).repeatForever(autoreverses: false)) {
                    expanded = true
                }
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
