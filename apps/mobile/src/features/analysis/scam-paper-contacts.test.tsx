// DOCUMENT_TAXONOMY §6.4 on the result screen: on a paper scored a possible or likely scam nothing
// sends the reader to a contact the paper prints. Integration review issue 12: a small model's
// block-id contact demand verified after repair, the re-typed paper had no agency verify line, and
// "Verify this date" fell back to the first printed phone — the scammer's. Neither that fallback,
// nor the demand row's "Call (number from your paper)", nor "Confirm … with the sender" appears on
// a scam paper; a real paper keeps all three.

import { fireEvent, render, within } from '@testing-library/react-native';

import type { AnalysisResult, Demand } from '@/api/types';
import { EN_PACK, t, useI18n } from '@/i18n/store';

import scamEn from '../../../assets/fixtures/scam_gift_card_letter.result.en.json';
import { footerKeys, isScamPaper } from './disclaimers';
import { hearItItems } from './hearItMode';
import { ResultView } from './ResultView';
import { firstPrintedPhone, paperPhoneHref } from './urgencyCopy';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const SCAMMER = '(202) 555-0147';

/** The scam sample plus what a small model's repaired demands gave: the officer's printed phone
 *  as a verified contact demand and a verified pay-by date driving the banner, no verify target
 *  (an older server). */
function withPrintedContact(risk: AnalysisResult['scam_risk']): AnalysisResult {
  const a = JSON.parse(JSON.stringify(scamEn)) as AnalysisResult;
  const base = a.demands[0];
  const contact: Demand = {
    ...base,
    id: 'd2',
    kind: 'contact',
    role: 'other',
    text: 'Call the officer.',
    value_verbatim: SCAMMER,
    source_quote: `Call Officer Daniel Sample at ${SCAMMER} and read the gift card numbers over the phone.`,
    verified: true,
    reminder_eligible: false,
    date: null,
  };
  const due: Demand = {
    ...base,
    id: 'd3',
    kind: 'deadline',
    role: 'payment_due',
    text: 'Pay by October 25, 2026.',
    value_verbatim: 'October 25, 2026',
    source_quote: 'Pay by October 25, 2026 with Google Play gift cards or you will be deported.',
    verified: true,
    reminder_eligible: true,
    date: {
      kind: 'estimated',
      value_iso: '2026-10-25',
      time_text: null,
      formula: 'printed date',
      anchor_quote: null,
      anchor_demand_id: null,
      rule_id: null,
      rule_source_url: null,
      rule_verification: null,
      localized_line: 'October 25, 2026',
    },
  };
  a.demands = [...a.demands, contact, due];
  a.scam_risk = risk;
  a.is_likely_scam = risk === 'likely';
  a.urgency = {
    ...a.urgency,
    level: 'high',
    headline_key: 'urgency.high.date_soon',
    headline_params: { date: 'October 25, 2026' },
    driving_demand_id: 'd3',
    nearest_date_iso: '2026-10-25',
    days_until: 3,
    past_date: false,
    verify_resource_id: null,
  };
  return a;
}

const handlers = () => ({ onCall: jest.fn(), onVerifyResource: jest.fn(), onRemind: jest.fn() });

beforeEach(() => useI18n.getState().setPack(EN_PACK));

describe.each(['likely', 'possible'] as const)('a %s scam paper', (risk) => {
  it('offers no call to the printed phone and no "Verify this date" fallback to it', async () => {
    const a = withPrintedContact(risk);
    expect(isScamPaper(a)).toBe(true);
    expect(firstPrintedPhone(a)).toBeNull();
    expect(paperPhoneHref(a, a.demands.find((d) => d.id === 'd2') as Demand)).toBeNull();
    const h = handlers();
    const { queryByText, getByTestId } = await render(<ResultView analysis={a} pages={[]} handlers={h} />);
    expect(queryByText(t('btn.call_printed'))).toBeNull();
    expect(queryByText(t('btn.verify_date'))).toBeNull();
    expect(within(getByTestId('demand-d3')).queryByText(t('demand.confirm_with_sender'))).toBeNull();
    expect(within(getByTestId('result-footer')).queryByText(t('footer.verify_with_sender'))).toBeNull();
    expect(within(getByTestId('result-footer')).getByText(t('footer.ai_generated'))).toBeTruthy();
    expect(h.onCall).not.toHaveBeenCalled();
  });

  it('"Verify this date" opens the vetted reporting line the server sets', async () => {
    const a = withPrintedContact(risk);
    a.urgency = { ...a.urgency, verify_resource_id: 'dhs_oig' };
    const h = handlers();
    const { getByText } = await render(<ResultView analysis={a} pages={[]} handlers={h} />);
    await fireEvent.press(getByText(t('btn.verify_date')));
    expect(h.onVerifyResource).toHaveBeenCalledWith('dhs_oig');
    expect(h.onCall).not.toHaveBeenCalled();
  });

  it('hear-it mode leaves out "Confirm dates and amounts with the sender"', () => {
    const a = withPrintedContact(risk);
    expect(footerKeys(a)).toEqual(['footer.ai_generated']);
    const footer = hearItItems(a, t, 'en', false).find((i) => i.id === 'footer');
    expect(footer?.text).toBe(t('footer.ai_generated'));
  });
});

describe('a paper scored none', () => {
  it('keeps the printed-phone call, the verify fallback and the sender lines', async () => {
    const a = withPrintedContact('none');
    expect(firstPrintedPhone(a)).toBe('tel:2025550147');
    const h = handlers();
    const { getByText, getAllByText, getByTestId } = await render(<ResultView analysis={a} pages={[]} handlers={h} />);
    expect(getAllByText(t('btn.call_printed')).length).toBe(1);
    expect(within(getByTestId('demand-d3')).getByText(t('demand.confirm_with_sender'))).toBeTruthy();
    expect(within(getByTestId('result-footer')).getByText(t('footer.verify_with_sender'))).toBeTruthy();
    await fireEvent.press(getByText(t('btn.verify_date')));
    expect(h.onCall).toHaveBeenCalledWith('tel:2025550147');
    expect(footerKeys(a)).toEqual(['footer.ai_generated', 'footer.verify_with_sender']);
  });
});
