// Shell smoke test (BUILD_PLAN §5.5 template table, day 2): the provider stack renders a real WP4
// screen (Settings tab) in English with no network, and the S0 redirect lands on the `(tabs)`
// Home route with the JS tab bar. Home itself (`(tabs)/index.tsx`) is WP6's screen, so the router
// test mounts a placeholder for it.

import { render } from '@testing-library/react-native';
import { renderRouter } from 'expo-router/testing-library';
import type { ReactNode } from 'react';
import { Text } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import TabsLayout from '@/app/(tabs)/_layout';
import SettingsScreen from '@/app/(tabs)/settings';
import Index from '@/app/index';
import { AppProviders } from '@/design/components/Providers';
import { resetConsentState } from '@/features/onboarding/consentState';
import { consentStore } from '@/storage/consent';
import { useSettings } from '@/store/settings';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return {
    baseUrl: 'http://127.0.0.1:8026',
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
    fixturePageUrl: (id, n) => `http://127.0.0.1:8026/v1/demo/fixtures/${id}/pages/${n}`,
  };
}

describe('mobile shell smoke', () => {
  it('renders the Settings tab inside the provider stack, offline, in English', async () => {
    const { getByText, getByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <SettingsScreen />
      </AppProviders>,
    );
    expect(getByTestId('settings-screen')).toBeTruthy();
    expect(getByText('Language')).toBeTruthy();
    expect(getByText('How your paper is handled')).toBeTruthy();
    // Unreachable /v1/config → the badge says it cannot confirm how papers are handled.
    expect(getByTestId('tier-badge-unknown')).toBeTruthy();
    expect(getByText('Need help now?')).toBeTruthy();
  });
});

describe('S0 redirect into the tabs group', () => {
  it('"/" with a language and a consent decision lands on the (tabs) Home route', async () => {
    useSettings.setState({ hydrated: true, languageDecided: true, languageTag: 'en' });
    resetConsentState();
    await consentStore.setNotNow();
    const placeholder = (label: string) => {
      function Placeholder() {
        return <Text>{label}</Text>;
      }
      return Placeholder;
    };
    const screen = await renderRouter(
      {
        index: Index,
        '(tabs)/_layout': TabsLayout,
        '(tabs)/index': placeholder('Home screen'),
        '(tabs)/papers': placeholder('Papers screen'),
        '(tabs)/help': placeholder('Help screen'),
        '(tabs)/settings': placeholder('Settings screen'),
        'onboarding/language': placeholder('Language screen'),
        'onboarding/consent': placeholder('Consent screen'),
      },
      {
        initialUrl: '/',
        wrapper: ({ children }: { children: ReactNode }) => (
          <AppProviders client={offlineClient()} staticMetrics>
            {children}
          </AppProviders>
        ),
      },
    );
    expect(await screen.findByText('Home screen')).toBeTruthy();
    for (const tab of ['index', 'papers', 'help', 'settings']) expect(screen.getByTestId(`tab-${tab}`)).toBeTruthy();
    expect(screen.getByText('My papers')).toBeTruthy();
  });

  it('a first run that lands inside the tabs (deep link or "/") is sent to the language grid', async () => {
    useSettings.setState({ hydrated: true, languageDecided: false });
    resetConsentState();
    await consentStore.clear();
    const screen = await renderRouter(
      {
        '(tabs)/_layout': TabsLayout,
        '(tabs)/index': () => <Text>Home screen</Text>,
        '(tabs)/settings': () => <Text>Settings screen</Text>,
        'onboarding/language': () => <Text>Language screen</Text>,
      },
      {
        initialUrl: '/settings',
        wrapper: ({ children }: { children: ReactNode }) => (
          <AppProviders client={offlineClient()} staticMetrics>
            {children}
          </AppProviders>
        ),
      },
    );
    expect(await screen.findByText('Language screen')).toBeTruthy();
    expect(screen.queryByText('Settings screen')).toBeNull();
  });
});
