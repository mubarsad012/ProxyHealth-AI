// Offline / sample mode (ARCHITECTURE §3 "offline.ts", D-29). When the API is unreachable and the
// user is in sample mode, recorded results for the bundled fixtures are served from
// `assets/fixtures` (synced by WP7). Real scans are NEVER faked: anything that is not a bundled
// sample resolves to `null` and the caller shows the offline state.

import { fixtureAssets, fixtureManifest } from '@/assets/fixtures';
import type { ApiClient } from '@/api/client';
import type { AnalysisResult, DemoFixture, TroubleshootResult } from '@/api/types';

export type SampleResult = AnalysisResult | TroubleshootResult;

export function bundledFixtures(): DemoFixture[] {
  return fixtureManifest;
}

export function bundledFixture(id: string): DemoFixture | null {
  return fixtureManifest.find((f) => f.id === id) ?? null;
}

/** Thumbnail asset id (`require` result) or null when none is bundled. */
export function bundledFixtureThumbnail(id: string): number | null {
  return fixtureAssets[id]?.thumbnail ?? null;
}

/** The language a recorded result exists for: exact tag, else English, else null. */
export function offlineResultLanguage(id: string, lang: string): string | null {
  const results = fixtureAssets[id]?.results;
  if (!results) return null;
  if (results[lang]) return lang;
  if (results.en) return 'en';
  return null;
}

export function canServeOffline(id: string, lang: string): boolean {
  return offlineResultLanguage(id, lang) !== null;
}

/** Recorded `AnalysisResult` / `TroubleshootResult` for a sample, or null (never a fake). */
export function bundledFixtureResult(id: string, lang: string): { result: SampleResult; language: string } | null {
  const use = offlineResultLanguage(id, lang);
  if (!use) return null;
  const raw = fixtureAssets[id]?.results[use];
  if (!raw || typeof raw !== 'object') return null;
  return { result: raw as SampleResult, language: use };
}

export interface FixtureListing {
  fixtures: DemoFixture[];
  source: 'server' | 'bundled';
}

/** `GET /v1/demo/fixtures`, falling back to the bundled manifest when the server is unreachable. */
export async function listFixturesWithFallback(client: ApiClient): Promise<FixtureListing> {
  try {
    const fixtures = await client.listFixtures();
    return { fixtures, source: 'server' };
  } catch {
    return { fixtures: bundledFixtures(), source: 'bundled' };
  }
}

/** Thumbnail for the sample list: server URL when online, bundled asset otherwise. */
export function fixtureThumbnailSource(
  client: ApiClient,
  fixture: DemoFixture,
  online: boolean,
): { uri: string } | number | null {
  if (online) return { uri: client.fixturePageUrl(fixture.id, 1) };
  return bundledFixtureThumbnail(fixture.id);
}
