// Settings → About names the server's helper by provider (the mock has no model: sample-mode line,
// not the Gemini ids it still reports), and the developer options exist only outside production
// builds, collapsed until opened. New keys (`settings.model_single`, `settings.developer_options`)
// are merged into en.json later, so nothing here asserts their English text.

import { fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { resetServerConfigSession } from '@/api/config';
import { ApiError } from '@/api/errors';
import type { ServerConfig } from '@/api/types';
import SettingsScreen from '@/app/(tabs)/settings';
import { AppProviders } from '@/design/components/Providers';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import { kv } from '@/storage/kv';
import { useSession } from '@/store/session';

import { AboutSection, DeveloperSection, helperModelsLine } from './SettingsSections';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

let mockProduction = false;
jest.mock('@/lib/platform', () => {
  const mocked = { ...jest.requireActual('@/lib/platform') };
  // A getter (not a spread value) so each test can flip the build type before rendering.
  Object.defineProperty(mocked, 'isProduction', { get: () => mockProduction, enumerable: true });
  return mocked;
});

const API_URL = 'http://127.0.0.1:8026';

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({} as ApiClient, {
    get: (_t, prop) => (prop === 'baseUrl' ? API_URL : fail),
  });
}

function config(overrides: Partial<ServerConfig> = {}): ServerConfig {
  return {
    api_version: '0.1.0',
    contract_version: 1,
    provider: 'mock',
    data_use_tier: 'demo',
    models: { fast: 'gemini-3.5-flash-lite', pro: 'gemini-3.8-flash', pro_degraded_thinking: 'medium' },
    features: {} as ServerConfig['features'],
    limits: {} as ServerConfig['limits'],
    consent_version: '2026-10-04',
    privacy_policy_url: 'https://proxyhealth.expo.app/privacy',
    base_pack_version: 'base',
    languages: [],
    taxonomy_version: 't',
    resource_db_version: 'r',
    rules_version: 'rv',
    key_slots: { total: 0, healthy: 0, cooling: 0, rpd_exhausted: 0, disabled: 0 },
    region_notice: 'us_only',
    server_time: '2026-09-27T00:00:00Z',
    ai_model_label: null,
    ...overrides,
  } as ServerConfig;
}

beforeEach(async () => {
  mockProduction = false;
  await kv.clearAll();
  resetServerConfigSession();
  useSession.getState().reset();
});

afterEach(() => {
  useI18n.getState().setPack(EN_PACK);
});

describe('About: the helper line by provider', () => {
  it('picks the line from /v1/config.provider', () => {
    expect(helperModelsLine(config())).toEqual({ key: 'banner.sample_mode', vars: {} });
    expect(
      helperModelsLine(
        config({
          provider: 'openai_compat',
          ai_model_label: 'Qwen 3.5 4B (on this computer)',
          models: { pro: 'qwen3.5:4b', fast: 'qwen3.5:4b', pro_degraded_thinking: 'medium' },
        }),
      ),
    ).toEqual({ key: 'settings.model_single', vars: { model: 'Qwen 3.5 4B (on this computer)' } });
    // openai_compat without a label: the model id, once when pro and fast are the same.
    expect(
      helperModelsLine(
        config({ provider: 'openai_compat', models: { pro: 'qwen3.5:4b', fast: 'qwen3.5:4b', pro_degraded_thinking: 'medium' } }),
      ),
    ).toEqual({ key: 'settings.model_single', vars: { model: 'qwen3.5:4b' } });
    expect(helperModelsLine(config({ provider: 'gemini', data_use_tier: 'paid' }))).toEqual({
      key: 'settings.models',
      vars: { pro: 'gemini-3.8-flash', fast: 'gemini-3.5-flash-lite' },
    });
  });

  it('sample mode (mock): shows the sample-mode line, not the Gemini model ids', async () => {
    const { getByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <AboutSection config={config()} />
      </AppProviders>,
    );
    const line = getByTestId('settings-about-models');
    expect(line).toHaveTextContent(t('banner.sample_mode'));
    expect(line).not.toHaveTextContent(/gemini/);
  });

  it('gemini: shows both model ids', async () => {
    const { getByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <AboutSection config={config({ provider: 'gemini', data_use_tier: 'paid' })} />
      </AppProviders>,
    );
    const line = getByTestId('settings-about-models');
    expect(line).toHaveTextContent(/gemini-3\.8-flash/);
    expect(line).toHaveTextContent(/gemini-3\.5-flash-lite/);
  });

  it('openai_compat: shows ai_model_label', async () => {
    // Fixture template for the new key, so the placeholder renders before the en.json merge.
    useI18n.getState().setPack({ ...EN_PACK, strings: { ...EN_PACK.strings, 'settings.model_single': '{model}' } });
    const { getByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <AboutSection
          config={config({
            provider: 'openai_compat',
            data_use_tier: 'local',
            ai_model_label: 'Qwen 3.5 4B',
            models: { pro: 'qwen3.5:4b', fast: 'qwen3.5:4b', pro_degraded_thinking: 'medium' },
          })}
        />
      </AppProviders>,
    );
    const line = getByTestId('settings-about-models');
    expect(line).toHaveTextContent(/Qwen 3\.5 4B/);
    expect(line).not.toHaveTextContent(/qwen3\.5:4b/);
  });
});

describe('Developer options', () => {
  it('are collapsed until opened', async () => {
    const { getByTestId, queryByText, getByText } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <DeveloperSection
          apiUrl={API_URL}
          config={config()}
          getInstallId={async () => 'id'}
          rotateInstallId={async () => 'id2'}
        />
      </AppProviders>,
    );
    const toggle = getByTestId('settings-developer-toggle');
    expect(toggle.props.accessibilityState).toEqual({ expanded: false });
    expect(queryByText(t('settings.developer_api_url'))).toBeNull();
    expect(queryByText(t('btn.rotate_install_id'))).toBeNull();
    await fireEvent.press(toggle);
    expect(getByText(t('settings.developer_api_url'))).toBeTruthy();
    expect(getByText(t('btn.rotate_install_id'))).toBeTruthy();
  });

  it('Settings shows them (collapsed) in a development build', async () => {
    const { getByTestId, queryByText } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <SettingsScreen />
      </AppProviders>,
    );
    expect(getByTestId('settings-developer')).toBeTruthy();
    expect(getByTestId('settings-developer-toggle').props.accessibilityState).toEqual({ expanded: false });
    expect(queryByText(t('settings.developer_api_url'))).toBeNull();
  });

  it('Settings leaves them out of a production build', async () => {
    mockProduction = true;
    const { getByTestId, queryByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <SettingsScreen />
      </AppProviders>,
    );
    expect(getByTestId('settings-screen')).toBeTruthy();
    expect(queryByTestId('settings-developer')).toBeNull();
    expect(queryByTestId('settings-developer-toggle')).toBeNull();
  });
});
