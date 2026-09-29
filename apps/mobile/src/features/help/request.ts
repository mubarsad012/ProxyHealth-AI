// Match requests, the per-document cache and the bundled offline fallbacks (PRODUCT_SPEC S11,
// RESOURCE_DB §6.9 / §7, ARCHITECTURE §3.1 "Offline behaviors"). Resources only ever come from the
// vetted DB: the server response, or its synced subset in `assets/resources/national_fallbacks.json`.
// The cache lives in memory only — nothing about a paper is written to the device by this module.

import type {
  AnalysisResult,
  Resource,
  ResourceMatch,
  ResourceMatchRequest,
  ResourceMatchResponse,
  ResourceTag,
  ScamRisk,
} from '@/api/types';

import { HEALTH_GROUP, IMMIGRATION_GROUP } from './needs';

export interface Region {
  state: string | null;
  zip3: string | null;
}

export const MATCH_LIMIT = 8;
const MAX_TAGS = 12;
const MAX_INSTITUTIONS = 10;
/** Used only when a paper carries no routing tag at all: 211-style general help. */
export const GENERIC_TAG: ResourceTag = 'benefits_navigation';

function uniqTags(tags: readonly ResourceTag[]): ResourceTag[] {
  return Array.from(new Set(tags)).slice(0, MAX_TAGS);
}

/** Tags for one paper: `resource_tags`, then plan-step tags, else the generic tag. */
export function tagsForAnalysis(analysis: AnalysisResult): ResourceTag[] {
  const tags = [...(analysis.resource_tags ?? [])];
  for (const step of analysis.plan_steps ?? []) tags.push(...(step.resource_tags ?? []));
  if (analysis.scam_risk === 'likely') tags.unshift('scam_report');
  const out = uniqTags(tags);
  return out.length ? out : [GENERIC_TAG];
}

export function buildMatchRequestForAnalysis(
  analysis: AnalysisResult,
  opts: { region: Region; language: string; tags?: ResourceTag[] | null },
): ResourceMatchRequest {
  const tags = opts.tags && opts.tags.length ? uniqTags(opts.tags) : tagsForAnalysis(analysis);
  return {
    tags,
    document_type: analysis.document_type ?? null,
    category: analysis.category ?? null,
    // Where the person lives (Settings) wins; the paper's own state is the fallback hint.
    state: opts.region.state ?? analysis.entities?.geo?.state ?? null,
    county: null,
    zip3: opts.region.state ? opts.region.zip3 : null,
    language: opts.language,
    institutions_as_written: (analysis.entities?.institutions_as_written ?? []).slice(0, MAX_INSTITUTIONS),
    scam_risk: analysis.scam_risk ?? 'none',
    emergency: Boolean(analysis.safety?.emergency),
    limit: MATCH_LIMIT,
  };
}

export function buildMatchRequestForTags(
  tags: readonly ResourceTag[],
  opts: { region: Region; language: string; scamRisk?: ScamRisk; emergency?: boolean },
): ResourceMatchRequest | null {
  const unique = uniqTags(tags);
  if (!unique.length) return null;
  return {
    tags: unique,
    document_type: null,
    category: null,
    state: opts.region.state,
    county: null,
    zip3: opts.region.state ? opts.region.zip3 : null,
    language: opts.language,
    institutions_as_written: [],
    scam_risk: opts.scamRisk ?? (unique.includes('scam_report') ? 'possible' : 'none'),
    emergency: Boolean(opts.emergency),
    limit: MATCH_LIMIT,
  };
}

/** Stable cache key (tag order does not matter). */
export function matchKey(req: ResourceMatchRequest): string {
  return JSON.stringify({
    ...req,
    tags: [...req.tags].sort(),
    institutions_as_written: [...(req.institutions_as_written ?? [])].sort(),
  });
}

// --- per-document memory cache -------------------------------------------------------------------

const byKey = new Map<string, ResourceMatchResponse>();
const byDocument = new Map<string, ResourceMatchResponse>();

export function cachedMatch(req: ResourceMatchRequest): ResourceMatchResponse | null {
  return byKey.get(matchKey(req)) ?? null;
}

export function rememberMatch(req: ResourceMatchRequest, res: ResourceMatchResponse, documentId?: string | null): void {
  byKey.set(matchKey(req), res);
  if (documentId) byDocument.set(documentId, res);
}

/** The last list found for this paper (any region), for the quick sheet and the offline state. */
export function lastMatchForDocument(documentId: string | null | undefined): ResourceMatchResponse | null {
  return documentId ? (byDocument.get(documentId) ?? null) : null;
}

export function clearMatchCache(): void {
  byKey.clear();
  byDocument.clear();
}

// --- bundled offline subset ----------------------------------------------------------------------

const BUNDLED: Resource[] = require('../../../assets/resources/national_fallbacks.json');

export function bundledResources(): Resource[] {
  return BUNDLED.filter((r) => r.link_health !== 'broken');
}

function byId(id: string): Resource | null {
  return bundledResources().find((r) => r.id === id) ?? null;
}

/** RESOURCE_DB §6.9 order, from the bundle, de-duplicated against `exclude`. */
export function offlineFallbacksFor(req: ResourceMatchRequest, exclude: ReadonlySet<string> = new Set()): Resource[] {
  const ids: string[] = [];
  if (req.emergency || req.tags.includes('crisis')) ids.push('988');
  if (req.tags.includes('domestic_violence')) ids.push('dv_hotline');
  if (req.tags.includes('trafficking')) ids.push('trafficking');
  if (req.tags.includes('poison')) ids.push('poison');
  if (req.scam_risk !== 'none' || req.tags.includes('scam_report')) ids.push('ftc_reportfraud', 'dhs_oig');
  ids.push('211');
  if (req.tags.some((t) => IMMIGRATION_GROUP.has(t))) ids.push('immlawhelp');
  if (req.tags.some((t) => HEALTH_GROUP.has(t))) ids.push('hrsa_fqhc');
  const out: Resource[] = [];
  const seen = new Set(exclude);
  for (const id of ids) {
    const r = byId(id);
    if (r && !seen.has(r.id)) {
      seen.add(r.id);
      out.push(r);
    }
  }
  return out;
}

function asMatch(resource: Resource): ResourceMatch {
  return {
    resource,
    score: 0,
    why_keys: ['why.anywhere_in_us'],
    why: [],
    eligibility_note_key: resource.status_note_key ?? null,
    checklist: (resource.prepare_checklist_keys ?? []).map((key) => ({ key, text_en: '' })),
  };
}

/** What the Help screen shows with no server: bundled entries for these tags + the fallbacks. */
export function offlineMatchResponse(req: ResourceMatchRequest): ResourceMatchResponse {
  const fallbacks = offlineFallbacksFor(req);
  const fallbackIds = new Set(fallbacks.map((r) => r.id));
  const results = bundledResources()
    .filter((r) => !fallbackIds.has(r.id) && r.tags.some((t) => req.tags.includes(t)))
    .filter((r) => !r.never_show_with_tags?.some((t) => req.tags.includes(t)))
    .sort((a, b) => b.priority - a.priority)
    .slice(0, req.limit)
    .map(asMatch);
  return {
    results,
    national_fallbacks: fallbacks,
    notes_keys: ['notes.verify_before_going'],
    disclaimer_kind: 'general_information',
    resource_db_version: 'bundled',
  };
}
