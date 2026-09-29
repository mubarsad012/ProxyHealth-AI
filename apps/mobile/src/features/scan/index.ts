// Scan seam (BUILD_PLAN §4.2 / §5.0; owner WP5). Keep every export name and signature.
// On web the picker call must be the first statement inside the button's onPress (gesture-safe),
// which is why both pickers accept the press event:
//   <BigButton onPress={(e) => void pick.pickFromLibrary(e).then(onPages)} … />

import { useMemo } from 'react';

import { useSession } from '@/store/session';

import { createPickers, DEFAULT_MAX_PAGES, type PickImageApi } from './pick';

export type { PickImageApi } from './pick';
export { compressPage, rotateMasks, turnPage } from './compress';
export { hasMasks, maskAround, maskFromDrag, moveMask, resizeMask } from './masks';
export { assetToPage, DEFAULT_MAX_PAGES, documentToPage, forgetWebFile, imageMime, webFileFor } from './pick';
export { pagesAfterPick, type PickOutcome } from './pageQueue';

/** Gesture-safe pickers. Library selection is capped at the pages still allowed in this scan. */
export function usePickImage(): PickImageApi {
  return useMemo(
    () =>
      createPickers(() => {
        const s = useSession.getState();
        const max = s.serverConfig?.limits.max_pages ?? DEFAULT_MAX_PAGES;
        const images = s.pages.filter((p) => p.mimeType !== 'application/pdf').length;
        return Math.max(1, max - images);
      }),
    [],
  );
}
