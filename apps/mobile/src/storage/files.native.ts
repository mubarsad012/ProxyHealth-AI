// Page image files for the native vault (D-22): `Paths.document/vault/<doc_id>/page-<n>.jpg` and
// `thumb-<n>.jpg`, written from base64 JPEG. expo-file-system SDK 57 class API, verified against
// https://docs.expo.dev/versions/v57.0.0/sdk/filesystem/ and the installed types:
// `new Directory(Paths.document, 'vault', id).create({ intermediates, idempotent })`,
// `new File(dir, name).write(base64, { encoding: 'base64' })` (synchronous in SDK 57),
// `file.exists`, `file.uri`, `dir.delete()`. No web implementation (files.web.ts covers web).

import { Directory, File, Paths } from 'expo-file-system';

import { pageFileName, thumbFileName } from '@/storage/rows';

export const VAULT_DIR_NAME = 'vault';

function vaultRoot(): Directory {
  return new Directory(Paths.document, VAULT_DIR_NAME);
}

function documentDir(documentId: string): Directory {
  return new Directory(Paths.document, VAULT_DIR_NAME, documentId);
}

function ensureDir(dir: Directory): void {
  if (!dir.exists) dir.create({ intermediates: true, idempotent: true });
}

function writeBase64(dir: Directory, name: string, base64: string): string {
  const file = new File(dir, name);
  if (file.exists) file.delete();
  file.create({ overwrite: true });
  file.write(base64, { encoding: 'base64' });
  return file.uri;
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
  const dir = documentDir(documentId);
  ensureDir(dir);
  const filePath = writeBase64(dir, pageFileName(page), base64Jpeg);
  const thumbPath = thumbBase64 ? writeBase64(dir, thumbFileName(page), thumbBase64) : null;
  return { filePath, thumbPath };
}

/** File URI for display, or null when the file is gone (e.g. keep_pages off). */
export async function fileUri(path: string | null): Promise<string | null> {
  if (!path) return null;
  try {
    const file = new File(path);
    return file.exists ? file.uri : null;
  } catch {
    return null;
  }
}

export async function deleteDocumentFiles(documentId: string): Promise<void> {
  try {
    const dir = documentDir(documentId);
    if (dir.exists) dir.delete();
  } catch {
    // already gone
  }
}

export async function deleteAllFiles(): Promise<void> {
  try {
    const root = vaultRoot();
    if (root.exists) root.delete();
  } catch {
    // already gone
  }
}
