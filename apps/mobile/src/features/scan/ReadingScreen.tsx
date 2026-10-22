// S6 — Reading your paper (`/scan/reading`). Honest three-step progress, Cancel aborts the request
// (nothing to clean up server-side), and every failure has a next step (D-07, PRODUCT_SPEC §5.4).

import { Image } from 'expo-image';
import { type Href, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import type { ApiError } from '@/api/errors';
import { BigButton } from '@/design/components/BigButton';
import { ProgressSteps } from '@/design/components/ProgressSteps';
import { Screen } from '@/design/components/Screen';
import { ErrorState } from '@/design/components/States';
import { AppText } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { isSlowTier, useAnalyze } from '@/features/analysis/useAnalyze';
import { ConsentScreen, TABS_HREF } from '@/features/onboarding/ConsentScreen';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { useT } from '@/i18n/useT';
import { type CapturedPage, useSession } from '@/store/session';

import { useReadLater } from './readLater';

const BACK_TO_PAGES: ReadonlySet<string> = new Set([
  'too_many_pages',
  'pdf_too_long',
  'payload_too_large',
  'unsupported_media_type',
  'invalid_request',
  'model_output_invalid',
]);

function backToReview() {
  if (router.canGoBack()) router.back();
  else router.replace('/scan/review' as Href);
}

/** S6 `428` row: after S2 is accepted, retry the request once; any other exit goes where S2 says. */
export function consentThenRetry(opts: {
  href: Href;
  accepted: boolean;
  alreadyRetried: boolean;
  retry(): void;
  navigate(href: Href): void;
}): 'retried' | 'navigated' {
  if (opts.accepted && !opts.alreadyRetried && opts.href === TABS_HREF) {
    opts.retry();
    return 'retried';
  }
  opts.navigate(opts.href);
  return 'navigated';
}

export function ReadingScreen() {
  const t = useT();
  const run = useAnalyze();
  const started = useRef(false);
  const [retriedAfterConsent, setRetriedAfterConsent] = useState(false);
  const pages = useSession((s) => s.pages);
  const isSample = useSession((s) => Boolean(s.demoSampleId));
  // A local test model takes minutes per page: say so instead of "usually under a minute".
  const slowTier = useSession((s) => isSlowTier(s.serverConfig?.client_timeouts));
  const { start, status, result } = run;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);

  useEffect(() => {
    if (status === 'done' && result) router.replace(`/result/${encodeURIComponent(result.analysis_id)}` as Href);
  }, [status, result]);

  const cancel = () => {
    run.cancel();
    backToReview();
  };

  if (status === 'error' && run.error?.isConsentRequired() && !retriedAfterConsent) {
    // 428 → S2 inline (WP4's screen), then one automatic retry of the same pages.
    return (
      <ConsentScreen
        navigate={(href) =>
          consentThenRetry({
            href,
            accepted: useConsentDecision.getState().decision === 'accepted',
            alreadyRetried: retriedAfterConsent,
            retry: () => {
              setRetriedAfterConsent(true);
              start();
            },
            navigate: (h) => router.replace(h),
          })
        }
      />
    );
  }

  if (status === 'error' && run.error) {
    return (
      <Screen back onBack={cancel} testID="reading-screen">
        <ReadingError error={run.error} onRetry={start} sample={isSample} pages={pages} />
      </Screen>
    );
  }

  if (status === 'unreadable') {
    const first = pages[0];
    return (
      <Screen back onBack={cancel} testID="reading-screen">
        <View role="alert" style={styles.stack}>
          <AppText variant="bodyLarge" weight="bold">
            {t('state.unreadable')}
          </AppText>
          {first && first.mimeType !== 'application/pdf' ? (
            <Image source={{ uri: first.uri }} cachePolicy="memory" contentFit="contain" style={styles.page} accessibilityLabel={t('state.unreadable')} />
          ) : null}
          <BigButton label={t('btn.retake')} icon="camera" variant="primary" size={72} onPress={backToReview} />
        </View>
      </Screen>
    );
  }

  const steps = [t('reading.step1'), t('reading.step2'), t('reading.step3')];
  return (
    <Screen testID="reading-screen" footer={<BigButton label={t('btn.cancel')} icon="close" variant="secondary" size={56} onPress={cancel} />}>
      <ProgressSteps steps={steps} active={run.step} live />
      <AppText>{t('reading.trust_line')}</AppText>
      <AppText color="textMuted">{t(slowTier ? 'reading.eta_slow' : 'reading.eta')}</AppText>
      {run.tipKey ? (
        <AppText role="status" color="textMuted">
          {t(run.tipKey)}
        </AppText>
      ) : null}
    </Screen>
  );
}

function ReadingError({ error, onRetry, sample, pages }: { error: ApiError; onRetry(): void; sample: boolean; pages: readonly CapturedPage[] }) {
  const t = useT();
  // "Save to read later" = save to My papers as "Not read yet" (PRODUCT_SPEC §5.4), then show the list.
  const readLater = useReadLater(pages, sample, () => router.replace('/papers' as Href));
  if (error.isConsentRequired()) {
    return (
      <View role="alert" style={styles.stack}>
        <AppText>{t('err.consent_required')}</AppText>
        <BigButton label={t('btn.continue')} variant="primary" size={72} onPress={() => router.push('/onboarding/consent' as Href)} />
      </View>
    );
  }
  if (error.isBlocked()) {
    return (
      <View role="alert" style={styles.stack}>
        <AppText>{t('err.content_blocked')}</AppText>
        {sample ? null : <BigButton label={t('btn.hide_and_retry')} icon="lock" variant="primary" size={72} onPress={backToReview} />}
        <BigButton label={t('btn.get_help')} icon="help" variant="secondary" size={56} onPress={() => router.push('/help' as Href)} />
      </View>
    );
  }
  const offlineLike = error.isOffline() || error.isQuotaExhausted() || error.code === 'upstream_unavailable';
  const call211 = () => void Linking.openURL('tel:211').catch(() => undefined);
  return (
    <View style={styles.stack}>
      <ErrorState
        error={error}
        onRetry={onRetry}
        onSaveLater={offlineLike && readLater.block === 'none' ? () => void readLater.start() : undefined}
        onCall211={call211}
        onTrySample={() => router.replace('/?sample=1' as Href)}
      />
      {/* BUILD_PLAN §5.6: the network state offers Call 211 too; WP4's ErrorState shows it only for
          quota/upstream errors, so it is added here for network/timeout (CL line in DECISIONS §14). */}
      {error.isOffline() ? (
        <BigButton testID="reading-call-211" label={t('btn.call_211')} icon="phone" variant="secondary" size={56} onPress={call211} />
      ) : null}
      {BACK_TO_PAGES.has(error.code) ? (
        <BigButton label={t('btn.back')} icon="arrow-back" variant="secondary" size={56} onPress={backToReview} />
      ) : null}
      {error.isUnpaidBlocked() || error.code === 'not_found' || error.code === 'unauthorized' ? (
        <BigButton label={t('btn.go_home')} icon="home" variant="secondary" size={56} onPress={() => router.replace('/' as Href)} />
      ) : null}
      {readLater.failed ? (
        <AppText role="alert" color="danger">
          {t('err.internal')}
        </AppText>
      ) : null}
      {readLater.sheet}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: space.lg,
  },
  page: {
    width: '100%',
    aspectRatio: 0.77,
  },
});
