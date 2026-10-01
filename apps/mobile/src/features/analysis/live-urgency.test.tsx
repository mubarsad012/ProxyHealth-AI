// A paper reopened days after it was read (Phase 2B finding 1): the urgency banner re-counts the
// driving date against the device clock for REAL papers — a hearing that has passed flips to
// "This date may have passed … Contact them today", "{n} days ago" and "Verify this date" — while
// sample papers keep the server's count pinned to DEMO_AS_OF (PRODUCT_SPEC §12.3). Also covers
// finding 2's route guard: opening a stored paper drops a sample left over in the session.

import { render, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

import type { ApiClient } from '@/api/client';
import type { AnalysisResult, Urgency } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { UrgencyBanner } from '@/design/components/UrgencyBanner';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import type { StoredDocument, Vault } from '@/storage/index';
import { useSession } from '@/store/session';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import ntaEn from '../../../assets/fixtures/nta_hearing_date.result.en.json';
import { isLeftoverSample, useAnalysisFor } from './ResultScreen';
import { forgetSampleOrigins, rememberSampleOrigin, sampleIdForAnalysis } from './sampleOrigin';
import { liveUrgency, urgencySpeech, withLiveUrgency } from './urgencyCopy';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

/** A golden result turned into a real (non-sample) paper, as the vault would store it. */
function real(raw: unknown): AnalysisResult {
  const a = JSON.parse(JSON.stringify(raw)) as AnalysisResult;
  a.warnings = a.warnings.filter((w) => w !== 'demo_sample');
  a.model_meta = { ...a.model_meta, demo: false, provider: 'gemini', data_use_tier: 'paid' };
  return a;
}

function sample(raw: unknown): AnalysisResult {
  return JSON.parse(JSON.stringify(raw)) as AnalysisResult;
}

const day = (y: number, m: number, d: number) => new Date(y, m - 1, d, 15, 0, 0);

function isoDaysFromToday(n: number): string {
  const d = new Date();
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const p = (v: number) => String(v).padStart(2, '0');
  return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`;
}

beforeEach(() => {
  useI18n.getState().setPack(EN_PACK);
  useSession.getState().reset();
  forgetSampleOrigins();
});

describe('liveUrgency (real papers re-count their driving date)', () => {
  it('NTA hearing read 5 days before, reopened 3 days after: date passed, critical, verify CTA', async () => {
    const a = real(ntaEn); // nearest 2026-10-07, days_until 5, critical date_soon
    const u = liveUrgency(a, day(2026, 10, 10));
    expect(u).toMatchObject({ past_date: true, days_until: -3, level: 'critical', headline_key: 'urgency.critical.date_passed' });
    expect(u.verify_resource_id).toBe('eoir_hotline');
    const onVerify = jest.fn();
    const { getByText, queryByText } = await render(<UrgencyBanner urgency={u} onVerify={onVerify} onRemind={jest.fn()} />);
    expect(getByText('This date may have passed: ', { exact: false })).toBeTruthy();
    expect(getByText('3 days ago')).toBeTruthy();
    expect(queryByText('In 5 days')).toBeNull();
    expect(queryByText(t('btn.remind_me'))).toBeNull();
    expect(getByText(t('btn.verify_date'))).toBeTruthy();
    // Read-aloud says the same thing.
    expect(urgencySpeech(u, t)).toContain('3 days ago');
    expect(urgencySpeech(u, t)).not.toContain('In 5 days');
  });

  it('same day as the server count → the stored urgency object, unchanged', () => {
    const a = real(ntaEn);
    expect(liveUrgency(a, day(2026, 10, 2))).toBe(a.urgency);
    expect(withLiveUrgency(a, day(2026, 10, 2))).toBe(a);
  });

  it('the hearing is today → "is today" headline, still critical', () => {
    const u = liveUrgency(real(ntaEn), day(2026, 10, 7));
    expect(u).toMatchObject({ days_until: 0, past_date: false, level: 'critical', headline_key: 'urgency.critical.date_today' });
  });

  it('a nearer date raises the level by the server thresholds (critical set only for its roles)', () => {
    const nta = real(ntaEn);
    nta.urgency = { ...nta.urgency, level: 'medium', headline_key: 'urgency.medium.date_soon', days_until: 25 };
    expect(liveUrgency(nta, day(2026, 10, 3))).toMatchObject({ level: 'critical', days_until: 4 });
    const medicaid = real(medicaidEn); // response_due 2026-10-14, high, 12 days; not a critical-set role
    expect(liveUrgency(medicaid, day(2026, 10, 12))).toMatchObject({ level: 'high', days_until: 2, headline_key: 'urgency.high.date_soon' });
  });

  it('past on a benefits paper → the server past-date level (high for response_due)', () => {
    const u = liveUrgency(real(medicaidEn), day(2026, 10, 20));
    expect(u).toMatchObject({ past_date: true, days_until: -6, level: 'high', headline_key: 'urgency.critical.date_passed' });
  });

  it('never lowers the server level (a type floor stays) and keeps estimates at most medium', () => {
    const floored = real(medicaidEn);
    floored.urgency = { ...floored.urgency, level: 'high', floor_applied: true, days_until: 45, nearest_date_iso: '2026-11-16' };
    expect(liveUrgency(floored, day(2026, 10, 3))).toMatchObject({ level: 'high', floor_applied: true, days_until: 44 });

    const est = real(ntaEn);
    est.demands[0] = { ...est.demands[0], date: { ...(est.demands[0].date as NonNullable<AnalysisResult['demands'][0]['date']>), kind: 'estimated' } };
    est.urgency = { ...est.urgency, level: 'info', headline_key: 'urgency.medium.estimated', days_until: 40 } as Urgency;
    expect(liveUrgency(est, day(2026, 10, 3))).toMatchObject({ level: 'medium', headline_key: 'urgency.medium.estimated' });
  });

  it('sample papers and emergencies are never re-counted', () => {
    const s = sample(ntaEn);
    expect(liveUrgency(s, day(2026, 10, 10))).toBe(s.urgency);
    const e = real(ntaEn);
    e.urgency = { ...e.urgency, level: 'emergency', headline_key: 'urgency.emergency.headline' };
    expect(liveUrgency(e, day(2026, 10, 10))).toBe(e.urgency);
  });
});

// ---- useAnalysisFor: the route hook every /result/<id> screen uses ----

function vaultWith(doc: StoredDocument | null): Vault {
  const none = () => Promise.resolve();
  return {
    init: none,
    members: { list: async () => [], add: jest.fn(), rename: none, remove: none },
    documents: { list: async () => [], get: async (id: string) => (doc && doc.id === id ? doc : null), save: none, move: none, remove: none, search: async () => [] },
    pages: { list: async () => [], uri: async () => null },
    checklist: { get: async () => ({}), set: none },
    reminders: { list: async () => [], add: jest.fn(), remove: none, setEnabled: none },
    consent: { get: async () => null, set: none, clear: none },
    wipeAll: none,
  } as unknown as Vault;
}

const client = new Proxy({} as ApiClient, {
  get: (_t, prop) => (prop === 'baseUrl' ? 'http://127.0.0.1:8027' : () => Promise.reject(new Error('offline'))),
});

function Probe({ id }: { id: string }) {
  const { analysis } = useAnalysisFor(id);
  return (
    <>
      <Text>{analysis ? analysis.urgency.headline_key : 'none'}</Text>
      <Text testID="probe-urgency">{JSON.stringify(analysis?.urgency ?? null)}</Text>
    </>
  );
}

function probedUrgency(node: { props: { children?: unknown } }): Urgency {
  return JSON.parse(String(node.props.children)) as Urgency;
}

describe('useAnalysisFor', () => {
  it('a stored real paper whose date has passed opens with the "may have passed" urgency', async () => {
    const a = real(ntaEn);
    a.urgency = { ...a.urgency, nearest_date_iso: isoDaysFromToday(-3), days_until: 5 };
    const doc = { id: a.analysis_id, memberId: 'me', title: 'x', category: a.category, documentType: a.document_type, createdAt: '', nextDateIso: null, pageCount: 1, analysis: a, keepPages: false } as StoredDocument;
    const { findByText, getByTestId } = await render(
      <AppProviders client={client} vault={vaultWith(doc)} staticMetrics>
        <Probe id={a.analysis_id} />
      </AppProviders>,
    );
    expect(await findByText('urgency.critical.date_passed')).toBeTruthy();
    expect(probedUrgency(getByTestId('probe-urgency'))).toMatchObject({ past_date: true, days_until: -3, level: 'critical' });
  });

  it('opening a stored paper drops a sample left over in the session (pages + demoSampleId)', async () => {
    const a = real(medicaidEn);
    const doc = { id: 'doc_real', memberId: 'me', title: 'x', category: a.category, documentType: a.document_type, createdAt: '', nextDateIso: null, pageCount: 1, analysis: { ...a, analysis_id: 'doc_real' }, keepPages: false } as StoredDocument;
    useSession.getState().setDemoSampleId('medicaid_address_confirmation');
    useSession.getState().setPages([{ id: 's1', uri: 'http://x/p1.png', mimeType: 'image/png', rotation: 0, masks: [], source: 'sample' }]);
    await render(
      <AppProviders client={client} vault={vaultWith(doc)} staticMetrics>
        <Probe id="doc_real" />
      </AppProviders>,
    );
    await waitFor(() => expect(useSession.getState().demoSampleId).toBeNull());
    expect(useSession.getState().pages).toEqual([]);
  });

  it('keeps the sample state for the sample result it produced', async () => {
    const s = sample(medicaidEn);
    rememberSampleOrigin(s.analysis_id, 'medicaid_address_confirmation');
    useSession.getState().setDemoSampleId('medicaid_address_confirmation');
    useSession.getState().setCurrentAnalysis(s);
    const { findByText } = await render(
      <AppProviders client={client} vault={vaultWith(null)} staticMetrics>
        <Probe id={s.analysis_id} />
      </AppProviders>,
    );
    expect(await findByText(s.urgency.headline_key)).toBeTruthy();
    expect(useSession.getState().demoSampleId).toBe('medicaid_address_confirmation');
  });
});

describe('isLeftoverSample / sampleIdForAnalysis', () => {
  it('only a sample result this session made carries its fixture id', () => {
    const s = sample(medicaidEn);
    expect(sampleIdForAnalysis(s)).toBeNull(); // not recorded → treated as real (safe side)
    rememberSampleOrigin(s.analysis_id, 'medicaid_address_confirmation');
    expect(sampleIdForAnalysis(s)).toBe('medicaid_address_confirmation');
    // A real paper never gets one, even if an id were recorded for its analysis_id.
    const r = real(medicaidEn);
    expect(sampleIdForAnalysis(r)).toBeNull();
    expect(isLeftoverSample(s, true, 'medicaid_address_confirmation')).toBe(false);
    expect(isLeftoverSample(s, false, 'medicaid_address_confirmation')).toBe(true);
    expect(isLeftoverSample(r, true, 'medicaid_address_confirmation')).toBe(true);
    expect(isLeftoverSample(r, true, null)).toBe(false);
  });
});
