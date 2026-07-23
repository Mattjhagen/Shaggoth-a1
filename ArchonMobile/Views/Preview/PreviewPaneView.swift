import SwiftUI
import WebKit

struct PreviewPaneView: UIViewRepresentable {
    var htmlContent: String

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .systemBackground
        webView.scrollView.backgroundColor = .systemBackground
        webView.navigationDelegate = context.coordinator
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        uiView.loadHTMLString(htmlContent, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            // Preview load failed — graceful fallback
        }
    }
}

// MARK: - Full Preview Screen

struct FullPreviewScreen: View {
    let htmlContent: String
    let projectName: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                DesignSystem.Colors.base.ignoresSafeArea()

                PreviewPaneView(htmlContent: htmlContent)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .padding()
            }
            .navigationTitle("Preview: \(projectName)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .dsTouchTarget()
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}

#Preview {
    FullPreviewScreen(
        htmlContent: """
        <!DOCTYPE html>
        <html>
        <head><style>body { font-family: sans-serif; text-align: center; padding: 50px; background: #1a1a2e; color: white; }</style></head>
        <body><h1>Hello from Archon!</h1><p>Your app preview appears here.</p></body>
        </html>
        """,
        projectName: "My App"
    )
}
