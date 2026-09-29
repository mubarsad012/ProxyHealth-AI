// The app's provider stack in one place (ARCHITECTURE §3 `_layout.tsx`): safe area, theme, i18n,
// direction, API config, storage. The root layout renders it; tests and feature packages can
// wrap screens with it (`<AppProviders client={fakeClient}>`).

import type { ReactNode } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ApiClient } from '@/api/client';
import { ApiConfigProvider } from '@/api/config';
import { ThemeProvider } from '@/design/theme';
import { DirectionProvider, I18nProvider } from '@/i18n/I18nProvider';
import type { Vault } from '@/storage/index';
import { StorageProvider } from '@/storage/StorageProvider';

const TEST_METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

export interface AppProvidersProps {
  children: ReactNode;
  /** Inject a client (tests, developer settings); defaults to the env-configured singleton. */
  client?: ApiClient;
  vault?: Vault;
  /** Tests: fixed safe-area metrics so nothing waits for native measurements. */
  staticMetrics?: boolean;
}

export function AppProviders({ children, client, vault, staticMetrics }: AppProvidersProps) {
  return (
    <SafeAreaProvider initialMetrics={staticMetrics ? TEST_METRICS : undefined}>
      <ThemeProvider>
        <I18nProvider>
          <DirectionProvider>
            <ApiConfigProvider client={client}>
              <StorageProvider value={vault}>{children}</StorageProvider>
            </ApiConfigProvider>
          </DirectionProvider>
        </I18nProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
