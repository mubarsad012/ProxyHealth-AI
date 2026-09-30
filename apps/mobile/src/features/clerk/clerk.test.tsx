// Clerk mode (D-18, PRODUCT_SPEC §8) and the S19 emergency card (D-14). Clerk: the card is LTR
// English at ≥ 24 pt on the high-contrast palette even when the UI pack is RTL; clerk mode is on
// while the screen is shown; "Back to me" exits only after a 1.5 s hold (release early cancels);
// the interpreter line is appended only when the server listed it. Emergency: fixed rows with
// tel:/sms: links, the context line from `emergency_kinds`, trigger derivation biased to fire.

import { act, fireEvent, render } from '@testing-library/react-native';
import { Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { AnalysisResult } from '@/api/types';
import { ThemeProvider } from '@/design/theme';
import { palette } from '@/design/tokens';
import { EMERGENCY_ROWS, EmergencyCard, emergencyTrigger } from '@/features/emergency';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';

import { ClerkScreen, splitGreeting } from './ClerkScreen';
import { clerkCardFromAnalysis, genericClerkCard } from './clerkModel';
import { LongPressExit } from './LongPressExit';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
}));

let mockScheme: 'light' | 'dark' = 'light';
jest.mock('@/hooks/use-color-scheme', () => ({ useColorScheme: () => mockScheme }));

const clerkMessage = {
  english: 'Hello. I speak Dari. I am here about: a Virginia Medicaid letter asking me to confirm my address. Thank you.',
  translated: 'سلام. من دری صحبت می‌کنم.',
  need_line_source: 'ai' as const,
  appended_line_keys: ['clerk.interpreter_hhs', 'not.a.real.key'],
};

const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };

function flatStyle(style: unknown): Record<string, unknown> {
  return Object.assign({}, ...([style].flat(Infinity as 1).filter(Boolean) as object[]));
}

afterEach(() => {
  mockScheme = 'light';
  useI18n.getState().setPack(EN_PACK);
  useSession.getState().reset();
});

describe('clerk card model', () => {
  it('uses the server English card plus only allowed appended lines, in English', () => {
    const card = clerkCardFromAnalysis({ clerk_message: clerkMessage }, t);
    expect(card.english).toEqual([clerkMessage.english, 'I may ask for a free interpreter.']);
  });

  it('generic card: fixed English template, preset or own words, never an interpreter line', () => {
    const pack = bundledPackFor('prs');
    if (pack) useI18n.getState().setPack(pack);
    const preset = genericClerkCard('prs', { kind: 'preset', preset: 'bill' }, t);
    expect(preset.english[0]).toBe('Hello. I speak Dari. I need help with: a bill. Please speak slowly or write it down. Thank you.');
    const own = genericClerkCard('prs', { kind: 'own', text: 'my son’s school form' }, t);
    expect(own.english[0]).toContain('I need help with: my son’s school form.');
    expect(own.ownWords).toBe(true);
    expect(own.english.join(' ')).not.toContain('interpreter');
  });

  it('splits the greeting for the 32 pt line', () => {
    expect(splitGreeting(clerkMessage.english)[0]).toBe('Hello. I speak Dari.');
  });
});

describe('<ClerkScreen>', () => {
  it('renders LTR, ≥ 24 pt, high contrast in an RTL UI and turns clerk mode on', async () => {
    const pack = bundledPackFor('prs');
    if (pack) useI18n.getState().setPack(pack);
    const { getByText, getByTestId } = await render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <ClerkScreen analysis={{ clerk_message: clerkMessage } as unknown as AnalysisResult} />
      </SafeAreaProvider>,
    );
    expect(useSession.getState().clerkMode).toBe(true);
    const greeting = flatStyle(getByText('Hello. I speak Dari.').props.style);
    expect(greeting.fontSize).toBeGreaterThanOrEqual(32);
    const body = flatStyle(getByText('I may ask for a free interpreter.').props.style);
    expect(body.fontSize).toBeGreaterThanOrEqual(24);
    expect(body.writingDirection).toBe('ltr');
    expect(body.textAlign).toBe('left');
    expect(body.color).toBe(palette.highContrast.text);
    expect(flatStyle(getByTestId('clerk-screen').props.style).backgroundColor).toBe(palette.highContrast.background);
    expect(getByText(t('clerk.brightness_tip'))).toBeTruthy();
  });

  it('keeps "What this card says" black on white in the dark colour scheme', async () => {
    mockScheme = 'dark';
    const { getByText, getByRole } = await render(
      <ThemeProvider>
        <SafeAreaProvider initialMetrics={METRICS}>
          <ClerkScreen analysis={{ clerk_message: clerkMessage } as unknown as AnalysisResult} />
        </SafeAreaProvider>
      </ThemeProvider>,
    );
    const title = t('clerk.what_it_says');
    expect(flatStyle(getByText(title).props.style).color).toBe(palette.highContrast.text);
    await act(async () => {
      fireEvent.press(getByRole('button', { name: title }));
    });
    expect(flatStyle(getByText(clerkMessage.translated, { exact: false }).props.style).color).toBe(palette.highContrast.text);
  });
});

describe('<LongPressExit>', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('exits only after a 1.5 s hold; an early release cancels', async () => {
    const onExit = jest.fn();
    const { getByTestId } = await render(<LongPressExit onExit={onExit} />);
    const btn = getByTestId('clerk-exit');
    await fireEvent(btn, 'pressIn');
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    await fireEvent(btn, 'pressOut');
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    expect(onExit).not.toHaveBeenCalled();
    await fireEvent(btn, 'pressIn');
    await act(async () => {
      jest.advanceTimersByTime(1400);
    });
    expect(onExit).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(200);
    });
    expect(onExit).toHaveBeenCalledTimes(1);
  });

  it('the accessibility "activate" action runs the same timer', async () => {
    const onExit = jest.fn();
    const { getByTestId } = await render(<LongPressExit onExit={onExit} />);
    await fireEvent(getByTestId('clerk-exit'), 'accessibilityAction', { nativeEvent: { actionName: 'activate' } });
    await act(async () => {
      jest.advanceTimersByTime(1600);
    });
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});

describe('emergency card', () => {
  it('derives the trigger (over-triggers on kinds alone)', () => {
    expect(emergencyTrigger(null).triggered).toBe(false);
    expect(emergencyTrigger({ emergency: false, emergency_kinds: ['overdose'], credential_or_payment_request: false }).triggered).toBe(true);
    expect(emergencyTrigger({ emergency: true, emergency_kinds: [], credential_or_payment_request: false }).triggered).toBe(true);
  });

  it('renders the four fixed rows with tel:/sms: links and the context line', async () => {
    const open = jest.spyOn(Linking, 'openURL').mockResolvedValue(true);
    const onClose = jest.fn();
    const { getByText, getByTestId, queryByText } = await render(
      <EmergencyCard kinds={['chest_pain', 'made_up_kind']} triggered onClose={onClose} />,
    );
    for (const row of EMERGENCY_ROWS) expect(getByTestId(`emergency-row-${row.id}`)).toBeTruthy();
    expect(getByText(t('emergency.triggered_by', { kinds: 'chest pain' }))).toBeTruthy();
    expect(queryByText('made_up_kind', { exact: false })).toBeNull();
    await fireEvent.press(getByText(t('btn.call_911')));
    expect(open).toHaveBeenCalledWith('tel:911');
    await fireEvent.press(getByText(t('btn.text_988')));
    expect(open).toHaveBeenCalledWith('sms:988');
    await fireEvent.press(getByText(t('btn.close')));
    expect(onClose).toHaveBeenCalled();
  });
});
