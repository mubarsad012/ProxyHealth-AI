// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP6. Keep every export name and signature.

import type { ReactElement } from 'react';

import type { AnalysisResult, QuickSheetSection, Resource } from '@/api/types';

export interface QuickSheetScreenProps {
  analysis: AnalysisResult;
  documentId?: string;
}

/** S15 quick-sheet preview + share/print/copy/read aloud. Day-0 stub renders nothing. */
export function QuickSheetScreen(_props: QuickSheetScreenProps): ReactElement | null {
  return null;
}

export type TranslateFn = (key: string, vars?: Record<string, string | number>) => string;

export interface QuickSheetText {
  title: string;
  sections: QuickSheetSection[];
  footer: string;
}

/** Build the quick-sheet text from an analysis and its matched resources (contacts only from
 *  the paper or the vetted DB — never invented). Day-0 stub returns an empty sheet. */
export function buildQuickSheetText(
  _analysis: AnalysisResult,
  _resources: Resource[],
  _t: TranslateFn,
): QuickSheetText {
  return { title: '', sections: [], footer: '' };
}
