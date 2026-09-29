// Gesture-safe pickers (BUILD_PLAN §1.1 rule 7, §4.2 seam; PRODUCT_SPEC S4). On web every picker
// call is the FIRST statement of the function the press handler calls — no `await` or state
// update happens before `launch…Async` / `getDocumentAsync`, otherwise the browser blocks the
// file dialog. APIs verified against the installed SDK 57 types (expo-image-picker 57.0.19:
// `mediaTypes: ['images']`, `allowsMultipleSelection`, `selectionLimit`, asset `{uri, width,
// height, fileName, fileSize, mimeType, file?}`; expo-document-picker 57.0.2: `{type,
// multiple, copyToCacheDirectory}` → asset `{uri, name, size, mimeType, file?}`).

import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import { newPageId } from '@/lib/ids';
import { PDF_MIME } from '@/lib/pdf';
import type { CapturedPage, CapturedPageMime } from '@/store/session';

export interface PickImageApi {
  pickFromLibrary(e?: unknown): Promise<CapturedPage[]>;
  pickPdf(e?: unknown): Promise<CapturedPage | null>;
  /** Web (mobile browsers): `<input capture>` camera via expo-image-picker; native: system camera. */
  takePhoto(e?: unknown): Promise<CapturedPage[]>;
}

/** D-21: at most 12 image pages per scan (overridden by `limits.max_pages` when known). */
export const DEFAULT_MAX_PAGES = 12;

const IMAGE_MIMES: readonly CapturedPageMime[] = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];

/** Web only: DOM `File`s behind picked pages, kept in memory for the session (never persisted). */
const webFiles = new Map<string, File>();

export function webFileFor(pageId: string): File | null {
  return webFiles.get(pageId) ?? null;
}

export function forgetWebFile(pageId: string): void {
  webFiles.delete(pageId);
}

export function imageMime(mime: string | null | undefined, fileName?: string | null): CapturedPageMime {
  const m = (mime ?? '').toLowerCase();
  if ((IMAGE_MIMES as readonly string[]).includes(m)) return m as CapturedPageMime;
  if (m === 'image/jpg') return 'image/jpeg';
  const ext = (fileName ?? '').toLowerCase().split('.').pop();
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'heic') return 'image/heic';
  if (ext === 'heif') return 'image/heif';
  return 'image/jpeg';
}

export function assetToPage(asset: ImagePicker.ImagePickerAsset, source: CapturedPage['source']): CapturedPage {
  const page: CapturedPage = {
    id: newPageId(),
    uri: asset.uri,
    mimeType: imageMime(asset.mimeType, asset.fileName),
    width: asset.width || undefined,
    height: asset.height || undefined,
    rotation: 0,
    masks: [],
    source,
    fileName: asset.fileName ?? undefined,
    byteLength: asset.fileSize ?? asset.file?.size ?? undefined,
  };
  if (Platform.OS === 'web' && asset.file) webFiles.set(page.id, asset.file);
  return page;
}

export function documentToPage(asset: DocumentPicker.DocumentPickerAsset): CapturedPage {
  const page: CapturedPage = {
    id: newPageId(),
    uri: asset.uri,
    mimeType: 'application/pdf',
    rotation: 0,
    masks: [],
    source: 'pdf',
    fileName: asset.name,
    byteLength: asset.size ?? asset.file?.size ?? undefined,
  };
  if (Platform.OS === 'web' && asset.file) webFiles.set(page.id, asset.file);
  return page;
}

function libraryOptions(limit: number): ImagePicker.ImagePickerOptions {
  return {
    mediaTypes: ['images'],
    allowsMultipleSelection: limit > 1,
    selectionLimit: Math.max(1, limit),
    orderedSelection: true,
    quality: 1,
    exif: false,
    base64: false,
  };
}

function toPages(res: ImagePicker.ImagePickerResult, source: CapturedPage['source'], limit: number): CapturedPage[] {
  if (res.canceled || !res.assets) return [];
  return res.assets.slice(0, Math.max(1, limit)).map((a) => assetToPage(a, source));
}

/** Pure factory (exported for tests): `remaining()` is read AFTER the picker call returns. */
export function createPickers(remaining: () => number): PickImageApi {
  return {
    pickFromLibrary: (_e?: unknown) => {
      const pending = ImagePicker.launchImageLibraryAsync(libraryOptions(remaining()));
      return pending.then((res) => toPages(res, 'library', remaining()));
    },
    takePhoto: (_e?: unknown) => {
      const pending = ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1, exif: false });
      return pending.then((res) => toPages(res, 'camera', 1));
    },
    pickPdf: (_e?: unknown) => {
      const pending = DocumentPicker.getDocumentAsync({
        type: PDF_MIME,
        multiple: false,
        copyToCacheDirectory: true,
      });
      return pending.then((res) => (res.canceled || !res.assets?.length ? null : documentToPage(res.assets[0])));
    },
  };
}
