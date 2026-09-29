// WP6 lane 6B — Action Hub: request building, the per-document cache, bundled national fallbacks
// (RESOURCE_DB §6.9 order), the LSC note + "If that is not you", and hidden broken links.

import { fireEvent, render, waitFor } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult, Resource, ResourceMatchResponse } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';

import { whyText, whyVars } from './format';
import { HelpForDocument } from './HelpForDocument';
import {
  buildMatchRequestForAnalysis,
  buildMatchRequestForTags,
  clearMatchCache,
  lastMatchForDocument,
  matchKey,
  offlineFallbacksFor,
  offlineMatchResponse,
} from './request';
import { ResourceList } from './ResourceList';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const medicaid = require('../../../assets/fixtures/medicaid_address_confirmation.result.en.json') as AnalysisResult;
const bundle = require('../../../assets/resources/national_fallbacks.json') as Resource[];
const byId = (id: string) => bundle.find((r) => r.id === id) as Resource;
const region = { state: null, zip3: null };

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return {
    baseUrl: 'http://127.0.0.1:8029',
    health: fail,
    getConfig: fail,
    getPack: fail,
    postPack: fail,
    analyze: fail,
    troubleshoot: fail,
    chat: fail,
    matchResources: fail,
    listResources: fail,
    getResource: fail,
    getRules: fail,
    quicksheetPdf: fail,
    feedback: fail,
    listFixtures: fail,
    fixturePageUrl: (id, n) => `http://127.0.0.1:8029/v1/demo/fixtures/${id}/pages/${n}`,
    ...overrides,
  };
}

function lscResponse(): ResourceMatchResponse {
  const lawhelp: Resource = { ...byId('lawhelp'), status_note_key: 'lsc_restricted' };
  const broken: Resource = { ...byId('liheap'), id: 'broken_one', name: 'Broken Listing', link_health: 'broken' };
  return {
    results: [
      { resource: lawhelp, score: 3, why_keys: ['why.for_benefits_navigation'], why: ['For benefits letters'], eligibility_note_key: 'lsc_restricted', checklist: [{ key: 'bring_notice', text_en: 'This letter' }] },
      { resource: broken, score: 2, why_keys: [], why: [], eligibility_note_key: null, checklist: [] },
    ],
    national_fallbacks: [byId('211')],
    notes_keys: ['notes.lsc_restricted_explained', 'notes.verify_before_going'],
    disclaimer_kind: 'general_information',
    resource_db_version: 'test',
  };
}

describe('match requests', () => {
  it('uses the paper tags, the paper state as a hint, and limit 8', () => {
    const req = buildMatchRequestForAnalysis(medicaid, { region, language: 'en' });
    expect(req.tags).toEqual(['medicaid_renewal', 'change_of_address', 'benefits_navigation']);
    expect(req.state).toBe('VA');
    expect(req.zip3).toBeNull();
    expect(req.limit).toBe(8);
    expect((req.institutions_as_written ?? []).length).toBeLessThanOrEqual(10);
  });

  it('prefers the Settings region and keys the cache independent of tag order', () => {
    const a = buildMatchRequestForTags(['food', 'snap'], { region: { state: 'MD', zip3: '208' }, language: 'es' })!;
    const b = buildMatchRequestForTags(['snap', 'food'], { region: { state: 'MD', zip3: '208' }, language: 'es' })!;
    expect(a.state).toBe('MD');
    expect(a.zip3).toBe('208');
    expect(matchKey(a)).toBe(matchKey(b));
    expect(buildMatchRequestForTags([], { region, language: 'en' })).toBeNull();
  });
});

