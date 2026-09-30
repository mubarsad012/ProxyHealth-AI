// S5 "blurry hint" (web only, canvas variance): each picked photo is measured once on a small grey
// copy; blurry pages get `review.blur_hint` ("Page {n} looks blurry. Take it again?"). Native has
// no pixel access here, so the hook returns nothing there. Nothing is stored or sent.

import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { looksBlurry, sharpnessScore } from '@/lib/image';
import type { CapturedPage } from '@/store/session';

import { webFileFor } from './pick';

/** Page numbers (1-based, document order) whose score says "blurry" (pure; exported for tests). */
export function blurryPageNumbers(pages: readonly CapturedPage[], scores: Readonly<Record<string, number | null>>): number[] {
  const out: number[] = [];
  pages.forEach((p, i) => {
    if (looksBlurry(scores[p.id] ?? null)) out.push(i + 1);
  });
  return out;
}

export function useBlurHints(pages: readonly CapturedPage[], enabled: boolean): number[] {
  const [scores, setScores] = useState<Record<string, number | null>>({});
  useEffect(() => {
    if (Platform.OS !== 'web' || !enabled) return;
    let cancelled = false;
    const todo = pages.filter((p) => p.mimeType !== 'application/pdf' && p.source !== 'sample' && !(p.id in scores));
    for (const p of todo) {
      const file = webFileFor(p.id);
      void sharpnessScore(file ? { file } : { uri: p.uri })
        .catch(() => null)
        .then((score) => {
          if (!cancelled) setScores((s) => ({ ...s, [p.id]: score }));
        });
    }
    return () => {
      cancelled = true;
    };
    // `scores` is read only to skip pages already measured.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages, enabled]);
  return enabled ? blurryPageNumbers(pages, scores) : [];
}
