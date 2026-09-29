// Platform helpers (ARCHITECTURE §7 rule 7): every device feature branches on `isWeb`.

import { Platform } from 'react-native';

export const isWeb = Platform.OS === 'web';
export const isNative = !isWeb;
export const isIOS = Platform.OS === 'ios';
export const isAndroid = Platform.OS === 'android';

export type PlatformName = 'ios' | 'android' | 'web';

export function platformName(): PlatformName {
  if (Platform.OS === 'ios') return 'ios';
  if (Platform.OS === 'android') return 'android';
  return 'web';
}

/** Public env (ARCHITECTURE §6.2). Baked at build/export time. */
export const env = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000',
  appToken: process.env.EXPO_PUBLIC_APP_TOKEN || '',
  appEnv: process.env.EXPO_PUBLIC_APP_ENV || 'development',
  defaultSampleMode: process.env.EXPO_PUBLIC_DEFAULT_SAMPLE_MODE === 'true',
} as const;

export const isProduction = env.appEnv === 'production';

/**
 * On web, pickers and clipboard calls must be the first statement inside the gesture handler
 * (no `await` before them). `runInGesture` documents that rule at the call site: it invokes `fn`
 * synchronously and returns its promise, so callers cannot accidentally await something first.
 */
export function runInGesture<T>(fn: () => Promise<T>): Promise<T> {
  return fn();
}

/** `document` only exists on web; guarded so shared code can call it anywhere. */
export function webDocument(): Document | null {
  if (Platform.OS !== 'web') return null;
  return typeof document === 'undefined' ? null : document;
}
