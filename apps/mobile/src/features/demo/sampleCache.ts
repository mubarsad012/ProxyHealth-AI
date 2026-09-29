// Session cache for the sample list, kept apart from `samples.ts` so "Delete everything" can reset
// it without importing the bundled fixture assets (jest maps `@/` to `src/` only).

import type { FixtureListing } from '@/api/offline';

let cache: Promise<FixtureListing> | null = null;
let cacheSource: FixtureListing['source'] | null = null;

/** Session-cached listing; a bundled (offline) answer is retried on the next open. */
export function cachedSamples(load: () => Promise<FixtureListing>): Promise<FixtureListing> {
  if (!cache || cacheSource === 'bundled') {
    cache = load().then((listing) => {
      cacheSource = listing.source;
      return listing;
    });
  }
  return cache;
}

export function resetSamplesCache(): void {
  cache = null;
  cacheSource = null;
}
