# Archon TestFlight checklist

## Verified release configuration

- Bundle ID: `com.matthagen.archon`
- Apple development team: `WZMXKCK98R`
- Version: `1.0.0`
- Build: `1`
- Minimum iOS version: iOS 17
- Target devices: iPhone
- Sign in with Apple entitlement: enabled
- App icon: 1024 × 1024, opaque
- Privacy manifest: bundled
- Non-exempt encryption: not used
- Production API: `https://archon-ide-pacmac.fly.dev/api`

Increase `CURRENT_PROJECT_VERSION` in `project.yml` before every replacement upload.

## Before archiving

1. Merge the release pull request into `main`.
2. Clone or pull `main`.
3. Copy `Config/Config.example.xcconfig` to `Config/Config.xcconfig`.
4. Add the Supabase publishable key, Supabase URL, and production API URL.
5. Run `xcodegen generate`.
6. Open `ArchonMobile.xcodeproj`.
7. Select the ArchonMobile target, then Signing & Capabilities.
8. Confirm Automatically manage signing, team `WZMXKCK98R`, bundle ID `com.matthagen.archon`, and Sign in with Apple.
9. Run the Release configuration on a physical iPhone and verify sign-in, project sync, AI chat, background return, code editing, profile photo, sign-out, and the account-deletion confirmation screen.

## App Store Connect app record

Create the app with:

- Platform: iOS
- Name: Archon
- Primary language: English (U.S.)
- Bundle ID: `com.matthagen.archon`
- SKU: `archon-ios-001`
- User access: Full Access

Use `https://github.com/Mattjhagen/archon-ios/blob/main/PRIVACY.md` as the privacy policy URL after the release pull request is merged.

## App privacy answers

Declare the following data as linked to the user, used for App Functionality, and not used for tracking:

- Contact Info: Email Address
- Identifiers: User ID
- User Content: Other User Content

Other User Content includes projects, source files, prompts, and AI conversation history. Archon does not sell data and does not use third-party advertising trackers.

## Upload

1. In Xcode, choose Any iOS Device (arm64).
2. Choose Product > Archive.
3. In Organizer, select the new archive.
4. Choose Distribute App > App Store Connect > Upload.
5. Keep automatic signing and symbol upload enabled.
6. Resolve every validation error before uploading.
7. Wait for processing in App Store Connect > TestFlight.
8. Complete export-compliance questions using the app's `ITSAppUsesNonExemptEncryption = NO` declaration.
9. Add the processed build to an internal testing group.

External testers require TestFlight Beta App Review. Internal testers can use the processed build without beta review.

## Manual checks that cannot be automated

- Enable Supabase Auth leaked-password protection when the project plan supports it.
- Confirm the App Store Connect agreements, tax, and banking sections do not show blocking actions.
- Confirm the privacy policy URL is publicly reachable.
- Confirm support contact information and beta review notes are complete.
