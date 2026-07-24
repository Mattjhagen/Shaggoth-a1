import Foundation
import Supabase
import AuthenticationServices

@MainActor
class AuthManager: NSObject, ObservableObject {
    @Published var isAuthenticated: Bool = false
    @Published var isSessionExpired: Bool = false
    @Published var authError: String?
    @Published var authMessage: String?
    @Published var isLoading: Bool = false
    @Published var isDeletingAccount: Bool = false
    @Published var currentUser: UserProfile?

    static let shared = AuthManager()

    private var authStateTask: Task<Void, Never>?

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
            for await (event, session) in supabaseClient.auth.authStateChanges {
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
        authMessage = nil
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
        authMessage = nil
        defer { isLoading = false }

        do {
            let response = try await supabaseClient.auth.signUp(email: email, password: password)
            if case .user = response {
                authMessage = "Check your email and open the confirmation link on this iPhone. Archon will finish signing you in automatically."
            }
        } catch {
            self.authError = error.localizedDescription
        }
    }

    // MARK: - Email Confirmation and OAuth Callback

    /// Completes Supabase's PKCE flow after an email confirmation link opens
    /// Archon. The auth state listener updates the app UI to the signed-in
    /// experience as soon as the session is stored in the keychain.
    func handleAuthCallback(_ url: URL) {
        guard url.scheme?.lowercased() == AppEnvironment.authRedirectURL.scheme else { return }

        isLoading = true
        authError = nil
        authMessage = nil

        Task {
            defer { isLoading = false }
            do {
                _ = try await supabaseClient.auth.session(from: url)
                authMessage = "Email confirmed. You’re signed in."
            } catch {
                authError = "Could not complete sign-in: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Apple Sign In

    func completeAppleSignIn(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .failure(let error):
            if (error as NSError).code != ASAuthorizationError.canceled.rawValue {
                authError = error.localizedDescription
            }
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let idToken = String(data: tokenData, encoding: .utf8) else {
                authError = "Apple did not return a valid sign-in credential."
                return
            }

            isLoading = true
            authError = nil
            authMessage = nil
            Task {
                defer { isLoading = false }
                do {
                    _ = try await supabaseClient.auth.signInWithIdToken(
                        credentials: .init(provider: .apple, idToken: idToken)
                    )

                    if let fullName = credential.fullName?.formatted(), !fullName.isEmpty {
                        _ = try? await supabaseClient.auth.update(
                            user: UserAttributes(data: ["full_name": .string(fullName)])
                        )
                    }
                } catch {
                    authError = error.localizedDescription
                }
            }
        }
    }

    // MARK: - Sign Out

    func signOut() async {
        authError = nil
        authMessage = nil
        do {
            try await supabaseClient.auth.signOut()
            UserDefaults.standard.removeObject(forKey: "builder.pendingAIJob")
            currentUser = nil
        } catch {
            authError = error.localizedDescription
        }
    }

    // MARK: - Delete Account

    func deleteAccount() async {
        guard let userId = currentUser?.id else {
            authError = "You must be signed in to delete your account."
            return
        }

        isDeletingAccount = true
        authError = nil
        defer { isDeletingAccount = false }

        do {
            let response: DeleteAccountResponse = try await supabaseClient.functions.invoke(
                "delete-account",
                options: FunctionInvokeOptions(body: DeleteAccountRequest(confirmation: true))
            )
            guard response.success else {
                throw APIError(message: "The account deletion service did not confirm deletion.")
            }

            await LocalChatMemoryStore.shared.clear(userId: userId)
            try? ProfilePhotoStore.remove(userId: userId)
            UserDefaults.standard.removeObject(forKey: "builder.pendingAIJob")
            try await supabaseClient.auth.signOut()
            isAuthenticated = false
            currentUser = nil
        } catch {
            authError = "Account deletion failed: \(error.localizedDescription)"
        }
    }

    deinit {
        authStateTask?.cancel()
    }
}

private struct DeleteAccountRequest: Encodable {
    let confirmation: Bool
}

private struct DeleteAccountResponse: Decodable {
    let success: Bool
}
