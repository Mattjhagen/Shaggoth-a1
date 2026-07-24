import SwiftUI
import PhotosUI

/// Paperclip button for the chat composers — screenshots and photos ride
/// along with the next message so the AI can actually see them.
struct AttachmentPickerButton: View {
    @ObservedObject var viewModel: BuilderViewModel
    @State private var selection: [PhotosPickerItem] = []

    var body: some View {
        PhotosPicker(
            selection: $selection,
            maxSelectionCount: 3,
            matching: .images
        ) {
            Image(systemName: "paperclip")
                .font(.system(size: 18, weight: .medium))
                .foregroundStyle(
                    viewModel.pendingAttachments.isEmpty
                        ? DesignSystem.Colors.textSecondary
                        : DesignSystem.Colors.accent
                )
        }
        .dsTouchTarget()
        .accessibilityLabel("Attach photos or screenshots")
        .onChange(of: selection) { _, items in
            guard !items.isEmpty else { return }
            selection = []
            Task {
                for item in items {
                    if let data = try? await item.loadTransferable(type: Data.self),
                       let compressed = UIImage(data: data)?.archonAttachmentJPEG() {
                        viewModel.pendingAttachments.append(compressed)
                    }
                }
            }
        }
    }
}

/// Thumbnails of images staged to send with the next message.
struct AttachmentTray: View {
    @ObservedObject var viewModel: BuilderViewModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(Array(viewModel.pendingAttachments.enumerated()), id: \.offset) { index, data in
                    if let image = UIImage(data: data) {
                        ZStack(alignment: .topTrailing) {
                            Image(uiImage: image)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 56, height: 56)
                                .clipShape(RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: DesignSystem.Radius.sm, style: .continuous)
                                        .strokeBorder(DesignSystem.Colors.borderFaint, lineWidth: 1)
                                )

                            Button {
                                guard viewModel.pendingAttachments.indices.contains(index) else { return }
                                viewModel.pendingAttachments.remove(at: index)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 16))
                                    .foregroundStyle(.white, .black.opacity(0.6))
                            }
                            .offset(x: 6, y: -6)
                            .accessibilityLabel("Remove attachment")
                        }
                        .padding(.top, 6)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
        }
        .background(DesignSystem.Colors.surface)
    }
}

extension UIImage {
    /// Downscales to a sensible size for sending to the AI (max 1280pt JPEG),
    /// keeping requests fast and cheap.
    func archonAttachmentJPEG(maxDimension: CGFloat = 1280) -> Data? {
        let largest = max(size.width, size.height)
        guard largest > maxDimension else { return jpegData(compressionQuality: 0.7) }
        let scale = maxDimension / largest
        let newSize = CGSize(width: size.width * scale, height: size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        let resized = renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: newSize))
        }
        return resized.jpegData(compressionQuality: 0.7)
    }
}
