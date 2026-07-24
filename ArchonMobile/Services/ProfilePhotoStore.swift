import Foundation

enum ProfilePhotoStore {
    private static func fileURL(userId: String?) -> URL? {
        guard let userId, !userId.isEmpty else { return nil }
        let safeUserId = userId.replacingOccurrences(
            of: "[^A-Za-z0-9-]",
            with: "_",
            options: .regularExpression
        )
        return FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first?
            .appendingPathComponent("Archon", isDirectory: true)
            .appendingPathComponent("Profiles", isDirectory: true)
            .appendingPathComponent("\(safeUserId).jpg")
    }

    static func load(userId: String?) -> Data? {
        guard let fileURL = fileURL(userId: userId) else { return nil }
        return try? Data(contentsOf: fileURL)
    }

    static func save(_ data: Data, userId: String?) throws {
        guard var fileURL = fileURL(userId: userId) else {
            throw CocoaError(.fileNoSuchFile)
        }
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: fileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        var resourceValues = URLResourceValues()
        resourceValues.isExcludedFromBackup = true
        try? fileURL.setResourceValues(resourceValues)
    }

    static func remove(userId: String?) throws {
        guard let fileURL = fileURL(userId: userId),
              FileManager.default.fileExists(atPath: fileURL.path) else { return }
        try FileManager.default.removeItem(at: fileURL)
    }
}
