// S19 phone numbers in RTL packs (Phase 2B finding 4): the hotline numbers inside the fixed
// Arabic / Dari / Pashto lines are LTR-isolated, so bidi rule W2 cannot reorder their digit groups
// ("1222-222-800-1"); the SMS buttons no longer wear the "info" glyph (finding 8).

import { render } from '@testing-library/react-native';

import { LRI, PDI, stripIsolates } from '@/design/components/Bidi';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';

import { EMERGENCY_ROWS, EmergencyCard, phoneParts } from './EmergencyCard';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

afterEach(() => useI18n.getState().setPack(EN_PACK));

function flatText(node: unknown): string {
  if (node === null || node === undefined) return '';
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(flatText).join('');
  return flatText((node as { children?: unknown }).children);
}

describe('phoneParts', () => {
  it('splits hyphenated numbers out of a line and leaves the rest', () => {
    expect(phoneParts('call 1-800-799-7233 or text START to 88788.')).toEqual([
      { text: 'call ', phone: false },
      { text: '1-800-799-7233', phone: true },
      { text: ' or text START to 88788.', phone: false },
    ]);
    expect(phoneParts('call 911')).toEqual([{ text: 'call 911', phone: false }]);
  });
});

describe.each(['ar', 'prs', 'ps'])('EmergencyCard in %s', (tag) => {
  it('isolates every hotline number in the poison and domestic-violence lines', async () => {
    const pack = bundledPackFor(tag);
    if (!pack) throw new Error(`${tag} pack not bundled`);
    useI18n.getState().setPack(pack);
    const { getByTestId } = await render(<EmergencyCard kinds={[]} onClose={jest.fn()} />);
    for (const [id, key, number] of [
      ['poison', 'emergency.poison', '1-800-222-1222'],
      ['dv', 'emergency.dv', '1-800-799-7233'],
    ] as const) {
      const line = t(key);
      expect(line).toContain(number); // the pack string itself carries the number
      const shown = flatText(getByTestId(`emergency-line-${id}`));
      expect(shown).toContain(`${LRI}${number}${PDI}`);
      expect(stripIsolates(shown)).toBe(line);
    }
  });
});

describe('EMERGENCY_ROWS', () => {
  it('call buttons dial with the phone glyph; text buttons are sms: and never the "info" glyph', () => {
    for (const row of EMERGENCY_ROWS) {
      for (const a of row.actions) {
        if (a.kind === 'call') expect(a.href.startsWith('tel:')).toBe(true);
        else expect(a.href.startsWith('sms:')).toBe(true);
        expect(a).not.toHaveProperty('icon');
      }
    }
  });
});
