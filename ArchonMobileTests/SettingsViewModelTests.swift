import XCTest
@testable import ArchonMobile

@MainActor
final class SettingsViewModelTests: XCTestCase {
    
    func testAppearanceDisplayNames() {
        XCTAssertEqual(SettingsViewModel.AppearanceMode.light.displayName, "Light")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.dark.displayName, "Dark")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.glass.displayName, "Glass")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.system.displayName, "System")
    }
    
    func testAppearanceIcons() {
        XCTAssertEqual(SettingsViewModel.AppearanceMode.light.icon, "sun.max.fill")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.dark.icon, "moon.fill")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.glass.icon, "circle.hexagongrid.fill")
        XCTAssertEqual(SettingsViewModel.AppearanceMode.system.icon, "circle.lefthalf.filled")
    }

    func testDefaultAppearance() {
        // Just verify the default initialization doesn't crash and reads correctly
        let vm = SettingsViewModel()
        XCTAssertEqual(vm.appearance.rawValue, UserDefaults.standard.string(forKey: "appearance") ?? SettingsViewModel.AppearanceMode.dark.rawValue)
    }
    
    func testSaveAppearance() {
        let vm = SettingsViewModel()
        vm.appearance = .glass
        // Note: the view model updates UserDefaults in onChange in the View, not automatically on property set.
        // We're just making sure it sets the state properly.
        XCTAssertEqual(vm.appearance, .glass)
    }
}
