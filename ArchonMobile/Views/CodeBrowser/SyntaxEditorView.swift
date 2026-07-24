import SwiftUI
import UIKit

struct SyntaxEditorView: UIViewRepresentable {
    enum Language {
        case javascript, typescript, html, css, swift, json, plaintext
    }

    @Binding var text: String
    var language: Language = .swift
    var isEditing: Bool = false

    func makeUIView(context: Context) -> CodeTextView {
        let editor = CodeTextView()
        editor.delegate = context.coordinator
        editor.language = language
        editor.text = text
        editor.isEditable = isEditing
        editor.applyHighlighting()
        return editor
    }

    func updateUIView(_ uiView: CodeTextView, context: Context) {
        uiView.language = language
        uiView.isEditable = isEditing

        guard uiView.text != text else { return }

        let selection = uiView.selectedRange
        uiView.text = text
        uiView.applyHighlighting()
        uiView.selectedRange = NSRange(
            location: min(selection.location, (uiView.text as NSString).length),
            length: 0
        )
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    final class Coordinator: NSObject, UITextViewDelegate {
        @Binding private var text: String

        init(text: Binding<String>) {
            _text = text
        }

        func textViewDidChange(_ textView: UITextView) {
            text = textView.text
            (textView as? CodeTextView)?.applyHighlighting()
        }

        func textView(
            _ textView: UITextView,
            shouldChangeTextIn range: NSRange,
            replacementText replacementText: String
        ) -> Bool {
            guard replacementText == "\n",
                  let editor = textView as? CodeTextView
            else {
                return true
            }

            let source = textView.text as NSString
            let prefix = source.substring(to: range.location)
            let currentLine = prefix.components(separatedBy: .newlines).last ?? ""

            let indentation = currentLine.prefix { $0 == " " || $0 == "\t" }
            let trimmedLine = currentLine.trimmingCharacters(in: .whitespaces)

            let addsIndent = trimmedLine.hasSuffix("{")
                || trimmedLine.hasSuffix("[")
                || trimmedLine.hasSuffix("(")
                || trimmedLine.hasSuffix(":")

            let extraIndent = addsIndent ? "    " : ""
            let insertion = "\n" + indentation + extraIndent

            textView.textStorage.replaceCharacters(in: range, with: insertion)
            textView.selectedRange = NSRange(location: range.location + (insertion as NSString).length, length: 0)

            editor.applyHighlighting()
            return false
        }
    }
}

final class CodeTextView: UITextView {
    var language: SyntaxEditorView.Language = .swift {
        didSet { applyHighlighting() }
    }

    private let gutterWidth: CGFloat = 48
    private let codeFont = UIFont.monospacedSystemFont(ofSize: 13, weight: .regular)

