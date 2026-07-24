import Foundation
import UIKit
import UserNotifications

/// Lets the user know a build finished: a success haptic when the app is
/// open, and a banner notification when it's in the background.
@MainActor
enum BuildNotifier {
    /// Asks for notification permission the first time a build starts, so
    /// the request appears in a moment where the value is obvious.
    static func requestPermissionIfNeeded() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus == .notDetermined else { return }
            center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }
    }

    static func notifyBuildFinished(projectName: String?) {
        UINotificationFeedbackGenerator().notificationOccurred(.success)

        let content = UNMutableNotificationContent()
        content.title = "Your app is ready 🎉"
        content.body = projectName.map { "\"\($0)\" just finished building. Come take a look!" }
            ?? "Your build just finished. Come take a look!"
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "build-complete-\(UUID().uuidString)",
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }
}
