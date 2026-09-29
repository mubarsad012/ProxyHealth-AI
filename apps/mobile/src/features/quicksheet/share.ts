// Quick-sheet actions per platform (PRODUCT_SPEC S15; expo-print / expo-sharing / expo-clipboard
// SDK 57, verified against docs.expo.dev/versions/v57.0.0 and the installed type definitions).
// Native: `Print.printToFileAsync({ html })` → `Sharing.shareAsync(uri, { mimeType })`, gated by
// `Sharing.isAvailableAsync()`; the temporary PDF is deleted afterwards. Web: `Print.printAsync`
// opens the browser print dialog; the PDF file comes from the server (`serverPdf.ts`).

import * as Clipboard from 'expo-clipboard';
import { File } from 'expo-file-system';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

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

/** "Print or save as PDF": native print UI, or the browser print dialog on web. */
export async function printQuickSheet(html: string): Promise<void> {
  await Print.printAsync({ html });
}

/**
 * Copy the sheet text. On web this must be the first call inside the click handler (WebKit
 * rejects clipboard writes after an await), so callers invoke it synchronously in `onPress`.
 */
export function copyQuickSheetText(text: string): Promise<boolean> {
  return Clipboard.setStringAsync(text);
}
