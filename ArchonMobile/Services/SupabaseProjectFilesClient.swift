import Foundation
import Supabase

struct CloudProjectFile: Identifiable {
    let id: UUID
    let path: String
    let content: String
    let mimeType: String
    let updatedAt: Date
}

protocol ProjectFilesClientProtocol {
    func fetchFiles(projectId: String) async throws -> [CloudProjectFile]
    func createStarterFiles(projectId: String) async throws -> [CloudProjectFile]
    func updateFile(id: UUID, content: String) async throws -> CloudProjectFile
    func upsertGeneratedFiles(_ files: [GeneratedProjectFile], projectId: String) async throws
}

final class SupabaseProjectFilesClient: ProjectFilesClientProtocol {
    private let client: SupabaseClient

    init(client: SupabaseClient = SupabaseClientManager.shared.client) {
        self.client = client
    }

    func fetchFiles(projectId: String) async throws -> [CloudProjectFile] {
        let rows: [ProjectFileRow] = try await client
            .from("project_files")
            .select()
            .eq("project_id", value: projectId)
            .order("path")
            .execute()
            .value

        return rows.map(\.file)
    }

    func createStarterFiles(projectId: String) async throws -> [CloudProjectFile] {
        guard
            let projectUUID = UUID(uuidString: projectId),
            let user = client.auth.currentUser
        else {
            throw APIError(message: "A signed-in user and valid project are required.", code: 401)
        }

        let payloads = StarterFile.all.map {
            ProjectFileInsertPayload(
                projectId: projectUUID,
                userId: user.id,
                path: $0.path,
                content: $0.content,
                mimeType: $0.mimeType
            )
        }

        let rows: [ProjectFileRow] = try await client
            .from("project_files")
            .insert(payloads)
            .select()
            .execute()
            .value

        return rows.map(\.file).sorted { $0.path < $1.path }
    }

    func updateFile(id: UUID, content: String) async throws -> CloudProjectFile {
        let payload = ProjectFileUpdatePayload(content: content, updatedAt: Date())

        let row: ProjectFileRow = try await client
            .from("project_files")
            .update(payload)
            .eq("id", value: id)
            .select()
            .single()
            .execute()
            .value

        return row.file
    }

    func upsertGeneratedFiles(_ files: [GeneratedProjectFile], projectId: String) async throws {
        guard
            !files.isEmpty,
            let projectUUID = UUID(uuidString: projectId),
            let user = client.auth.currentUser
        else { return }

        let payloads = files.map {
            ProjectFileInsertPayload(
                projectId: projectUUID,
                userId: user.id,
                path: $0.path,
                content: $0.content,
                mimeType: $0.mimeType
            )
        }

        try await client
            .from("project_files")
            .upsert(payloads, onConflict: "project_id,path")
            .execute()
    }
}

private struct ProjectFileRow: Decodable {
    let id: UUID
    let path: String
    let content: String
    let mimeType: String
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case path
        case content
        case mimeType = "mime_type"
        case updatedAt = "updated_at"
    }

    var file: CloudProjectFile {
        CloudProjectFile(
            id: id,
            path: path,
            content: content,
            mimeType: mimeType,
            updatedAt: updatedAt
        )
    }
}

private struct ProjectFileInsertPayload: Encodable {
    let projectId: UUID
    let userId: UUID
    let path: String
    let content: String
    let mimeType: String

    enum CodingKeys: String, CodingKey {
        case projectId = "project_id"
        case userId = "user_id"
        case path
        case content
        case mimeType = "mime_type"
    }
}

private struct ProjectFileUpdatePayload: Encodable {
    let content: String
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case content
        case updatedAt = "updated_at"
    }
}

private struct StarterFile {
    let path: String
    let content: String
    let mimeType: String

    static let all = [
        StarterFile(
            path: "index.html",
            content: """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>Archon Project</title>
              <link rel="stylesheet" href="style.css">
            </head>
            <body>
              <main>
                <p class="eyebrow">BUILT WITH ARCHON</p>
                <h1>Your new project is ready.</h1>
                <p>Edit these cloud-backed files and preview your work.</p>
                <button id="action">Try it</button>
              </main>
              <script src="app.js"></script>
            </body>
            </html>
            """,
            mimeType: "text/html"
        ),
        StarterFile(
            path: "style.css",
            content: """
            :root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
            * { box-sizing: border-box; }
            body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #080b14; color: #f7f8ff; }
            main { width: min(680px, calc(100% - 40px)); padding: 48px; border: 1px solid #27304a; border-radius: 28px; background: #111629; }
            .eyebrow { color: #8ca5ff; font-size: 12px; font-weight: 800; letter-spacing: .16em; }
            h1 { margin: 12px 0; font-size: clamp(38px, 8vw, 72px); line-height: .96; }
            p { color: #aeb7d2; line-height: 1.6; }
            button { margin-top: 18px; padding: 12px 18px; border: 0; border-radius: 12px; background: #8ca5ff; color: #080b14; font-weight: 800; }
            """,
            mimeType: "text/css"
        ),
        StarterFile(
            path: "app.js",
            content: """
            document.querySelector('#action')?.addEventListener('click', () => {
              document.querySelector('h1').textContent = 'It works.';
            });
            """,
            mimeType: "text/javascript"
        )
    ]
}
