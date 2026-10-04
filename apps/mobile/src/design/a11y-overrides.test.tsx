// Phase 2C leftovers (CL-076(a), D-28): `BigButton` and `Tile` take an `accessibilityLabel` override
// (S11 "Call {organization}, {digits grouped}"), and the web theme follows the browser's
// `prefers-contrast: more` like the OS contrast flags on native.

import { act, render, renderHook } from '@testing-library/react-native';
import { Platform } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Tile } from '@/design/components/Tile';
import { useSystemHighContrast, webHighContrastQuery } from '@/design/theme';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

describe('accessibilityLabel overrides', () => {
  it('BigButton: the override replaces the visible label (+ sublabel); default unchanged', async () => {
    const { getByTestId } = await render(
      <>
        <BigButton testID="plain" label="Call 1-800-555-0100" variant="primary" size={56} onPress={() => {}} />
        <BigButton testID="sub" label="Scan" sublabel="Busy until 3:00" variant="primary" size={72} onPress={() => {}} />
        <BigButton
          testID="override"
          label="Call 1-800-555-0100"
          accessibilityLabel="Call 1-800-555-0100, Legal Aid, 1 800 555 0100"
          variant="primary"
          size={56}
          onPress={() => {}}
        />
      </>,
    );
    expect(getByTestId('plain').props.accessibilityLabel).toBe('Call 1-800-555-0100');
    expect(getByTestId('sub').props.accessibilityLabel).toBe('Scan. Busy until 3:00');
    expect(getByTestId('override').props.accessibilityLabel).toBe('Call 1-800-555-0100, Legal Aid, 1 800 555 0100');
  });

  it('BigButton: an empty override falls back to the visible label', async () => {
    const { getByTestId } = await render(
      <BigButton testID="b" label="Save" accessibilityLabel="" variant="secondary" size={56} onPress={() => {}} />,
    );
    expect(getByTestId('b').props.accessibilityLabel).toBe('Save');
  });

  it('Tile: override or the default "{title}. {line}"', async () => {
    const { getByTestId } = await render(
      <>
        <Tile testID="t1" title="Reminders" line="2 in the next 7 days" icon="calendar" onPress={() => {}} />
        <Tile testID="t2" title="Reminders" line="2 in the next 7 days" icon="calendar" accessibilityLabel="Reminders, 2 soon" onPress={() => {}} />
      </>,
    );
    expect(getByTestId('t1').props.accessibilityLabel).toBe('Reminders. 2 in the next 7 days');
    expect(getByTestId('t2').props.accessibilityLabel).toBe('Reminders, 2 soon');
  });
});

describe('web prefers-contrast: more', () => {
  type Listener = (e: { matches: boolean }) => void;

  function fakeMedia(initial: boolean) {
    const listeners = new Set<Listener>();
    const mq = {
      matches: initial,
      media: '(prefers-contrast: more)',
      addEventListener: (_: string, l: Listener) => listeners.add(l),
      removeEventListener: (_: string, l: Listener) => listeners.delete(l),
    };
    return {
      matchMedia: jest.fn((q: string) => {
        expect(q).toBe('(prefers-contrast: more)');
        return mq as unknown as MediaQueryList;
      }),
      set(matches: boolean) {
        mq.matches = matches;
        listeners.forEach((l) => l({ matches }));
      },
      listenerCount: () => listeners.size,
    };
  }

  const g = globalThis as unknown as { window?: { matchMedia?: unknown } };
  const realWindow = g.window;
  const realMatchMedia = realWindow?.matchMedia;

  afterEach(() => {
    jest.restoreAllMocks();
    if (realWindow) realWindow.matchMedia = realMatchMedia;
  });

  it('native: no media query is consulted', () => {
    expect(Platform.OS).not.toBe('web');
    expect(webHighContrastQuery({ matchMedia: fakeMedia(true).matchMedia })).toBeNull();
  });

  it('web: reads and follows the browser preference', async () => {
    jest.replaceProperty(Platform, 'OS', 'web');
    const media = fakeMedia(true);
    expect(webHighContrastQuery({ matchMedia: media.matchMedia })?.matches).toBe(true);
    expect(webHighContrastQuery({})).toBeNull();

    if (!g.window) g.window = {};
    g.window.matchMedia = media.matchMedia;
    const { result, unmount } = await renderHook(() => useSystemHighContrast());
    expect(result.current).toBe(true);
    await act(async () => {
      media.set(false);
    });
    expect(result.current).toBe(false);
    await unmount();
    expect(media.listenerCount()).toBe(0);
  });
});
