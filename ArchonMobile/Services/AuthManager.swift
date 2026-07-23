import Foundation
import Supabase
import AuthenticationServices

@MainActor
class AuthManager: NSObject, ObservableObject {
    @Published var isAuthenticated: Bool = false
    @Published var isSessionExpired: Bool = false
    @Published var authError: String?
    @Published var isLoading: Bool = false
    @Published var currentUser: UserProfile?

    static let shared = AuthManager()

    private var authStateTask: Task<Void, Never>?
    private var webAuthSession: ASWebAuthenticationSession?

    struct UserProfile {
        let id: String
        let email: String?
        let displayName: String?
    }

    private override init() {
        super.init()
        startListeningToAuthState()
    }

    private func startListeningToAuthState() {
        authStateTask = Task {
            for await (event, session) in await supabaseClient.auth.authStateChanges {
                self.isAuthenticated = session != nil
                if event == .tokenRefreshed {
                    self.isSessionExpired = false
                }
                if let session {
                    self.currentUser = UserProfile(
                        id: session.user.id.uuidString,
                        email: session.user.email,
                        displayName: session.user.userMetadata["full_name"]?.stringValue
                    )
                } else {
                    self.currentUser = nil
                }
            }
        }
    }

    // MARK: - Email Sign In

    func signInWithEmail(_ email: String, password: String) async {
        isLoading = true
        authError = nil
        defer { isLoading = false }

        do {
            try await supabaseClient.auth.signIn(email: email, password: password)
        } catch {
            self.authError = error.localizedDescription
        }
    }

    func signUpWithEmail(_ email: String, password: String) async {
        isLoading = true
        authError = nil
        defer { isLoading = false }

        do {
            try await supabaseClient.auth.signUp(email: email, password: password)
        } catch {
            self.authError = error.localizedDescription
        }
    }

    // MARK: - Apple Sign In

    func startAppleSignIn() {
        Task {
            do {
                self.authError = nil
                let response = try await supabaseClient.auth.getOAuthSignInURL(
                    provider: .apple,
                    redirectTo: URL(string: "com.archonmobile.auth://auth/callback")
                )

                webAuthSession = ASWebAuthenticationSession(url: response, callbackURLScheme: "com.archonmobile.auth") { [weak self] callbackURL, error in
                    guard let self = self else { return }
                    if let error = error {
                        if (error as NSError).code != ASWebAuthenticationSessionError.canceledLogin.rawValue {
                            DispatchQueue.main.async { self.authError = error.localizedDescription }
                        }
                        return
                    }
                    guard let callbackURL = callbackURL else { return }

                    Task {
                        do {
                            try await supabaseClient.auth.session(from: callbackURL)
                        } catch {
                            self.authError = error.localizedDescription
                        }
                    }
                }

                webAuthSession?.presentationContextProvider = self
                webAuthSession?.start()
            } catch {
                self.authError = error.localizedDescription
            }
        }
    }

    // MARK: - Sign Out

    func signOut() async {
        do {
            try await supabaseClient.auth.signOut()
            currentUser = nil
        } catch {
            authError = error.localizedDescription
        }
    }

    // MARK: - Delete Account

    func deleteAccount() async {
        do {
            // Account deletion requires server-side endpoint
            // For now, sign out and let the user know to contact support
            try await supabaseClient.auth.signOut()
            currentUser = nil
        } catch {
            authError = error.localizedDescription
        }
    }

    deinit {
        authStateTask?.cancel()
    }
}

extension AuthManager: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes
        let windowScene = scenes.first as? UIWindowScene
        return windowScene?.windows.first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
}