    init() {
        super.init(frame: .zero, textContainer: nil)

        backgroundColor = DesignSystem.Colors.UIKitColors.base
        textColor = DesignSystem.Colors.UIKitColors.text
        tintColor = DesignSystem.Colors.UIKitColors.accent
        font = codeFont
        autocorrectionType = .no
        autocapitalizationType = .none
        smartDashesType = .no
        smartQuotesType = .no
        smartInsertDeleteType = .no
        keyboardDismissMode = .interactive
        alwaysBounceVertical = true

        textContainerInset = UIEdgeInsets(top: 14, left: gutterWidth + 10, bottom: 14, right: 14)
        textContainer.lineFragmentPadding = 0
        layoutManager.allowsNonContiguousLayout = false
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func draw(_ rect: CGRect) {
        super.draw(rect)

        guard let context = UIGraphicsGetCurrentContext() else { return }

        let gutterRect = CGRect(x: 0, y: 0, width: gutterWidth, height: bounds.height)
        context.setFillColor(DesignSystem.Colors.UIKitColors.surface.cgColor)
        context.fill(gutterRect)

        context.setStrokeColor(DesignSystem.Colors.UIKitColors.border.cgColor)
        context.setLineWidth(1)
        context.move(to: CGPoint(x: gutterWidth, y: 0))
        context.addLine(to: CGPoint(x: gutterWidth, y: bounds.height))
        context.strokePath()

        drawLineNumbers()
    }

    private func drawLineNumbers() {
        let visibleRect = CGRect(x: contentOffset.x, y: contentOffset.y, width: bounds.width, height: bounds.height)
        let glyphRange = layoutManager.glyphRange(forBoundingRect: visibleRect, in: textContainer)

        var lineNumber = 1
        let visibleCharacterRange = layoutManager.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil)
        let precedingText = (text as NSString).substring(to: visibleCharacterRange.location)
        lineNumber += precedingText.filter { $0 == "\n" }.count

        var glyphIndex = glyphRange.location

        let attributes: [NSAttributedString.Key: Any] = [
            .font: UIFont.monospacedDigitSystemFont(ofSize: 11, weight: .regular),
            .foregroundColor: DesignSystem.Colors.UIKitColors.textMuted
        ]

        while glyphIndex < NSMaxRange(glyphRange) {
            var lineRange = NSRange()
            let lineRect = layoutManager.lineFragmentRect(forGlyphAt: glyphIndex, effectiveRange: &lineRange)

            let number = "\(lineNumber)" as NSString
            let size = number.size(withAttributes: attributes)

            let point = CGPoint(
                x: gutterWidth - size.width - 8,
                y: lineRect.minY + textContainerInset.top
            )

            number.draw(at: point, withAttributes: attributes)

            glyphIndex = NSMaxRange(lineRange)
            lineNumber += 1
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        setNeedsDisplay()
    }

    func applyHighlighting() {
        let selection = selectedRange
        let source = text ?? ""
        let fullRange = NSRange(location: 0, length: (source as NSString).length)

        let baseAttributes: [NSAttributedString.Key: Any] = [
            .font: codeFont,
            .foregroundColor: DesignSystem.Colors.UIKitColors.text
        ]

        textStorage.beginEditing()
        textStorage.setAttributes(baseAttributes, range: fullRange)

        switch language {
        case .javascript, .typescript:
            highlightJavaScript(source, range: fullRange)
        case .html:
            highlightHTML(source, range: fullRange)
        case .css:
            highlightCSS(source, range: fullRange)
        case .swift:
            highlightSwift(source, range: fullRange)
        case .json:
            highlightJSON(source, range: fullRange)
        case .plaintext:
            break
        }

        textStorage.endEditing()
        selectedRange = selection
        setNeedsDisplay()
    }

    // MARK: - Language Highlighters

    private func highlightJavaScript(_ source: String, range: NSRange) {
        applyRegex(
            #"\b(const|let|var|function|return|if|else|for|while|async|await|import|from|export|class|new|throw|try|catch|switch|case|default|typeof|instanceof|void|delete|in|of|yield)\b"#,
            in: source,
            color: DesignSystem.Colors.UIKitColors.keyword
        )
        applyRegex(#""(?:\\.|[^"])*"|'(?:\\.|[^'])*'|`(?:\\.|[^`])*`"#, in: source, color: DesignSystem.Colors.UIKitColors.string)
        applyRegex(#"//.*|/\*[\s\S]*?\*/"#, in: source, color: DesignSystem.Colors.UIKitColors.comment)
        applyRegex(#"\b\d+(\.\d+)?\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
        applyRegex(#"\b(true|false|null|undefined|NaN|Infinity)\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
    }

    private func highlightSwift(_ source: String, range: NSRange) {
        applyRegex(
            #"\b(import|let|var|func|return|if|else|guard|for|while|switch|case|struct|class|enum|protocol|extension|async|await|throws|try|private|public|internal|some|any|where|print|self|super|init|deinit|static|final|override|didSet|willSet|lazy|weak|unowned|inout|indirect|typealias|associatedtype|precedencegroup|operator|subscript|associatedValue|associatedValues|caseIterable)\b"#,
            in: source,
            color: DesignSystem.Colors.UIKitColors.keyword
        )
        applyRegex(#""(?:\\.|[^"])*""#, in: source, color: DesignSystem.Colors.UIKitColors.string)
        applyRegex(#"//.*|/\*[\s\S]*?\*/"#, in: source, color: DesignSystem.Colors.UIKitColors.comment)
        applyRegex(#"\b(true|false|nil)\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
        applyRegex(#"\b\d+(\.\d+)?\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
    }

    private func highlightHTML(_ source: String, range: NSRange) {
        applyRegex(#"</?[A-Za-z][^>]*>"#, in: source, color: DesignSystem.Colors.UIKitColors.keyword)
        applyRegex(#"\b[A-Za-z\-]+(?==)"#, in: source, color: DesignSystem.Colors.UIKitColors.attribute)
        applyRegex(#""[^"]*"|'[^']*'"#, in: source, color: DesignSystem.Colors.UIKitColors.string)
        applyRegex(#"<!--[\s\S]*?-->"#, in: source, color: DesignSystem.Colors.UIKitColors.comment)
    }

    private func highlightCSS(_ source: String, range: NSRange) {
        applyRegex(#"\.[a-zA-Z][\w-]*"#, in: source, color: DesignSystem.Colors.UIKitColors.attribute)
        applyRegex(#"#[0-9a-fA-F]{3,8}\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
        applyRegex(#":\b[a-zA-Z-]+(?=\s*[;{])"#, in: source, color: DesignSystem.Colors.UIKitColors.keyword)
        applyRegex(#""[^"]*"|'[^']*'"#, in: source, color: DesignSystem.Colors.UIKitColors.string)
        applyRegex(#"//.*|/\*[\s\S]*?\*/"#, in: source, color: DesignSystem.Colors.UIKitColors.comment)
        applyRegex(#"\b\d+(\.\d+)?(px|em|rem|%|vh|vw|s|ms)\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
    }

    private func highlightJSON(_ source: String, range: NSRange) {
        applyRegex(#""[^"]*"(?=\s*:)"#, in: source, color: DesignSystem.Colors.UIKitColors.keyword)
        applyRegex(#"\b\d+(\.\d+)?\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
        applyRegex(#"\b(true|false|null)\b"#, in: source, color: DesignSystem.Colors.UIKitColors.number)
        applyRegex(#""(?:\\.|[^"])*""#, in: source, color: DesignSystem.Colors.UIKitColors.string)
    }

    // MARK: - Regex Helper

    private func applyRegex(_ pattern: String, in source: String, color: UIColor) {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return }
        let range = NSRange(location: 0, length: (source as NSString).length)

        regex.enumerateMatches(in: source, range: range) { match, _, _ in
            guard let match = match else { return }
            self.textStorage.addAttribute(.foregroundColor, value: color, range: match.range)
        }
    }
}

// MARK: - UIKit Colors

extension DesignSystem.Colors {
    enum UIKitColors {
        static let base      = adaptive(light: 0xFFFFFF, dark: 0x0A0A14)
        static let surface   = adaptive(light: 0xF1F3F8, dark: 0x14142A)
        static let border    = adaptive(light: 0xD6D9E6, dark: 0x2A2A50)
        static let text      = adaptive(light: 0x171724, dark: 0xEEEEF8)
        static let textMuted = adaptive(light: 0x6D7084, dark: 0x505070)
        static let accent    = adaptive(light: 0x007F73, dark: 0x00E8CA)
        static let keyword   = adaptive(light: 0xA626A4, dark: 0xFF79C6)
        static let string    = adaptive(light: 0x508000, dark: 0xF1FA8C)
        static let comment   = adaptive(light: 0x6A737D, dark: 0x6272A4)
        static let number    = adaptive(light: 0x7A3E9D, dark: 0xBD93F9)
        static let attribute = adaptive(light: 0x005CC5, dark: 0x8BE9FD)

        private static func adaptive(light: UInt32, dark: UInt32) -> UIColor {
            UIColor { traits in
                UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
            }
        }
    }
}
