import XCTest
@testable import ArchonMobile

final class DecodingTests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .customISO8601
        return decoder
    }

    func testDecodeTaskEventAllKinds() throws {
        let json = """
        [
            {"id": "evt-1", "task_id": "task-1", "sequence": 1, "kind": "planning", "summary": "Starting plan", "created_at": "2024-07-23T12:00:00Z"},
            {"id": "evt-2", "task_id": "task-1", "sequence": 2, "kind": "model_call", "summary": "Calling claude", "created_at": "2024-07-23T12:00:01.123Z"},
            {"id": "evt-3", "task_id": "task-1", "sequence": 3, "kind": "tool_call", "summary": "Using grep", "created_at": "2024-07-23T12:00:02.456789Z"},
            {"id": "evt-4", "task_id": "task-1", "sequence": 4, "kind": "tool_result", "summary": "Found results", "created_at": "2024-07-23T12:00:03.000Z", "metadata": {"token_count": 120, "success": true, "ratio": 0.95, "tags": ["search", "fast"], "nested": {"key": "value"}}},
            {"id": "evt-5", "task_id": "task-1", "sequence": 5, "kind": "verification", "summary": "Verifying", "created_at": "2024-07-23T12:00:04Z"},
            {"id": "evt-6", "task_id": "task-1", "sequence": 6, "kind": "file_edit", "summary": "Editing main.swift", "created_at": "2024-07-23T12:00:05Z"},
            {"id": "evt-7", "task_id": "task-1", "sequence": 7, "kind": "completion", "summary": "Done", "created_at": "2024-07-23T12:00:06Z"},
            {"id": "evt-8", "task_id": "task-1", "sequence": 8, "kind": "blocker", "summary": "Blocked on user", "created_at": "2024-07-23T12:00:07Z"},
            {"id": "evt-9", "task_id": "task-1", "sequence": 9, "kind": "error", "summary": "Error occurred", "created_at": "2024-07-23T12:00:08Z"},
            {"id": "evt-10", "task_id": "task-1", "sequence": 10, "kind": "message", "summary": "Chat message", "created_at": "2024-07-23T12:00:09Z"}
        ]
        """.data(using: .utf8)!

        let events = try makeDecoder().decode([TaskEvent].self, from: json)

        XCTAssertEqual(events.count, 10)
        XCTAssertEqual(events[0].type, .planning)
        XCTAssertEqual(events[1].type, .modelCall)
        XCTAssertEqual(events[2].type, .toolCall)
        XCTAssertEqual(events[3].type, .toolResult)
        XCTAssertEqual(events[4].type, .verification)
        XCTAssertEqual(events[5].type, .fileEdit)
        XCTAssertEqual(events[6].type, .completion)
        XCTAssertEqual(events[7].type, .blocker)
        XCTAssertEqual(events[8].type, .error)
        XCTAssertEqual(events[9].type, .message)

        // Verify fractional timestamps
        let evt2Date = events[1].timestamp
        let expectedTime = 1721736001.123
        XCTAssertEqual(evt2Date.timeIntervalSince1970, expectedTime, accuracy: 0.001)

        // Verify metadata AnyCodable dynamic decoding
        let metadata = events[3].metadata
        XCTAssertNotNil(metadata)
        if let md = metadata {
            XCTAssertEqual(md["token_count"]?.value as? Int, 120)
            XCTAssertEqual(md["success"]?.value as? Bool, true)
            XCTAssertEqual(md["ratio"]?.value as? Double, 0.95)
            let tags = md["tags"]?.value as? [Any]
            XCTAssertEqual(tags?.count, 2)
            XCTAssertEqual(tags?[0] as? String, "search")
            let nested = md["nested"]?.value as? [String: Any]
            XCTAssertEqual(nested?["key"] as? String, "value")
        }
    }

    func testDecodeArchonTask() throws {
        let json = """
        {
            "id": "task-123",
            "title": "Make an app",
            "status": "running",
            "provider": "Anthropic",
            "model": "claude-3-5-sonnet",
            "reasoning_effort": "high",
            "current_step": 10,
            "max_steps": 25,
            "credits_used": 150,
            "credit_limit": 500,
            "project_id": "proj-1",
            "created_at": "2024-07-23T12:00:00.123Z",
            "updated_at": "2024-07-23T12:01:00Z"
        }
        """.data(using: .utf8)!

        let task = try makeDecoder().decode(ArchonTask.self, from: json)

        XCTAssertEqual(task.id, "task-123")
        XCTAssertEqual(task.reasoningEffort, .high)
        XCTAssertEqual(task.creditLimit, 500)
        XCTAssertEqual(task.creditsUsed, 150)
        XCTAssertEqual(task.projectId, "proj-1")
    }

    func testDecodeArchonProject() throws {
        let json = """
        {
            "id": "proj-1",
            "name": "Test Project",
            "description": "A test project",
            "status": "active",
            "created_at": "2024-07-23T12:00:00Z",
            "updated_at": "2024-07-23T12:01:00Z"
        }
        """.data(using: .utf8)!

        let project = try makeDecoder().decode(ArchonProject.self, from: json)

        XCTAssertEqual(project.id, "proj-1")
        XCTAssertEqual(project.name, "Test Project")
        XCTAssertEqual(project.description, "A test project")
        XCTAssertEqual(project.status, .active)
    }

    func testDecodeProviderMetadata() throws {
        let json = """
        {
            "id": "anthropic",
            "name": "Anthropic",
            "models": [
                {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"}
            ],
            "configured": true,
            "requires_key": true
        }
        """.data(using: .utf8)!

        let provider = try makeDecoder().decode(ProviderMetadata.self, from: json)

        XCTAssertEqual(provider.id, "anthropic")
        XCTAssertEqual(provider.models.count, 1)
        XCTAssertEqual(provider.models[0].name, "Claude Sonnet 4")
        XCTAssertEqual(provider.configured, true)
    }

    func testDecodeChatMessage() throws {
        let json = """
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "role": "user",
            "content": "Hello!",
            "timestamp": "2024-07-23T12:00:00Z"
        }
        """.data(using: .utf8)!

        let message = try makeDecoder().decode(ChatMessage.self, from: json)

        XCTAssertEqual(message.role, .user)
        XCTAssertEqual(message.content, "Hello!")
    }
}
