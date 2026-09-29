// Action Hub seam (BUILD_PLAN §4.2; PRODUCT_SPEC S11). Owner: WP6 lane 6B.
// `HelpForDocument` is rendered by WP5's `app/result/[id]/help.tsx`; `HelpTabScreen` by
// `app/(tabs)/help.tsx`. Resources only come from the vetted DB (server match or bundled subset).

export { HelpForDocument, type HelpForDocumentProps, quickSheetHref, ScamNotice } from './HelpForDocument';
export { HelpTabScreen, type HelpTabScreenProps } from './HelpTabScreen';
export { NEED_TILES, needById, type NeedTile } from './needs';
export { RegionControl, useRegion } from './RegionControl';
export {
  buildMatchRequestForAnalysis,
  buildMatchRequestForTags,
  bundledResources,
  cachedMatch,
  clearMatchCache,
  lastMatchForDocument,
  matchKey,
  offlineFallbacksFor,
  offlineMatchResponse,
  type Region,
  rememberMatch,
  tagsForAnalysis,
} from './request';
export { ResourceCard, type ResourceCardProps } from './ResourceCard';
export { ResourceList, type ResourceListProps } from './ResourceList';
export {
  isOfflineError,
  type ResourceMatchExtras,
  type ResourceMatchState,
  useResourceMatch,
  type UseResourceMatchOptions,
} from './useResourceMatch';
