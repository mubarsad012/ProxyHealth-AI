// PDF pre-checks and base64 reading (ARCHITECTURE §3 `lib/pdf.ts`, D-21). The page count is only
// known server-side (pypdfium2 in memory), so the client checks size only and lets the server
// answer `pdf_too_long`. Native reads the picked file with the SDK 57 class API
// (`new File(uri).base64()`, verified against the installed expo-file-system 57.0.7 types);
// web reads the DOM `File` from expo-document-picker. Nothing is written anywhere.

import { File as FsFile } from 'expo-file-system';
import { Platform } from 'react-native';

import { ApiError } from '@/api/errors';
import type { Limits } from '@/api/types';
import { base64ByteLength } from '@/lib/image';

export const PDF_MIME = 'application/pdf';

/** D-21 default when `/v1/config` is not loaded yet. */
export const DEFAULT_MAX_PDF_BYTES = 12 * 1024 * 1024;

/** One decimal, as shown by `review.pdf_summary` ("PDF · {size} MB"). */
export function pdfSizeMb(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return (Math.max(0.1, Math.round(mb * 10) / 10)).toFixed(1);
}

/** `payload_too_large` before upload when the file exceeds `limits.max_pdf_bytes`, else null. */
export function checkPdfSize(bytes: number | undefined, limits: Pick<Limits, 'max_pdf_bytes'> | null): ApiError | null {
  const max = limits?.max_pdf_bytes ?? DEFAULT_MAX_PDF_BYTES;
  if (bytes === undefined || bytes <= max) return null;
  return new ApiError({
    code: 'payload_too_large',
    status: 413,
    userMessageKey: 'err.payload_too_large',
    details: { max_pdf_bytes: max },
  });
}

/** Base64 of an ArrayBuffer without blowing the call stack on large files. */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export type PdfInput = { uri: string; file?: File | null };

/** Read a picked PDF as base64 (web: DOM File or blob: URL; native: file URI). */
export async function readPdfBase64(input: PdfInput): Promise<{ base64: string; byteLength: number }> {
  if (Platform.OS === 'web') {
    const blob: Blob = input.file ?? (await (await fetch(input.uri)).blob());
    const base64 = arrayBufferToBase64(await blob.arrayBuffer());
    return { base64, byteLength: blob.size };
  }
  const file = new FsFile(input.uri);
  const base64 = await file.base64();
  return { base64, byteLength: base64ByteLength(base64) };
}
