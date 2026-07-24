import SwiftUI

/// A particle-collider loading indicator: two glowing particles race around
/// a ring toward each other, collide, and burst into sparks — a nod to the
/// LHC. Replaces plain spinners anywhere a build is in flight.
struct ColliderLoadingView: View {
    var size: CGFloat = 120

    private let period: Double = 2.2
    private let approachShare: Double = 0.62

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, canvasSize in
                let t = timeline.date.timeIntervalSinceReferenceDate
                let phase = t.truncatingRemainder(dividingBy: period) / period
                let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height / 2)
                let radius = min(canvasSize.width, canvasSize.height) / 2 - 6

                drawRing(context: context, center: center, radius: radius)

                if phase < approachShare {
                    drawApproach(
                        context: context,
                        center: center,
                        radius: radius,
                        progress: phase / approachShare
                    )
                } else {
                    drawBurst(
                        context: context,
                        center: center,
                        radius: radius,
                        progress: (phase - approachShare) / (1 - approachShare)
                    )
                }
            }
        }
        .frame(width: size, height: size)
        .accessibilityLabel("Working")
        .accessibilityAddTraits(.updatesFrequently)
    }

    private var beamA: Color { Color(hex: 0x00E8CA) }
    private var beamB: Color { Color(hex: 0x5BA4F5) }

    private func drawRing(context: GraphicsContext, center: CGPoint, radius: CGFloat) {
        let ring = Path(ellipseIn: CGRect(
            x: center.x - radius,
            y: center.y - radius,
            width: radius * 2,
            height: radius * 2
        ))
        context.stroke(ring, with: .color(.white.opacity(0.10)), lineWidth: 1.5)
    }

    /// Both particles sweep along the ring's upper and lower arcs and meet
    /// at the right side, trailing streaks behind them.
    private func drawApproach(
        context: GraphicsContext,
        center: CGPoint,
        radius: CGFloat,
        progress: Double
    ) {
        // Ease-in: the particles accelerate as they approach collision.
        let eased = progress * progress * (3 - 2 * progress)
        let sweep = Double.pi * eased  // 0...π, meeting at angle 0

        for (direction, color) in [(1.0, beamA), (-1.0, beamB)] {
            let angle = Double.pi - sweep  // π → 0
            let signedAngle = direction * angle
            let position = CGPoint(
                x: center.x + radius * cos(signedAngle),
                y: center.y + radius * sin(signedAngle)
            )

            // Trail: fading dots along the path already travelled.
            for i in 1...7 {
                let trailAngle = direction * (angle + Double(i) * 0.11)
                let trailPoint = CGPoint(
                    x: center.x + radius * cos(trailAngle),
                    y: center.y + radius * sin(trailAngle)
                )
                let fade = 1 - Double(i) / 8
                let dotSize = 3.5 * fade
                context.fill(
                    Path(ellipseIn: CGRect(
                        x: trailPoint.x - dotSize / 2,
                        y: trailPoint.y - dotSize / 2,
                        width: dotSize,
                        height: dotSize
                    )),
                    with: .color(color.opacity(0.45 * fade))
                )
            }

            // The particle itself, with a soft glow.
            var glow = context
            glow.addFilter(.blur(radius: 4))
            glow.fill(
                Path(ellipseIn: CGRect(x: position.x - 6, y: position.y - 6, width: 12, height: 12)),
                with: .color(color.opacity(0.8))
            )
            context.fill(
                Path(ellipseIn: CGRect(x: position.x - 3.5, y: position.y - 3.5, width: 7, height: 7)),
                with: .color(.white)
            )
        }
    }

    /// Collision: an expanding shockwave ring and radial sparks that fade.
    private func drawBurst(
        context: GraphicsContext,
        center: CGPoint,
        radius: CGFloat,
        progress: Double
    ) {
        let impact = CGPoint(x: center.x + radius, y: center.y)
        let fade = 1 - progress

        // Shockwave ring.
        let waveRadius = 4 + progress * radius * 0.9
        var wave = context
        wave.addFilter(.blur(radius: 1.5))
        wave.stroke(
            Path(ellipseIn: CGRect(
                x: impact.x - waveRadius,
                y: impact.y - waveRadius,
                width: waveRadius * 2,
                height: waveRadius * 2
            )),
            with: .color(beamA.opacity(0.55 * fade)),
            lineWidth: 2.5 * fade + 0.5
        )

        // Sparks flying outward at fixed angles.
        for i in 0..<10 {
            let sparkAngle = Double(i) / 10 * 2 * Double.pi
            let sparkColor = i.isMultiple(of: 2) ? beamA : beamB
            let distance = 6 + progress * radius * 0.75
            let sparkPoint = CGPoint(
                x: impact.x + distance * cos(sparkAngle),
                y: impact.y + distance * sin(sparkAngle)
            )
            let sparkSize = 3.0 * fade
            guard sparkSize > 0.2 else { continue }
            context.fill(
                Path(ellipseIn: CGRect(
                    x: sparkPoint.x - sparkSize / 2,
                    y: sparkPoint.y - sparkSize / 2,
                    width: sparkSize,
                    height: sparkSize
                )),
                with: .color(sparkColor.opacity(fade))
            )
        }

        // Bright core flash right at impact.
        let coreSize = 10 * fade
        if coreSize > 0.5 {
            var flash = context
            flash.addFilter(.blur(radius: 3))
            flash.fill(
                Path(ellipseIn: CGRect(
                    x: impact.x - coreSize / 2,
                    y: impact.y - coreSize / 2,
                    width: coreSize,
                    height: coreSize
                )),
                with: .color(.white.opacity(fade))
            )
        }
    }
}

#Preview {
    ZStack {
        Color(hex: 0x0A0A14).ignoresSafeArea()
        ColliderLoadingView(size: 140)
    }
}
