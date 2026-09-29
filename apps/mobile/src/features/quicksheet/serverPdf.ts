// Web quick-sheet PDF (PRODUCT_SPEC S15, ARCHITECTURE §3.1): `POST /v1/quicksheet/pdf` → Blob →
// `<a download>`. expo-print cannot produce a file on web ("On Web this method opens the print
// dialog") and expo-sharing cannot share local files there, so the server renders the PDF with
// Noto fonts embedded and stores nothing. The object URL is revoked right after the click.

import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import type { QuickSheetRequest } from '@/api/types';
import { webDocument } from '@/lib/platform';

export const QUICKSHEET_PDF_FILENAME = 'proxyhealth-quick-sheet.pdf';

export function toPdfBlob(body: Blob | Uint8Array): Blob {
  if (typeof Blob !== 'undefined' && body instanceof Blob) return body;
  const bytes = body as Uint8Array;
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy.buffer], { type: 'application/pdf' });
}

/** Save a Blob through a temporary `<a download>` (web only; returns false elsewhere). */
export function downloadBlob(blob: Blob, filename: string): boolean {
  if (Platform.OS !== 'web') return false;
  const doc = webDocument();
  if (!doc || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return false;
  const url = URL.createObjectURL(blob);
  const a = doc.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  a.style.display = 'none';
  doc.body.appendChild(a);
  a.click();
  doc.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
}

/** Web "Download PDF": server render, then a local download. Throws `ApiError` on failure. */
export async function downloadServerPdf(client: ApiClient, req: QuickSheetRequest): Promise<boolean> {
  const body = await client.quicksheetPdf(req);
  return downloadBlob(toPdfBlob(body), QUICKSHEET_PDF_FILENAME);
}
