// Urgency banner (PRODUCT_SPEC §5.5, D-12): every level renders icon + word + colour (never colour
// alone), the headline from `headline_key` with `{date}` LTR-isolated, the days line, the floor
// note, and the CTA rules (past date → "Verify this date" primary; no "Remind me" on a past date).

import { fireEvent, render } from '@testing-library/react-native';

import type { Urgency, UrgencyLevel } from '@/api/types';
import { LRI, PDI } from '@/design/components/Bidi';
import { UrgencyBanner } from '@/design/components/UrgencyBanner';
import { palette, urgency as urgencyTokens } from '@/design/tokens';
import { EN_PACK, t, useI18n } from '@/i18n/store';

import { urgencySpeech } from './urgencyCopy';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function u(level: UrgencyLevel, patch: Partial<Urgency> = {}): Urgency {
  const headline: Record<UrgencyLevel, string> = {
    emergency: 'urgency.emergency.headline',
    critical: 'urgency.critical.date_soon',
    high: 'urgency.high.date_soon',
    medium: 'urgency.medium.date_soon',
    info: 'urgency.info.date_later',
  };
  return {
    level,
    headline_key: headline[level],
    headline_params: { date: 'October 14, 2026' },
    driving_demand_id: 'd1',
    nearest_date_iso: '2026-10-14',
    days_until: 5,
    past_date: false,
    floor_applied: false,
    verify_resource_id: null,
    ...patch,
  };
}

function flatStyles(node: unknown, out: Record<string, unknown>[] = []): Record<string, unknown>[] {
  if (!node) return out;
  if (Array.isArray(node)) {
    for (const n of node) flatStyles(n, out);
    return out;
  }
  const n = node as { props?: { style?: unknown; name?: unknown }; children?: unknown };
  const style = n.props?.style;
  for (const s of [style].flat(Infinity as 1)) if (s && typeof s === 'object') out.push(s as Record<string, unknown>);
  if (n.children) flatStyles(n.children, out);
  return out;
}

beforeEach(() => useI18n.getState().setPack(EN_PACK));

describe.each(['emergency', 'critical', 'high', 'medium', 'info'] as UrgencyLevel[])('UrgencyBanner level %s', (level) => {
  it('shows the word, the icon colour and the headline with the date isolated', async () => {
    const { getByText, getByLabelText, toJSON } = await render(<UrgencyBanner urgency={u(level)} />);
    const token = urgencyTokens[level];
    const word = t(token.wordKey);
    expect(getByText(word)).toBeTruthy();
    expect(getByLabelText(word)).toBeTruthy();
    expect(JSON.stringify(toJSON())).toContain('"role":"alert"');
    const colors = flatStyles(toJSON()).map((s) => s.borderColor ?? s.color);
    expect(colors).toContain(token.color.light);
    if (level !== 'emergency') {
      expect(getByText(`${LRI}October 14, 2026${PDI}`, { exact: false })).toBeTruthy();
    }
    expect(getByText('In 5 days')).toBeTruthy();
  });

  it('speaks word + headline for read-aloud', () => {
    const text = urgencySpeech(u(level), t);
    expect(text.startsWith(t(urgencyTokens[level].wordKey))).toBe(true);
    expect(text).toContain('In 5 days');
  });
});

describe('UrgencyBanner rules', () => {
  it('uses a distinct icon for every level (icon + word + colour, never colour alone)', () => {
    const icons = new Set(Object.values(urgencyTokens).map((tk) => tk.icon));
    expect(icons.size).toBe(5);
    const words = new Set(Object.values(urgencyTokens).map((tk) => t(tk.wordKey)));
    expect(words.size).toBe(5);
    for (const tk of Object.values(urgencyTokens)) expect(tk.color.light).not.toBe(palette.light.background);
  });

  it('past date → "may have passed" headline, days-ago line, verify CTA and no reminder', async () => {
    const onVerify = jest.fn();
    const onRemind = jest.fn();
    const { getByText, queryByText } = await render(
      <UrgencyBanner urgency={u('critical', { past_date: true, days_until: -3 })} onVerify={onVerify} onRemind={onRemind} />,
    );
    expect(getByText('3 days ago')).toBeTruthy();
    expect(getByText('This date may have passed: ', { exact: false })).toBeTruthy();
    expect(queryByText(t('btn.remind_me'))).toBeNull();
    await fireEvent.press(getByText(t('btn.verify_date')));
    expect(onVerify).toHaveBeenCalledTimes(1);
  });

  it('floor note and remind CTA', async () => {
    const onRemind = jest.fn();
    const { getByText } = await render(
      <UrgencyBanner
        urgency={u('high', { headline_key: 'urgency.high.floor', headline_params: {}, days_until: null, floor_applied: true })}
        onRemind={onRemind}
      />,
    );
    expect(getByText(t('urgency.floor_note'))).toBeTruthy();
    await fireEvent.press(getByText(t('btn.remind_me')));
    expect(onRemind).toHaveBeenCalledTimes(1);
  });

  it('shows no CTA when no handler is given', async () => {
    const { queryByText } = await render(<UrgencyBanner urgency={u('medium')} />);
    expect(queryByText(t('btn.remind_me'))).toBeNull();
    expect(queryByText(t('btn.verify_date'))).toBeNull();
  });
});
