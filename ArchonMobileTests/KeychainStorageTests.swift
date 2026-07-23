import XCTest
@testable import ArchonMobile

final class KeychainStorageTests: XCTestCase {
    var storage: KeychainSessionStore!

    override func setUp() {
        super.setUp()
        storage = KeychainSessionStore(service: "com.archon.test")
        try? storage.remove(key: "test_key")
    }

    override func tearDown() {
        try? storage.remove(key: "test_key")
        storage = nil
        super.tearDown()
    }

    func testStoreAndRetrieve() throws {
        let testData = "super_secret_refresh_token".data(using: .utf8)!

        try storage.store(key: "test_key", value: testData)

        let retrievedData = try storage.retrieve(key: "test_key")
        XCTAssertNotNil(retrievedData)

        let retrievedString = String(data: retrievedData!, encoding: .utf8)
        XCTAssertEqual(retrievedString, "super_secret_refresh_token")
    }

    func testRemove() throws {
        let testData = "token_to_delete".data(using: .utf8)!

        try storage.store(key: "test_key", value: testData)
        try storage.remove(key: "test_key")

        let retrievedData = try storage.retrieve(key: "test_key")
        XCTAssertNil(retrievedData)
    }

    func testRetrieveNonExistentKey() throws {
        let data = try storage.retrieve(key: "non_existent_key_\(UUID().uuidString)")
        XCTAssertNil(data)
    }

    func testOverwriteExistingKey() throws {
        let first = "first_value".data(using: .utf8)!
        let second = "second_value".data(using: .utf8)!

        try storage.store(key: "test_key", value: first)
        try storage.store(key: "test_key", value: second)

        let retrieved = try storage.retrieve(key: "test_key")
        XCTAssertEqual(String(data: retrieved!, encoding: .utf8), "second_value")
    }
}
