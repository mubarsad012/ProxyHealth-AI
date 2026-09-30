// WP6 lane 6A: `deleteEverything()` runs the fixed `storage/wipe.ts` order first, then forgets the
// in-memory WP6 state (consent decision, sample list cache) and bumps the vault lists so they re-read.
// The wipe order itself is tested by WP4's storage tests.

import { useVaultVersion } from '@/features/vault/store';

import { deleteEverything } from './VaultAndDataSettings';

const mockCalls: string[] = [];

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
}));

jest.mock('@/storage/wipe', () => ({
  registerWipeHook: () => () => undefined,
  wipeEverything: jest.fn(async () => {
    mockCalls.push('wipe');
    return [];
  }),
}));

jest.mock('@/features/onboarding/consentState', () => ({
  ...jest.requireActual('@/features/onboarding/consentState'),
  resetConsentState: jest.fn(() => {
    mockCalls.push('consent');
  }),
}));

jest.mock('@/features/demo/sampleCache', () => ({
  ...jest.requireActual('@/features/demo/sampleCache'),
  resetSamplesCache: jest.fn(() => {
    mockCalls.push('samples');
  }),
}));

describe('deleteEverything', () => {
  beforeEach(() => {
    mockCalls.length = 0;
  });

  it('wipes storage before resetting memory, then bumps the vault lists', async () => {
    const before = useVaultVersion.getState().version;
    await deleteEverything();
    expect(mockCalls).toEqual(['wipe', 'consent', 'samples']);
    expect(useVaultVersion.getState().version).toBe(before + 1);
  });

  it('stops (and resets nothing) when the wipe fails', async () => {
    const { wipeEverything } = jest.requireMock('@/storage/wipe') as { wipeEverything: jest.Mock };
    wipeEverything.mockRejectedValueOnce(new Error('disk'));
    await expect(deleteEverything()).rejects.toThrow('disk');
    expect(mockCalls).toEqual([]);
  });
});
