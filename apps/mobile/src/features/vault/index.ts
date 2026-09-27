// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP6. Keep every export name and signature.

import type { ReactElement } from 'react';

import type { AnalysisResult } from '@/api/types';
import type { StoredDocument } from '@/storage';
import type { CapturedPage } from '@/store/session';

export interface SaveToVaultSheetProps {
  analysis: AnalysisResult;
  pages: CapturedPage[];
  onSaved(documentId: string): void;
  onCancel(): void;
}

/** "Whose paper is this?" save sheet. Day-0 stub renders nothing. */
export function SaveToVaultSheet(_props: SaveToVaultSheetProps): ReactElement | null {
  return null;
}

/** Load one stored document from the vault. Day-0 stub: never loads. */
export function useDocument(_id: string): { doc: StoredDocument | null; loading: boolean } {
  return { doc: null, loading: false };
}

/** The next upcoming date across all stored documents (Home "next date" card). */
export function useNextDate(): { documentId: string; title: string; dateIso: string } | null {
  return null;
}
