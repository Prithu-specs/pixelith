// SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
// Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
package solutions.pgatech.pixelith

import androidx.activity.ComponentActivity
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickMultipleVisualMedia
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia

/** Android Photo Picker grants access only to the selected items. */
class PixelithMediaPicker(activity: ComponentActivity, onPicked: (List<android.net.Uri>) -> Unit) {
    private val launcher = activity.registerForActivityResult(PickMultipleVisualMedia(4), onPicked)
    fun open() = launcher.launch(PickVisualMediaRequest(PickVisualMedia.ImageAndVideo))
}
