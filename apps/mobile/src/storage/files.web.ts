// Page images for the web vault (D-23): Blobs in memory (or in the IndexedDB `blobs` store when the
// user opted in), shown through `URL.createObjectURL`. expo-file-system has no web implementation.
// Paths are opaque keys `web://<doc_id>/page-<n>.jpg`.

import { pageFileName, thumbFileName } from '@/storage/rows';

export interface BlobSink {
  put(path: string, blob: Blob): Promise<void>;
  get(path: string): Promise<Blob | null>;
  remove(prefix: string): Promise<void>;
}

const memoryBlobs = new Map<string, Blob>();
const objectUrls = new Map<string, string>();
let sink: BlobSink | null = null;

/** IndexedDB opt-in hands a persistent sink in; `null` returns to memory only. */
export function setBlobSink(next: BlobSink | null): void {
  sink = next;
}

export function base64ToBytes(base64: string): Uint8Array {
  const clean = base64.replace(/^data:[^,]*,/, '');
  const bin = globalThis.atob(clean);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

export function base64ToBlob(base64: string, type = 'image/jpeg'): Blob {
  return new Blob([base64ToBytes(base64) as BlobPart], { type });
}

function webPath(documentId: string, name: string): string {
  return `web://${documentId}/${name}`;
}

function revoke(path: string): void {
  const url = objectUrls.get(path);
  if (url && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url);
  objectUrls.delete(path);
}

export interface WrittenPage {
  filePath: string;
  thumbPath: string | null;
}

export async function writePageFiles(
  documentId: string,
  page: number,
  base64Jpeg: string,
  thumbBase64?: string,
): Promise<WrittenPage> {
  const filePath = webPath(documentId, pageFileName(page));
  const blob = base64ToBlob(base64Jpeg);
  revoke(filePath);
  memoryBlobs.set(filePath, blob);
  await sink?.put(filePath, blob);
  let thumbPath: string | null = null;
  if (thumbBase64) {
    thumbPath = webPath(documentId, thumbFileName(page));
    const thumb = base64ToBlob(thumbBase64);
    revoke(thumbPath);
    memoryBlobs.set(thumbPath, thumb);
    await sink?.put(thumbPath, thumb);
  }
  return { filePath, thumbPath };
}

/** Object URL for display (data: URL where `createObjectURL` is unavailable), or null. */
export async function fileUri(path: string | null): Promise<string | null> {
  if (!path) return null;
  const cached = objectUrls.get(path);
  if (cached) return cached;
  let blob = memoryBlobs.get(path) ?? null;
  if (!blob && sink) {
    blob = await sink.get(path);
    if (blob) memoryBlobs.set(path, blob);
  }
  if (!blob) return null;
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(blob);
    objectUrls.set(path, url);
    return url;
  }
  return null;
}

export async function deleteDocumentFiles(documentId: string): Promise<void> {
  const prefix = `web://${documentId}/`;
  for (const path of [...memoryBlobs.keys()]) {
    if (path.startsWith(prefix)) {
      revoke(path);
      memoryBlobs.delete(path);
    }
  }
  await sink?.remove(prefix);
}

/** Synchronous part of `deleteAllFiles` (used on `pagehide`, where nothing awaited is sure to run). */
export function clearMemoryFiles(): void {
  for (const path of [...objectUrls.keys()]) revoke(path);
  memoryBlobs.clear();
}

export async function deleteAllFiles(): Promise<void> {
  clearMemoryFiles();
  await sink?.remove('web://');
}

/** Every page image held in memory (copied into IndexedDB when the user turns keeping on). */
export function memoryBlobEntries(): [string, Blob][] {
  return [...memoryBlobs.entries()];
}

/** Take page images into memory (before IndexedDB is deleted, so this tab keeps showing them). */
export function adoptBlobs(entries: readonly { path: string; blob: Blob }[]): void {
  for (const { path, blob } of entries) {
    if (typeof path === 'string' && !memoryBlobs.has(path)) memoryBlobs.set(path, blob);
  }
}

/** Test/inspection helper: number of blobs held in memory. */
export function memoryBlobCount(): number {
  return memoryBlobs.size;
}
