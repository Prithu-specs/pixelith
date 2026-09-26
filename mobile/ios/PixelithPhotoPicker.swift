// SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
// Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
import PhotosUI
import SwiftUI

/// Uses PHPicker: Pixelith receives only the items the user explicitly selects.
struct PixelithPhotoPicker: UIViewControllerRepresentable {
    let onSelection: ([PHPickerResult]) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onSelection) }
    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(photoLibrary: .shared())
        config.filter = .any(of: [.images, .videos])
        config.selectionLimit = 4
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: PHPickerViewController, context: Context) {}

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let onSelection: ([PHPickerResult]) -> Void
        init(_ callback: @escaping ([PHPickerResult]) -> Void) { onSelection = callback }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            onSelection(results)
        }
    }
}
