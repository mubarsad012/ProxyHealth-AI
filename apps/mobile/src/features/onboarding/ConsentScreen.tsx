// S2 — What happens to your paper (D-02, PRODUCT_SPEC S2, COMPLIANCE_PRIVACY §4.2). Badge + lines
// that are literally true per tier and AI provider (free-ai-providers §5.2: `{model}` / `{vendor}`
// from `/v1/config`), 18+ line, "Read more" notice, Continue / Not now / Try a sample. Every line,
// the 18+ line included, has a speaker button (§4.2). unknown → Continue disabled with a hint;
// unpaid/mixed → Continue hidden, sample is primary; local/attested → Continue shown.
// Backing out equals "Not now" (the route file wires the hardware back button).

import { type Href, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { useServerConfig } from '@/api/config';
import { Banner } from '@/design/components/Banner';
import { BigButton } from '@/design/components/BigButton';
import { Icon, type IconName } from '@/design/components/Icon';
import { Screen } from '@/design/components/Screen';
import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText, Heading } from '@/design/components/Text';
import { TierBadge } from '@/design/components/TierBadge';
import { useTheme } from '@/design/theme';
import { size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import { platformName } from '@/lib/platform';
import type { ConsentRecord } from '@/storage/index';
import type { TierSeen } from '@/storage/consent';

import { aiSeenFor, consentView, type ConsentLine } from './consentModel';
import { acceptConsent, declineConsent, previousRecord, useConsentDecision } from './consentState';
import { PrivacyNotice } from './PrivacyNotice';

const PICTOGRAM: Record<NonNullable<ConsentLine['pictogram']>, IconName> = {
  cloud: 'cloud',
  server: 'server',
  phone: 'lock',
  masks: 'image',
};

export const TABS_HREF = '/(tabs)' as Href;
/** Home opens the sample picker when it sees `?sample=1` (WP6, `features/demo`). */
export const TABS_SAMPLE_HREF = '/(tabs)?sample=1' as Href;

export interface ConsentScreenProps {
  /** Navigation override (tests). Defaults to `router.replace`. */
  navigate?(href: Href): void;
}

export function ConsentScreen({ navigate = (h) => router.replace(h) }: ConsentScreenProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const meta = usePackMeta();
  const { config, tier, loading } = useServerConfig();
  const decision = useConsentDecision((s) => s.decision);
  const [previous, setPrevious] = useState<ConsentRecord | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (decision === 'accepted') {
      void previousRecord().then((r) => {
        if (!cancelled) setPrevious(r);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [decision]);

  const view = consentView({
    tier,
    platform: platformName(),
    features: config?.features ?? null,
    ai: config,
    previous,
  });
  const waiting = loading && !config;

  const onContinue = async () => {
    if (!config || view.continueDisabled) return;
    setBusy(true);
    try {
      await acceptConsent(config.consent_version, tier as TierSeen, aiSeenFor(config));
      navigate(TABS_HREF);
    } finally {
      setBusy(false);
    }
  };
  const onNotNow = async () => {
    await declineConsent();
    navigate(TABS_HREF);
  };
  const onSample = async () => {
    if (decision !== 'accepted') await declineConsent();
    navigate(TABS_SAMPLE_HREF);
  };

  const title = view.changed ? `${t('consent.changed')} ${t('consent.title')}` : t('consent.title');

  return (
    <Screen testID="consent-screen">
      <Heading level={1}>{title}</Heading>
      <TierBadge tier={tier} />
      {meta.machineTranslated ? <Banner kind="machine_translation" /> : null}
      {meta.partial ? <Banner kind="partial_pack" /> : null}
      {waiting ? <ActivityIndicator color={colors.primary} accessibilityLabel={t('a11y.app_starting')} /> : null}
      <View style={styles.lines}>
        {view.lines.map((line) => (
          <View
            key={line.key}
            testID={`consent-line-${line.key}`}
            style={[
              styles.line,
              { flexDirection: dir.row },
              line.changed ? { borderColor: colors.warning, borderWidth: 2 } : null,
            ]}>
            {line.pictogram ? (
              <Icon
                name={PICTOGRAM[line.pictogram]}
                size={size.iconLarge}
                color={line.tone === 'danger' ? colors.danger : colors.primary}
                accessibilityLabel={line.altKey ? t(line.altKey) : undefined}
                mirror={false}
              />
            ) : (
              <View style={styles.pictogramSpace} />
            )}
            <View style={styles.lineText}>
              <AppText
                color={line.tone === 'danger' ? 'danger' : 'text'}
                weight={line.tone === 'danger' ? 'bold' : 'regular'}
                variant={line.pictogram ? 'body' : 'caption'}>
                {t(line.key, view.vars)}
              </AppText>
            </View>
            <SpeakButton text={t(line.key, view.vars)} lang={meta.tag} />
          </View>
        ))}
      </View>
      <View testID="consent-adults-only" style={[styles.adults, { flexDirection: dir.row }]}>
        <View style={styles.lineText}>
          <AppText weight="bold">{t('consent.adults_only')}</AppText>
        </View>
        <SpeakButton text={t('consent.adults_only')} lang={meta.tag} />
      </View>
      <Pressable role="link" hitSlop={size.hitSlop} onPress={() => setNoticeOpen(true)} style={styles.link}>
        <AppText color="link" style={styles.underline}>
          {t('consent.read_more')}
        </AppText>
      </Pressable>
      <View style={styles.actions}>
        {view.primary === 'sample' ? (
          <BigButton label={t('consent.try_sample')} icon="sample" variant="primary" size={72} onPress={onSample} />
        ) : null}
        {view.showContinue ? (
          <BigButton
            testID="consent-continue"
            label={t('consent.btn_continue')}
            variant="primary"
            size={72}
            disabled={view.continueDisabled || busy || !config}
            onPress={() => void onContinue()}
          />
        ) : null}
        {view.hintKey ? <AppText color="textMuted">{t(view.hintKey)}</AppText> : null}
        <BigButton
          testID="consent-not-now"
          label={t('consent.btn_not_now')}
          variant="secondary"
          size={56}
          onPress={() => void onNotNow()}
        />
        {view.primary === 'sample' ? null : (
          <Pressable role="link" hitSlop={size.hitSlop} onPress={() => void onSample()} style={styles.link}>
            <AppText color="link" align="center" style={styles.underline}>
              {t('consent.try_sample')}
            </AppText>
          </Pressable>
        )}
      </View>
      <PrivacyNotice visible={noticeOpen} onClose={() => setNoticeOpen(false)} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  lines: {
    gap: space.md,
  },
  line: {
    alignItems: 'center',
    gap: space.md,
    padding: space.sm,
    borderRadius: 12,
  },
  adults: {
    alignItems: 'center',
    gap: space.md,
  },
  pictogramSpace: {
    width: size.iconLarge,
  },
  lineText: {
    flex: 1,
  },
  actions: {
    gap: space.md,
    marginTop: space.md,
  },
  link: {
    minHeight: size.minTouch,
    justifyContent: 'center',
  },
  underline: {
    textDecorationLine: 'underline',
  },
});
