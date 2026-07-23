import Foundation

enum FileType: String, Codable {
    case file
    case folder
}

struct FileNode: Identifiable, Hashable, Codable {
    let id: UUID
    var name: String
    let type: FileType
    var children: [FileNode]?
    var content: String?
    var size: Int64?
    var updatedAt: Date?

    init(id: UUID = UUID(), name: String, type: FileType, children: [FileNode]? = nil, content: String? = nil, size: Int64? = nil, updatedAt: Date? = nil) {
        self.id = id
        self.name = name
        self.type = type
        self.children = children
        self.content = content
        self.size = size
        self.updatedAt = updatedAt
    }

    var isExpandable: Bool { type == .folder }
    var isLeaf: Bool { type == .file }

    private static var saveURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("workspace.json")
    }

    static func save(_ nodes: [FileNode]) {
        if let data = try? JSONEncoder().encode(nodes) {
            try? data.write(to: saveURL)
        }
    }

    static func load() -> [FileNode] {
        if let data = try? Data(contentsOf: saveURL),
           let nodes = try? JSONDecoder().decode([FileNode].self, from: data) {
            return nodes
        }
        return mock()
    }

    static func mock() -> [FileNode] {
        return [
            FileNode(name: "src", type: .folder, children: [
                FileNode(name: "App.swift", type: .file, content: "import SwiftUI\n\n@main\nstruct MyApp: App {\n    var body: some Scene {\n        WindowGroup {\n            ContentView()\n        }\n    }\n}\n"),
                FileNode(name: "ContentView.swift", type: .file, content: "import SwiftUI\n\nstruct ContentView: View {\n    var body: some View {\n        VStack {\n            Image(systemName: \"globe\")\n                .font(.system(size: 64))\n                .foregroundStyle(.blue)\n            Text(\"Hello, World!\")\n                .font(.largeTitle)\n        }\n        .padding()\n    }\n}\n"),
                FileNode(name: "Models.swift", type: .file, content: "import Foundation\n\nstruct Item: Identifiable, Codable {\n    let id: UUID\n    var name: String\n    var isComplete: Bool\n}\n")
            ]),
            FileNode(name: "public", type: .folder, children: [
                FileNode(name: "index.html", type: .file, content: "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>My App</title>\n    <link rel=\"stylesheet\" href=\"style.css\">\n</head>\n<body>\n    <div class=\"container\">\n        <h1>Welcome to My App</h1>\n        <p>Built with Archon</p>\n    </div>\n    <script src=\"app.js\"></script>\n</body>\n</html>\n"),
                FileNode(name: "style.css", type: .file, content: "* {\n    margin: 0;\n    padding: 0;\n    box-sizing: border-box;\n}\n\nbody {\n    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;\n    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);\n    min-height: 100vh;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n}\n\n.container {\n    text-align: center;\n    color: white;\n    padding: 2rem;\n}\n\nh1 {\n    font-size: 2.5rem;\n    margin-bottom: 0.5rem;\n}\n\np {\n    font-size: 1.2rem;\n    opacity: 0.9;\n}\n"),
                FileNode(name: "app.js", type: .file, content: "document.addEventListener('DOMContentLoaded', () => {\n    console.log('App loaded!');\n\n    const h1 = document.querySelector('h1');\n    if (h1) {\n        h1.style.animation = 'fadeIn 0.5s ease-in';\n    }\n});\n")
            ]),
            FileNode(name: "Package.swift", type: .file, content: "// swift-tools-version: 5.9\nimport PackageDescription\n\nlet package = Package(\n    name: \"MyApp\",\n    platforms: [.iOS(.v17)],\n    targets: [\n        .executableTarget(name: \"MyApp\")\n    ]\n)\n"),
            FileNode(name: "README.md", type: .file, content: "# My App\n\nBuilt with Archon AI App Builder\n\n## Features\n\n- Modern SwiftUI interface\n- Cross-platform support\n- Beautiful animations\n")
        ]
    }
}
