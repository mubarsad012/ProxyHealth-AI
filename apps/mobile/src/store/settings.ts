// Persisted user settings (BUILD_PLAN §4.2; D-22/D-23). zustand + `persist` over `storage/kv.ts`
// (AsyncStorage: works on web, holds nothing sensitive). Field names are fixed by §4.2; the extra
// `languageDecided`, `voiceRate` and `hydrated` fields are additions (never renames).

import { Platform } from 'react-native';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { kv, KV_KEYS } from '@/storage/kv';

export type TextSize = 'normal' | 'large' | 'xl';
export type Tone = 'plain' | 'formal';
export type DateFormatPref = 'auto' | 'mdy' | 'dmy';
export type WebPersist = 'session' | 'indexeddb';

export interface SettingsState {
  languageTag: string;
  /** True once the user picked a language on S1 (S0 redirect). */
  languageDecided: boolean;
  textSize: TextSize;
  highContrast: boolean;
  voiceId: string | null;
  /** TTS rate 0.8–1.2 (S17). */
  voiceRate: number;
  lockScreenDetail: boolean;
  sampleMode: boolean;
  region: { state: string | null; zip3: string | null };
  preferences: { tone: Tone; calendarNotes: string[]; dateFormat: DateFormatPref };
  keepPageImages: boolean;
  hideIdNumbers: boolean;
  webPersist: WebPersist;
  clearOnClose: boolean;
  pinEnabled: boolean;
  hearItMode: boolean;
  /** Set by the persist middleware once AsyncStorage has been read. */
  hydrated: boolean;
}

export interface SettingsActions {
  set<K extends keyof SettingsState>(key: K, value: SettingsState[K]): void;
  patch(partial: Partial<SettingsState>): void;
  setRegion(region: Partial<SettingsState['region']>): void;
  setPreferences(prefs: Partial<SettingsState['preferences']>): void;
  resetSettings(): void;
}

export type SettingsStore = SettingsState & SettingsActions;

export const defaultSettings: SettingsState = {
  languageTag: 'en',
  languageDecided: false,
  textSize: 'normal',
  highContrast: false,
  voiceId: null,
  voiceRate: 1.0,
  lockScreenDetail: false,
  sampleMode: process.env.EXPO_PUBLIC_DEFAULT_SAMPLE_MODE === 'true',
  region: { state: null, zip3: null },
  preferences: { tone: 'plain', calendarNotes: [], dateFormat: 'auto' },
  keepPageImages: Platform.OS !== 'web',
  hideIdNumbers: false,
  webPersist: 'session',
  clearOnClose: true,
  pinEnabled: false,
  hearItMode: false,
  hydrated: false,
};

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      ...defaultSettings,
      set: (key, value) => set({ [key]: value } as Partial<SettingsState>),
      patch: (partial) => set(partial),
      setRegion: (region) => set((s) => ({ region: { ...s.region, ...region } })),
      setPreferences: (prefs) => set((s) => ({ preferences: { ...s.preferences, ...prefs } })),
      resetSettings: () => set({ ...defaultSettings, hydrated: true }),
    }),
    {
      name: KV_KEYS.settings,
      version: 1,
      storage: createJSONStorage(() => ({
        getItem: (name) => kv.get(name),
        setItem: (name, value) => kv.set(name, value),
        removeItem: (name) => kv.remove(name),
      })),
      partialize: (s) => {
        // Never persist the transient flag or the actions.
        const { hydrated: _h, set: _s, patch: _p, setRegion: _r, setPreferences: _q, resetSettings: _x, ...rest } = s;
        return rest;
      },
      onRehydrateStorage: () => (state) => {
        state?.patch({ hydrated: true });
      },
    },
  ),
);

/** Resolves once settings have been read from AsyncStorage (used by the splash gate). */
export function waitForSettings(): Promise<void> {
  if (useSettings.getState().hydrated) return Promise.resolve();
  return new Promise((resolve) => {
    const unsub = useSettings.subscribe((s) => {
      if (s.hydrated) {
        unsub();
        resolve();
      }
    });
    // In environments where the persist storage never answers (tests), do not hang.
    setTimeout(() => {
      if (!useSettings.getState().hydrated) {
        useSettings.getState().patch({ hydrated: true });
      }
    }, 1500);
  });
}
