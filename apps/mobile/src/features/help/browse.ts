// S11 browse + search on the Get help tab (PRODUCT_SPEC S11: `GET /v1/resources?tag=…&state=…&q=…`
// and the language filter chip, default = the UI language). Pure helpers + the `useBrowse` hook.
// Resources only ever come from the vetted DB: the server list, or the bundled national subset
// when the server cannot be reached (filtered locally by the same name rule the server uses).

import { useEffect, useState } from 'react';

import type { ApiClient } from '@/api/client';
import { useApi } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { Resource } from '@/api/types';
import { LANGUAGE_TAGS } from '@/i18n/languages';

import { bundledResources } from './request';

/** The "Any language" choice of the filter chip (no `language` filter on browse/search). */
export const ANY_LANGUAGE = 'any';

/** Fewer characters than this do not start a search (one letter matches almost everything). */
export const MIN_QUERY_CHARS = 2;
/** The server caps `q`; a longer search box value is cut (names are short). */
export const MAX_QUERY_CHARS = 80;

/** `GET /v1/resources` caps `limit` at 200 (routers/resources.py); page with `offset` until
 *  `total` so "See all help" really lists the whole DB for the region (bounded to 5 pages). */
export const BROWSE_PAGE = 200;
export const BROWSE_MAX_PAGES = 5;

/** Chip choices, UI language first (the default), then English, the rest in the language-grid
 *  order, and "Any language" last. */
export function languageFilterTags(uiTag: string): string[] {
  const rest = LANGUAGE_TAGS.filter((tag) => tag !== uiTag && tag !== 'en');
  return [uiTag, ...(uiTag === 'en' ? [] : ['en']), ...rest, ANY_LANGUAGE];
}

/** The `language` sent to `POST /v1/resources/match` (required there; the matcher only ranks by
 *  it and never drops a result, so "Any language" ranks by the UI language). */
export function matchLanguage(filter: string, uiTag: string): string {
  return filter === ANY_LANGUAGE || !filter ? uiTag : filter;
}

/** The `language` query of `GET /v1/resources` (a strict filter there); none for "Any language". */
export function browseLanguage(filter: string): string | undefined {
  return filter === ANY_LANGUAGE || !filter ? undefined : filter;
}

/** Trimmed search text, or null when it is too short to search. */
export function normaliseQuery(q: string | null | undefined): string | null {
  const s = Array.from((q ?? '').trim()).slice(0, MAX_QUERY_CHARS).join('');
  return Array.from(s).length >= MIN_QUERY_CHARS ? s : null;
}

/** Same rule as the server's `ResourceRepo.list(q=…)`: case-folded substring of name, id or name_note. */
export function matchesQuery(r: Resource, q: string): boolean {
  const needle = q.trim().toLocaleLowerCase();
  if (!needle) return true;
  return (
    r.name.toLocaleLowerCase().includes(needle) ||
    r.id.toLocaleLowerCase().includes(needle) ||
    Boolean(r.name_note && r.name_note.toLocaleLowerCase().includes(needle))
  );
}

/** Same rule as the server's `language` filter: speaks it, or offers interpreters. */
export function speaks(r: Resource, language: string | undefined): boolean {
  if (!language) return true;
  const langs = r.languages ?? [];
  return langs.includes(language) || langs.includes('interpreters_200+');
}

export interface BrowseQuery {
  state: string | null;
  /** Already resolved with `browseLanguage` (undefined = any language). */
  language: string | undefined;
  /** Already normalised with `normaliseQuery` (null = browse everything). */
  q: string | null;
}

export async function listAll(client: ApiClient, query: BrowseQuery): Promise<Resource[]> {
  const items: Resource[] = [];
  for (let page = 0; page < BROWSE_MAX_PAGES; page += 1) {
    const res = await client.listResources({
      state: query.state ?? undefined,
      language: query.language,
      q: query.q ?? undefined,
      limit: BROWSE_PAGE,
      offset: page * BROWSE_PAGE,
    });
    items.push(...res.items);
    if (res.items.length === 0 || items.length >= res.total) break;
  }
  return items;
}

/** Offline: the bundled national subset, filtered like the server would filter it. */
export function bundledBrowse(query: BrowseQuery): Resource[] {
  return bundledResources().filter((r) => speaks(r, query.language) && (!query.q || matchesQuery(r, query.q)));
}

export function browseKey(query: BrowseQuery): string {
  return `${query.state ?? ''}|${query.language ?? ANY_LANGUAGE}|${query.q ?? ''}`;
}

interface BrowseState {
  key: string;
  items: Resource[];
  error: ApiError | null;
}

export interface BrowseResult {
  loading: boolean;
  items: Resource[];
  error: ApiError | null;
}

/** `GET /v1/resources` for "See all help" and the search box; the bundle when that fails. */
export function useBrowse(enabled: boolean, query: BrowseQuery): BrowseResult {
  const client = useApi();
  const key = enabled ? browseKey(query) : '';
  const [result, setResult] = useState<BrowseState | null>(null);
  const { state, language, q } = query;
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    const current: BrowseQuery = { state, language, q };
    listAll(client, current)
      .then((items) => {
        if (!cancelled) setResult({ key, items, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult({ key, items: bundledBrowse(current), error: toApiError(e) });
      });
    return () => {
      cancelled = true;
    };
  }, [client, key, state, language, q]);
  const current = result && result.key === key ? result : null;
  return { loading: Boolean(key) && !current, items: current?.items ?? [], error: current?.error ?? null };
}
