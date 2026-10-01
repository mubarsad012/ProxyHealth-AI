// Root layout (D-27, PRODUCT_SPEC S0): providers + one root Stack (tabs group, onboarding, stack
// screens above the tabs, the emergency modal). The splash screen stays up until the nine Noto
// families are loaded and the language decision is applied (max ~3 s, never a blank screen).

import { DarkTheme, DefaultTheme, type ErrorBoundaryProps, Stack, ThemeProvider as NavThemeProvider } from 'expo-router';
import Head from 'expo-router/head';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import { AccessibilityInfo, Platform } from 'react-native';

import '@/global.css';
import { AppProviders } from '@/design/components/Providers';
import { useTheme } from '@/design/theme';
import { loadConsent } from '@/features/onboarding/consentState';
import { NotFoundScreen } from '@/features/onboarding/NotFoundScreen';
import { useAppFonts } from '@/i18n/fonts';
import { t, useI18n } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { purgeCaptureCache } from '@/storage/cache';

void SplashScreen.preventAutoHideAsync().catch(() => undefined);

const SPLASH_MAX_MS = 3000;

/** Native capture modules leave full-size photos / crops / picked files in the app cache
 *  (storage/cache.native.ts). The scan session is memory-only, so at a cold start nothing still
 *  needs them: remove them once per app launch (no-op on web). */
let capturesPurged = false;
function purgeCapturesOnce(): void {
  if (capturesPurged) return;
  capturesPurged = true;
  void purgeCaptureCache().catch(() => undefined);
}

/** Root error boundary = S18 without a stack trace (developer builds show a collapsible). */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  return (
    <AppProviders>
      <NotFoundScreen error={error} retry={() => void retry()} />
    </AppProviders>
  );
}

/** Web only: a non-empty document title on every route (WCAG 2.4.2), in the active language. */
function WebTitle() {
  const tr = useT();
  if (Platform.OS !== 'web') return null;
  return (
    <Head>
      <title>{tr('app.name')}</title>
    </Head>
  );
}

function RootStack() {
  const theme = useTheme();
  const navTheme = useMemo(() => {
    const base = theme.scheme === 'dark' && !theme.highContrast ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: {
        ...base.colors,
        background: theme.colors.background,
        card: theme.colors.background,
        text: theme.colors.text,
        border: theme.colors.divider,
        primary: theme.colors.primary,
      },
    };
  }, [theme]);
  return (
    <NavThemeProvider value={navTheme}>
      <WebTitle />
      <StatusBar style={theme.scheme === 'dark' && !theme.highContrast ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: theme.colors.background } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="onboarding/language" />
        <Stack.Screen name="onboarding/adapting" options={{ gestureEnabled: false }} />
        <Stack.Screen name="onboarding/consent" />
        <Stack.Screen name="emergency" options={{ presentation: 'modal' }} />
        <Stack.Screen name="+not-found" />
      </Stack>
    </NavThemeProvider>
  );
}

function SplashGate() {
  const [fontsLoaded, fontError] = useAppFonts();
  const i18nReady = useI18n((s) => s.ready);
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    // The consent record must be in the session on every entry route (deep links too), because
    // the API client reads X-Consent-Version from there.
    void loadConsent();
    purgeCapturesOnce();
    try {
      AccessibilityInfo.announceForAccessibility(t('a11y.app_starting'));
    } catch {
      // best-effort
    }
    const id = setTimeout(() => setTimedOut(true), SPLASH_MAX_MS);
    return () => clearTimeout(id);
  }, []);
  const ready = ((fontsLoaded || Boolean(fontError)) && i18nReady) || timedOut;
  useEffect(() => {
    if (ready) void SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);
  return <RootStack />;
}

export default function RootLayout() {
  return (
    <AppProviders>
      <SplashGate />
    </AppProviders>
  );
}
