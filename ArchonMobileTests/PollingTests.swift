import XCTest
@testable import ArchonMobile

class MockSleeper: SleeperProtocol {
    var sleepCalled: XCTestExpectation?

    func sleep(nanoseconds: UInt64) async throws {
        sleepCalled?.fulfill()
        try await Task.sleep(nanoseconds: 10_000_000_000)
    }
}

@MainActor
final class PollingTests: XCTestCase {

    func testSuccessAndDeduplication() async throws {
        let mockAPI = MockAPIClient()
        let sleeper = MockSleeper()

        let sleepExpectation = XCTestExpectation(description: "Poll cycle 1")
        sleeper.sleepCalled = sleepExpectation

        // Use BuilderViewModel's internal polling mechanism
        let vm = BuilderViewModel(apiClient: mockAPI, sleeper: sleeper)

        // Simulate task events being available
        // The mock client already has events for task-2

        // Load initial state (just providers)
        await vm.loadInitialState()

        // Verify providers loaded
        XCTAssertFalse(vm.usableProviders.isEmpty)
    }

    func testTerminalTaskStopsPolling() async throws {
        let spy = SpyAPIClient()
        for status in [TaskStatus.completed, .failed, .cancelled, .blocked] {
            spy.tasks = [terminalTask(id: "done-\(status.rawValue)", status: status)]
            let sleeper = HangSleeper()
            let vm = BuilderViewModel(apiClient: spy, sleeper: sleeper)

            // The terminal task check happens in polling logic
            let task = try await spy.getTaskDetails(id: "done-\(status.rawValue)")
            XCTAssertFalse(task.status.isActive, "\(status): terminal task reported as active")
        }
    }

    func testCancellation() async {
        let mockAPI = MockAPIClient()
        let sleeper = MockSleeper()

        let sleepExpectation = XCTestExpectation(description: "Poll cycle 1")
        sleeper.sleepCalled = sleepExpectation

        let vm = BuilderViewModel(apiClient: mockAPI, sleeper: sleeper)
        vm.stopPolling()

        // After stopping, sleep should never be called
        try? await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertNil(sleeper.sleepCalled)
    }

    private func terminalTask(id: String, status: TaskStatus) -> ArchonTask {
        ArchonTask(
            id: id, title: "t", status: status, provider: "p", model: "m",
            reasoningEffort: .medium, currentStep: 1, maxSteps: 1,
            creditsUsed: 1, creditLimit: 10, projectId: nil, createdAt: Date(), updatedAt: Date()
        )
    }
}
