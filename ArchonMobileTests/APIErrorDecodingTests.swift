import XCTest
@testable import ArchonMobile

/// Fixtures shaped like real Rust backend error responses.
final class APIErrorDecodingTests: XCTestCase {

    private func decode(_ json: String) throws -> APIError {
        try JSONDecoder().decode(APIError.self, from: Data(json.utf8))
    }

    func testDecodes400ValidationError() throws {
        let error = try decode(#"{"error": "title must be 1–200 characters"}"#)
        XCTAssertEqual(error.message, "title must be 1–200 characters")
        XCTAssertNil(error.code)
    }

    func testDecodes401AuthError() throws {
        let error = try decode(#"{"error": "missing or invalid authorization token"}"#)
        XCTAssertEqual(error.message, "missing or invalid authorization token")
    }

    func testDecodes404OwnershipSafeError() throws {
        let error = try decode(#"{"error": "task not found"}"#)
        XCTAssertEqual(error.message, "task not found")
    }

    func testDecodes500MessageShape() throws {
        let error = try decode(#"{"message": "internal server error", "code": 500}"#)
        XCTAssertEqual(error.message, "internal server error")
        XCTAssertEqual(error.code, 500)
    }

    func testMessageKeyWinsWhenBothPresent() throws {
        let error = try decode(#"{"message": "primary", "error": "secondary"}"#)
        XCTAssertEqual(error.message, "primary")
    }

    func testRejectsBodyWithNeitherKey() {
        XCTAssertThrowsError(try decode(#"{"detail": "unrelated shape"}"#))
    }

    func testErrorDescriptionIncludesHTTPCode() {
        let error = APIError(message: "task not found", code: 404)
        XCTAssertEqual(error.errorDescription, "task not found (HTTP 404)")
    }

    func testErrorDescriptionWithoutCode() {
        let error = APIError(message: "task not found", code: nil)
        XCTAssertEqual(error.errorDescription, "task not found")
    }

    func testRoundTripEncodesMessageKey() throws {
        let original = APIError(message: "boom", code: 502)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(APIError.self, from: data)
        XCTAssertEqual(decoded.message, "boom")
        XCTAssertEqual(decoded.code, 502)
    }
}
