// S4 torch control (Phase 2B finding 8): a switch named "Light" (`capture.torch`) with its on/off
// state — not a button labelled with the "Too dark. Tap the light." instruction and an "info" glyph.

import { act, fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { AppProviders } from '@/design/components/Providers';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';

import { CaptureScreen, TORCH_LABEL_KEY } from './CaptureScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('expo-camera', () => ({
  CameraView: () => null,
  useCameraPermissions: () => [{ granted: true, canAskAgain: true, status: 'granted' }, jest.fn()],
}));
jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({}),
}));
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

const client = new Proxy({} as ApiClient, {
  get: (_t, prop) => (prop === 'baseUrl' ? 'http://127.0.0.1:8032' : () => Promise.reject(new Error('offline'))),
});

beforeEach(() => {
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
});

describe('<CaptureScreen> torch', () => {
  it('is a switch named by its own key, and its checked state follows the torch', async () => {
    const screen = await render(
      <AppProviders client={client} staticMetrics>
        <CaptureScreen />
      </AppProviders>,
    );
    const torch = screen.getByTestId('capture-torch');
    expect(torch.props.role).toBe('switch');
    // Merge step pending: until `capture.torch` is in en.json, t() returns the key itself.
    expect(torch.props.accessibilityLabel).toBe(t(TORCH_LABEL_KEY));
    expect(torch.props.accessibilityLabel).not.toBe(t('capture.guide_dark'));
    expect(torch.props.accessibilityState).toMatchObject({ checked: false });
    await act(async () => {
      fireEvent.press(torch);
    });
    expect(screen.getByTestId('capture-torch').props.accessibilityState).toMatchObject({ checked: true });
  });
});
