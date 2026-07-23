import SwiftUI

struct AuthView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var email = ""
    @State private var password = ""
    @State private var isSignUp = false
    @State private var showPassword = false

    var body: some View {
        ZStack {
            DesignSystem.Colors.base.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 32) {
                    Spacer(minLength: 60)

                    // Branding
                    VStack(spacing: 12) {
                        ZStack {
                            Circle()
                                .fill(DesignSystem.Colors.accent.opacity(0.15))
                                .frame(width: 88, height: 88)

                            Image(systemName: "sparkles")
                                .font(.system(size: 40, weight: .light))
                                .foregroundStyle(DesignSystem.Colors.accent)
                        }
                        .accessibilityHidden(true)

                        Text("Archon")
                            .font(.system(.largeTitle, design: .rounded).weight(.bold))
                            .foregroundStyle(DesignSystem.Colors.textPrimary)

                        Text("Build apps with AI")
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundStyle(DesignSystem.Colors.textSecondary)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Archon. Build apps with AI.")

                    // Auth Form
                    VStack(spacing: 16) {
                        // Email field
                        HStack {
                            Image(systemName: "envelope")
                                .foregroundStyle(DesignSystem.Colors.textMuted)
                                .frame(width: 20)

                            TextField("Email", text: $email)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                        }
                        .padding(14)
                        .background(DesignSystem.Colors.elevated)
                        .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))

                        // Password field
                        HStack {
                            Image(systemName: "lock")
                                .foregroundStyle(DesignSystem.Colors.textMuted)
                                .frame(width: 20)

                            if showPassword {
                                TextField("Password", text: $password)
                                    .textContentType(isSignUp ? .newPassword : .password)
                            } else {
                                SecureField("Password", text: $password)
                                    .textContentType(isSignUp ? .newPassword : .password)
                            }

                            Button {
                                showPassword.toggle()
                            } label: {
                                Image(systemName: showPassword ? "eye.slash" : "eye")
                                    .foregroundStyle(DesignSystem.Colors.textMuted)
                            }
                            .dsTouchTarget()
                        }
                        .padding(14)
                        .background(DesignSystem.Colors.elevated)
                        .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                    }
                    .padding(.horizontal, 32)

                    // Error display
                    if let error = authManager.authError {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(DesignSystem.Colors.danger)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)
                            .accessibilityLabel("Authentication error: \(error)")
                    }

                    // Sign in/up buttons
                    VStack(spacing: 12) {
                        Button {
                            Task {
                                if isSignUp {
                                    await authManager.signUpWithEmail(email, password: password)
                                } else {
                                    await authManager.signInWithEmail(email, password: password)
                                }
                            }
                        } label: {
                            if authManager.isLoading {
                                ProgressView()
                                    .frame(maxWidth: .infinity, minHeight: 50)
                            } else {
                                Text(isSignUp ? "Create Account" : "Sign In")
                                    .font(.headline)
                                    .foregroundStyle(DesignSystem.Colors.base)
                                    .frame(maxWidth: .infinity, minHeight: 50)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(DesignSystem.Colors.accent)
                        .disabled(authManager.isLoading || email.isEmpty || password.isEmpty)
                        .dsTouchTarget()

                        // Divider
                        HStack {
                            Rectangle().fill(DesignSystem.Colors.surfaceBorder).frame(height: 1)
                            Text("or").font(.caption).foregroundStyle(DesignSystem.Colors.textMuted)
                            Rectangle().fill(DesignSystem.Colors.surfaceBorder).frame(height: 1)
                        }
                        .padding(.horizontal, 16)

                        // Apple Sign In
                        Button {
                            authManager.startAppleSignIn()
                        } label: {
                            HStack {
                                Image(systemName: "apple.logo")
                                    .font(.title3)
                                Text("Sign in with Apple")
                                    .font(.headline)
                            }
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity, minHeight: 50)
                        }
                        .background(Color.black)
                        .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.md, style: .continuous))
                        .dsTouchTarget()
                    }
                    .padding(.horizontal, 32)

                    // Toggle sign in/up
                    Button {
                        isSignUp.toggle()
                    } label: {
                        Text(isSignUp ? "Already have an account? Sign In" : "Don't have an account? Create one")
                            .font(.subheadline)
                            .foregroundStyle(DesignSystem.Colors.accent)
                    }
                    .dsTouchTarget()

                    Spacer(minLength: 40)
                }
            }
        }
        .preferredColorScheme(.dark)
        .dynamicTypeSize(.xSmall ... .accessibility3)
        .animation(.easeInOut(duration: 0.2), value: isSignUp)
    }
}

#Preview {
    AuthView()
        .environmentObject(AuthManager.shared)
}
