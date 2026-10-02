// Phase 2C — S11 on the Get help tab: search by name (`GET /v1/resources?q=`) and the language
// filter chip (default = the UI language; the chosen language is what the requests send). New
// copy (`help.any_language`, `help.search_empty`) is merged into en.json in stage 3, so these tests
// select by testID / existing keys only.

import { fireEvent, render, waitFor } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { Resource, ResourceList as ResourceListBody, ResourceMatchResponse } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';

import {
  ANY_LANGUAGE,
  browseLanguage,
  bundledBrowse,
  languageFilterTags,
  matchesQuery,
  matchLanguage,
  normaliseQuery,
} from './browse';
import { HelpTabScreen } from './HelpTabScreen';
import { clearMatchCache } from './request';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

const bundle = require('../../../assets/resources/national_fallbacks.json') as Resource[];
const byId = (id: string) => bundle.find((r) => r.id === id) as Resource;

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return {
    baseUrl: 'http://127.0.0.1:8046',
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
    fixturePageUrl: (id, n) => `http://127.0.0.1:8046/v1/demo/fixtures/${id}/pages/${n}`,
    ...overrides,
  };
}

const listOf = (items: Resource[]): ResourceListBody => ({ items, total: items.length, resource_db_version: 'test' });
const emptyMatch: ResourceMatchResponse = {
  results: [],
  national_fallbacks: [byId('211')],
  notes_keys: [],
  disclaimer_kind: 'general_information',
  resource_db_version: 'test',
};

describe('browse helpers', () => {
  it('lists the UI language first, then English, every app language, and "Any language" last', () => {
    const tags = languageFilterTags('prs');
    expect(tags.slice(0, 2)).toEqual(['prs', 'en']);
    expect(tags[tags.length - 1]).toBe(ANY_LANGUAGE);
    expect(new Set(tags).size).toBe(tags.length);
    expect(languageFilterTags('en').slice(0, 2)).toEqual(['en', 'es']);
  });

  it('match requests always carry a language; browse drops it for "Any language"', () => {
    expect(matchLanguage(ANY_LANGUAGE, 'prs')).toBe('prs');
    expect(matchLanguage('es', 'prs')).toBe('es');
    expect(browseLanguage(ANY_LANGUAGE)).toBeUndefined();
    expect(browseLanguage('ar')).toBe('ar');
  });

  it('a search needs 2+ characters and matches name, id or name note like the server', () => {
    expect(normaliseQuery(' a ')).toBeNull();
    expect(normaliseQuery('  legal ')).toBe('legal');
    expect(matchesQuery(byId('211'), '211')).toBe(true);
    expect(matchesQuery(byId('poison'), 'POISON')).toBe(true);
    expect(matchesQuery(byId('poison'), 'housing')).toBe(false);
  });

  it('offline search filters the bundled subset by name and language', () => {
    expect(bundledBrowse({ state: null, language: undefined, q: 'poison' }).map((r) => r.id)).toEqual(['poison']);
    // Poison Control lists English only: a Dari filter keeps the interpreter lines instead.
    const dari = bundledBrowse({ state: null, language: 'prs', q: null }).map((r) => r.id);
    expect(dari).toContain('211');
    expect(dari).not.toContain('poison');
  });
});

describe('HelpTabScreen search + language filter', () => {
  beforeEach(() => clearMatchCache());

  it('searches by name with GET /v1/resources?q= in the UI language', async () => {
    const listResources = jest.fn().mockResolvedValue(listOf([byId('lawhelp')]));
    const { getByTestId, findByTestId } = await render(
      <AppProviders client={fakeClient({ listResources })} staticMetrics>
        <HelpTabScreen />
      </AppProviders>,
    );
    const box = getByTestId('help-search');
    await fireEvent.changeText(box, 'law');
    await fireEvent(box, 'submitEditing');
    await waitFor(() => expect(listResources).toHaveBeenCalled());
    expect(listResources.mock.calls[0][0]).toMatchObject({ q: 'law', language: 'en', offset: 0 });
    expect(await findByTestId('help-search-results')).toBeTruthy();
    expect(await findByTestId('resource-lawhelp')).toBeTruthy();
  });

  it('offline search shows the bundled match (never an invented listing)', async () => {
    const { getByTestId, findByTestId, queryByTestId } = await render(
      <AppProviders client={fakeClient()} staticMetrics>
        <HelpTabScreen />
      </AppProviders>,
    );
    const box = getByTestId('help-search');
    await fireEvent.changeText(box, 'poison');
    await fireEvent(box, 'submitEditing');
    expect(await findByTestId('resource-poison', {}, { timeout: 4000 })).toBeTruthy();
    expect(queryByTestId('resource-211')).toBeNull();
  });

  it('an empty search shows the empty line', async () => {
    const listResources = jest.fn().mockResolvedValue(listOf([]));
    const { getByTestId, findByTestId } = await render(
      <AppProviders client={fakeClient({ listResources })} staticMetrics>
        <HelpTabScreen />
      </AppProviders>,
    );
    await fireEvent.changeText(getByTestId('help-search'), 'zzz');
    await fireEvent(getByTestId('help-search'), 'submitEditing');
    expect(await findByTestId('help-search-empty')).toBeTruthy();
  });

  it('the chosen language is sent instead of the UI language (match and browse)', async () => {
    const matchResources = jest.fn().mockResolvedValue(emptyMatch);
    const listResources = jest.fn().mockResolvedValue(listOf([byId('211')]));
    const { getByTestId, getByText } = await render(
      <AppProviders client={fakeClient({ matchResources, listResources })} staticMetrics>
        <HelpTabScreen />
      </AppProviders>,
    );
    // Default: the UI language.
    await fireEvent.press(getByTestId('need-food'));
    await waitFor(() => expect(matchResources).toHaveBeenCalledTimes(1));
    expect(matchResources.mock.calls[0][0]).toMatchObject({ language: 'en' });
    // Open the chip ("Speaks: English") and pick Spanish.
    await fireEvent.press(getByText('Speaks: English'));
    await fireEvent.press(getByTestId('help-language-es'));
    await waitFor(() => expect(matchResources).toHaveBeenCalledTimes(2));
    expect(matchResources.mock.calls[1][0]).toMatchObject({ language: 'es' });
    await fireEvent.press(getByTestId('help-see-all'));
    await waitFor(() => expect(listResources).toHaveBeenCalled());
    expect(listResources.mock.calls[0][0]).toMatchObject({ language: 'es' });
    // "Any language": browse sends no language filter.
    await fireEvent.press(getByText('Speaks: Español'));
    await fireEvent.press(getByTestId(`help-language-${ANY_LANGUAGE}`));
    await waitFor(() => expect(listResources).toHaveBeenCalledTimes(2));
    expect(listResources.mock.calls[1][0].language).toBeUndefined();
  });
});