describe('bundled national fallbacks (offline)', () => {
  it('follows RESOURCE_DB §6.9: 211 always, immlawhelp for immigration, hrsa for health', () => {
    const imm = buildMatchRequestForTags(['immigration_legal_help'], { region, language: 'en' })!;
    expect(offlineFallbacksFor(imm).map((r) => r.id)).toEqual(['211', 'immlawhelp']);
    const health = buildMatchRequestForTags(['medical_bill'], { region, language: 'en' })!;
    expect(offlineFallbacksFor(health).map((r) => r.id)).toEqual(['211', 'hrsa_fqhc']);
  });

  it('puts crisis lines first when emergency and adds scam reporting', () => {
    const req = buildMatchRequestForTags(['crisis', 'scam_report'], { region, language: 'en', emergency: true })!;
    const ids = offlineFallbacksFor(req).map((r) => r.id);
    expect(ids[0]).toBe('988');
    expect(ids).toEqual(expect.arrayContaining(['ftc_reportfraud', 'dhs_oig', '211']));
  });

  it('offline response only contains bundled DB entries', () => {
    const req = buildMatchRequestForTags(['food'], { region, language: 'en' })!;
    const res = offlineMatchResponse(req);
    const ids = new Set(bundle.map((r) => r.id));
    for (const m of res.results) expect(ids.has(m.resource.id)).toBe(true);
    for (const r of res.national_fallbacks) expect(ids.has(r.id)).toBe(true);
    expect(res.results.map((m) => m.resource.id)).toContain('feeding_america');
  });
});

describe('why chips', () => {
  it('fills placeholders from the server line and falls back to it', () => {
    const t = (k: string, v?: Record<string, string | number>) =>
      k === 'why.serves_your_state' ? `Sirve a ${v?.state}` : k === 'why.for_food' ? 'Comida' : k;
    expect(whyVars('why.serves_your_state', 'Serves Virginia')).toEqual({ state: 'Virginia' });
    expect(whyText('why.serves_your_state', 'Serves Virginia', t)).toBe('Sirve a Virginia');
    expect(whyText('why.serves_your_state', undefined, t)).toBeNull();
    expect(whyText('why.for_food', 'For food', t)).toBe('Comida');
  });
});

describe('ResourceList', () => {
  it('shows the LSC note with "If that is not you", hides broken links, shows Verified on', async () => {
    const onAlt = jest.fn();
    const { getByText, queryByText, getAllByText } = await render(
      <AppProviders client={fakeClient()} staticMetrics>
        <ResourceList data={lscResponse()} regionKnown onLscAlternative={onAlt} />
      </AppProviders>,
    );
    expect(getByText(/usually cannot help people without immigration papers/)).toBeTruthy();
    await fireEvent.press(getByText('If that is not you, try these instead'));
    expect(onAlt).toHaveBeenCalled();
    expect(queryByText('Broken Listing')).toBeNull();
    expect(getByText('Nothing verified near you yet. These national services can help.')).toBeTruthy();
    expect(getByText('Always available')).toBeTruthy();
    expect(getAllByText(/^Verified on /).length).toBeGreaterThanOrEqual(2);
  });
});

describe('HelpForDocument', () => {
  beforeEach(() => clearMatchCache());

  it('fetches once per paper and serves the cache afterwards', async () => {
    const matchResources = jest.fn().mockResolvedValue(lscResponse());
    const client = fakeClient({ matchResources });
    const first = await render(
      <AppProviders client={client} staticMetrics>
        <HelpForDocument analysis={medicaid} />
      </AppProviders>,
    );
    await waitFor(() => expect(first.getByText('Always available')).toBeTruthy());
    expect(lastMatchForDocument(medicaid.analysis_id)).not.toBeNull();
    await first.unmount();
    const second = await render(
      <AppProviders client={client} staticMetrics>
        <HelpForDocument analysis={medicaid} />
      </AppProviders>,
    );
    expect(second.getByText('Always available')).toBeTruthy();
    expect(matchResources).toHaveBeenCalledTimes(1);
  });

  it('offline with nothing cached still shows the bundled national fallbacks', async () => {
    const { findByText } = await render(
      <AppProviders client={fakeClient()} staticMetrics>
        <HelpForDocument analysis={medicaid} />
      </AppProviders>,
    );
    expect(await findByText('Always available', {}, { timeout: 4000 })).toBeTruthy();
    expect(await findByText('Tell me your state to find help near you.')).toBeTruthy();
  });
});
