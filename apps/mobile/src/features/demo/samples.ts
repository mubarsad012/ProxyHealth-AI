// Sample papers (PRODUCT_SPEC §12.2, D-29): the list from `GET /v1/demo/fixtures` (cached for the
// session) with the bundled `assets/fixtures` manifest as the offline fallback, localized titles,
// and display-only capture pages for S5 (`source: 'sample'`). S6 then posts `demo_sample_id` with
// `pages: []`, so these page URIs are never uploaded.

import { Image } from 'react-native';

import type { ApiClient } from '@/api/client';
import { bundledFixtureThumbnail, type FixtureListing, listFixturesWithFallback } from '@/api/offline';
import type { DemoFixture } from '@/api/types';
import type { CapturedPage } from '@/store/session';

import { cachedSamples, resetSamplesCache } from './sampleCache';

type Translate = (key: string, vars?: Record<string, string | number>) => string;

/** Session-cached `GET /v1/demo/fixtures` with the bundled manifest as the offline fallback. */
export function loadSamples(client: ApiClient): Promise<FixtureListing> {
  return cachedSamples(() => listFixturesWithFallback(client));
}

export { resetSamplesCache };

/** Documents first (the canonical Medicaid letter at the top), the screenshot last. */
export function orderSamples(fixtures: DemoFixture[]): DemoFixture[] {
  const rank = (f: DemoFixture) => (f.id === 'medicaid_address_confirmation' ? 0 : f.kind === 'screenshot' ? 2 : 1);
  return [...fixtures].sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
}

/** `t(title_key)`, falling back to the English title when the pack has no such key. */
export function sampleTitle(f: DemoFixture, t: Translate): string {
  const text = t(f.title_key);
  return text && text !== f.title_key ? text : f.title_en;
}

/** A `require()`d asset → URI (native numbers via resolveAssetSource; web gives a string/object). */
export function assetUri(mod: unknown): string | null {
  if (typeof mod === 'string') return mod;
  if (mod && typeof mod === 'object' && typeof (mod as { uri?: unknown }).uri === 'string') {
    return (mod as { uri: string }).uri;
  }
  if (typeof mod === 'number') {
    try {
      const resolve = (Image as unknown as { resolveAssetSource?: (m: number) => { uri?: string } | null })
        .resolveAssetSource;
      return resolve?.(mod)?.uri ?? null;
    } catch {
      return null;
    }
  }
  return null;
}

/** Thumbnail source for the list: server PNG online, bundled PNG offline. */
export function sampleThumbnail(client: ApiClient, f: DemoFixture, source: FixtureListing['source']) {
  if (source === 'server') return { uri: client.fixturePageUrl(f.id, 1) };
  const bundled = bundledFixtureThumbnail(f.id);
  return bundled ?? null;
}

/** Display-only pages for S5 (never uploaded: S6 sends `demo_sample_id` with `pages: []`). */
export function samplePages(client: ApiClient, f: DemoFixture, source: FixtureListing['source']): CapturedPage[] {
  const count = Math.max(1, f.pages);
  const pages: CapturedPage[] = [];
  for (let n = 1; n <= count; n += 1) {
    const uri =
      source === 'server' ? client.fixturePageUrl(f.id, n) : n === 1 ? assetUri(bundledFixtureThumbnail(f.id)) : null;
    if (!uri) continue;
    pages.push({
      id: `sample-${f.id}-${n}`,
      uri,
      mimeType: 'image/png',
      rotation: 0,
      masks: [],
      source: 'sample',
    });
  }
  return pages;
}
