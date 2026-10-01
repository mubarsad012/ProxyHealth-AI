// Capture cache cleanup (D-22 "saving is opt-in", PRODUCT_SPEC S17 "Delete everything"). Native
// capture modules write full-size files into the app cache and never delete them:
//   expo-camera `takePictureAsync`         → <cache>/Camera         (ExpoCameraUtils.swift, ResolveTakenPicture.kt)
//   expo-image-manipulator `saveAsync`     → <cache>/ImageManipulator (ImageManipulatorUtils.swift, FileUtils.kt)
//   expo-image-picker results              → <cache>/ImagePicker    (MediaHandler.swift, ImagePickerConstants.kt)
//   expo-document-picker `copyToCacheDirectory` → <cache>/DocumentPicker
//   expo-print `printToFileAsync` (Android) → <cache>/Print
// Pictures of papers the user never saved (including originals from before "Hide parts") would stay
// on the phone. `purgeCaptureCache()` removes those folders: on every cold start (the scan session
// is memory-only, so nothing still needs them) and in "Delete everything". The vault's own copies
// live under `Paths.document/vault/` and are untouched.

import { Directory, Paths } from 'expo-file-system';

export const CAPTURE_CACHE_DIRS: readonly string[] = ['Camera', 'ImageManipulator', 'ImagePicker', 'DocumentPicker', 'Print'];

export async function purgeCaptureCache(): Promise<void> {
  for (const name of CAPTURE_CACHE_DIRS) {
    try {
      const dir = new Directory(Paths.cache, name);
      if (dir.exists) dir.delete();
    } catch {
      // already gone / not created on this platform
    }
  }
}
