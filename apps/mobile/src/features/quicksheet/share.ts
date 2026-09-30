// Quick-sheet actions per platform (PRODUCT_SPEC S15; expo-print / expo-sharing / expo-clipboard
// SDK 57, verified against docs.expo.dev/versions/v57.0.0 and the installed type definitions).
// Native: `Print.printToFileAsync({ html })` → `Sharing.shareAsync(uri, { mimeType })`, gated by
// `Sharing.isAvailableAsync()`; the temporary PDF is deleted afterwards. Web: the sheet HTML is
// printed from a hidden iframe (expo-print's web `printAsync` would print the whole app window);
// the PDF file comes from the server (`serverPdf.ts`).

import * as Clipboard from 'expo-clipboard';
import { File } from 'expo-file-system';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import { webDocument } from '@/lib/platform';

export type ShareOutcome = 'shared' | 'unavailable';

/** File sharing works on iOS/Android only (web cannot share local file URIs). */
export async function canShareFiles(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  try {
    return await Sharing.isAvailableAsync();
  } catch {
    return false;
  }
}

export async function shareQuickSheetPdf(html: string, dialogTitle: string): Promise<ShareOutcome> {
  if (Platform.OS === 'web') return 'unavailable';
  if (!(await canShareFiles())) return 'unavailable';
  const { uri } = await Print.printToFileAsync({ html, base64: false });
  try {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle });
  } finally {
    try {
      const f = new File(uri);
      if (f.exists) f.delete();
    } catch {
      // the OS clears its cache directory eventually
    }
  }
  return 'shared';
}

/**
 * Web print: expo-print's web `printAsync` ignores `html` and prints the whole app window, so the
 * sheet is written into a hidden same-origin `<iframe srcdoc>` and only that frame is printed.
 * Returns false when no DOM is available (the caller then falls back to `Print.printAsync`).
 */
export function printHtmlInFrame(html: string, doc: Document | null = webDocument()): boolean {
  if (Platform.OS !== 'web' || !doc?.body) return false;
  const frame = doc.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.setAttribute('tabindex', '-1');
  frame.style.position = 'fixed';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  frame.style.opacity = '0';
  let printed = false;
  const cleanup = () => setTimeout(() => frame.remove(), 1000);
  frame.onload = () => {
    if (printed) return;
    printed = true;
    const win = frame.contentWindow;
    try {
      win?.focus();
      win?.print();
    } finally {
      cleanup();
    }
  };
  frame.srcdoc = html;
  doc.body.appendChild(frame);
  return true;
}

/** "Print or save as PDF": native print UI, or the browser print dialog (sheet only) on web. */
export async function printQuickSheet(html: string): Promise<void> {
  if (Platform.OS === 'web' && printHtmlInFrame(html)) return;
  await Print.printAsync({ html });
}

/**
 * Copy the sheet text. On web this must be the first call inside the click handler (WebKit
 * rejects clipboard writes after an await), so callers invoke it synchronously in `onPress`.
 */
export function copyQuickSheetText(text: string): Promise<boolean> {
  return Clipboard.setStringAsync(text);
}
