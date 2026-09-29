// S3 — Home (PRODUCT_SPEC S3): one obvious 72 pt action, banners (offline → unpaid → sample mode →
// web session-only), the next-date card (`useNextDate`, → S14), four 56 pt tiles, the trust footer.
// Web: "Take a photo" / "Pick a photo or PDF" call the picker as the first statement of the press
// handler (browser gesture rule). Consent missing → the CTA opens S2. Unpaid/mixed tier → real
// papers are off and the sample tile leads. `?sample=1` (from S2) or sample mode opens the picker.

import { type Href, router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import type { GestureResponderEvent } from 'react-native';

import { useServerConfig } from '@/api/config';
import { Banner } from '@/design/components/Banner';
import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { Interpolated } from '@/design/components/Interpolated';
import { Screen } from '@/design/components/Screen';
import { AppText } from '@/design/components/Text';
import { Tile } from '@/design/components/Tile';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { openSample } from '@/features/demo/openSample';
import { SamplePickerSheet } from '@/features/demo/SamplePicker';
import { useSampleMode } from '@/features/demo/useSampleMode';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { formatDay } from '@/features/reminders/format';
import { useReminderTapRouting } from '@/features/reminders/useReminderTapRouting';
import { usePickImage } from '@/features/scan';
import { useDocuments, useNextDate } from '@/features/vault/hooks';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';
import { type CapturedPage, useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

const isWeb = Platform.OS === 'web';
let pickerShownThisSession = false;

function openPicked(pending: Promise<CapturedPage[]>): void {
  pending
    .then((pages) => {
      if (pages.length === 0) return;
      const session = useSession.getState();
      session.setDemoSampleId(null);
      session.setCurrentAnalysis(null);
      session.setPages(pages);
      router.push('/scan/review' as Href);
    })
    .catch(() => undefined);
}

function NextDateCard() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const tag = useSettings((s) => s.languageTag);
  const next = useNextDate();
  if (!next) return null;
  const href = next.documentId ? `/reminders?doc=${encodeURIComponent(next.documentId)}` : '/reminders';
  return (
    <Pressable
      testID="home-next-date"
      role="button"
      accessibilityLabel={t('home.next_date', { date: formatDay(next.dateIso, tag), document_title: next.title })}
      onPress={() => router.push(href as Href)}
      style={[styles.card, { flexDirection: dir.row, borderColor: colors.warning, backgroundColor: colors.surface }]}>
      <Icon name="calendar-alert" color={colors.warning} size={size.iconLarge} />
      <View style={styles.flex}>
        <Interpolated
          weight="bold"
          template={t('home.next_date')}
          vars={{ date: formatDay(next.dateIso, tag), document_title: next.title }}
          ltrKeys={[]}
        />
      </View>
      <Icon name="chevron-right" color={colors.textMuted} mirror />
    </Pressable>
  );
}

export default function HomeScreen() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const params = useLocalSearchParams<{ sample?: string }>();
  const { tier } = useServerConfig();
  const { online } = useOnline();
  const decision = useConsentDecision((s) => s.decision);
  const consent = useSession((s) => s.consent);
  const webPersist = useSettings((s) => s.webPersist);
  const sample = useSampleMode();
  const picker = usePickImage();
  const { rows } = useDocuments();
  const [manualOpen, setManualOpen] = useState(false);
  const [autoDismissed, setAutoDismissed] = useState(false);
  // Judging builds / sample mode: the picker is open when Home first appears (once per session).
  // (the Settings toggle / judging-build default only — not the mock server's forced sample mode).
  const sampleSetting = useSettings((s) => s.sampleMode);
  const [autoOpen] = useState(() => sampleSetting && !pickerShownThisSession);
  const pickerOpen = manualOpen || (!autoDismissed && (params.sample === '1' || autoOpen));
  const setPickerOpen = (open: boolean) => {
    setManualOpen(open);
    if (!open) setAutoDismissed(true);
  };
  useReminderTapRouting();

  const consentOk = decision === 'accepted' && consent !== null;
  const unpaid = tier === 'unpaid' || tier === 'mixed';
  const sampleFirst = unpaid || tier === 'demo' || sample.enabled;

  useEffect(() => {
    if (pickerOpen) pickerShownThisSession = true;
  }, [pickerOpen]);

  const scan = (e?: GestureResponderEvent) => {
    if (!consentOk) {
      router.push('/onboarding/consent' as Href);
      return;
    }
    if (isWeb) {
      openPicked(picker.pickFromLibrary(e));
      return;
    }
    router.push('/scan/capture' as Href);
  };
  const pick = (e?: GestureResponderEvent) => {
    if (!consentOk) {
      router.push('/onboarding/consent' as Href);
      return;
    }
    openPicked(picker.pickFromLibrary(e));
  };
  const newest = [...rows].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))[0];
  const clerkHref = newest ? `/result/${encodeURIComponent(newest.id)}/clerk` : '/result/generic/clerk';

  const sampleTile = (
    <Tile
      testID="home-tile-sample"
      title={t('home.tile_sample')}
      line={t('home.tile_sample_sub')}
      icon="sample"
      onPress={() => setPickerOpen(true)}
    />
  );

  return (
    <Screen title={t('app.name')} testID="home-screen">
      {!online ? <Banner kind="offline" /> : null}
      {unpaid ? <Banner kind="unpaid" /> : null}
      {tier === 'demo' || sample.enabled ? <Banner kind="demo" /> : null}
      {isWeb && webPersist === 'session' ? (
        <AppText variant="caption" color="textMuted">
          {t('banner.web_session_only')}
        </AppText>
      ) : null}
      <NextDateCard />
      {unpaid ? sampleTile : null}
      <View style={styles.cta}>
        <BigButton
          testID="home-scan-cta"
          label={t('home.scan_cta')}
          icon="camera"
          variant="primary"
          size={72}
          disabled={unpaid && consentOk}
          accessibilityHint={t('home.scan_hint')}
          onPress={scan}
        />
        {!online ? <AppText color="textMuted">{t('home.offline_line')}</AppText> : null}
        {unpaid ? <AppText weight="bold">{t('home.unpaid_disabled')}</AppText> : null}
        {!consentOk ? (
          <Pressable role="link" onPress={() => router.push('/onboarding/consent' as Href)} hitSlop={size.hitSlop}>
            <AppText color="link" weight="bold">
              {t('home.consent_needed')}
            </AppText>
          </Pressable>
        ) : null}
      </View>
      <Tile
        testID="home-tile-pick"
        title={t('home.tile_pick')}
        line={t('home.tile_pick_sub')}
        icon="image"
        disabled={unpaid && consentOk}
        onPress={pick}
      />
      <Tile
        testID="home-tile-troubleshoot"
        title={t('home.tile_troubleshoot')}
        line={online ? t('home.tile_troubleshoot_sub') : t('state.offline_disabled')}
        icon="help"
        disabled={!online}
        onPress={() => router.push('/troubleshoot' as Href)}
      />
      <Tile
        testID="home-tile-clerk"
        title={t('home.tile_clerk')}
        line={t('home.tile_clerk_sub')}
        icon="people"
        onPress={() => router.push(clerkHref as Href)}
      />
      {sampleFirst && !unpaid ? sampleTile : null}
      {sampleFirst ? null : (
        <Pressable testID="home-sample-link" role="button" onPress={() => setPickerOpen(true)} hitSlop={size.hitSlop}>
          <AppText color="link" weight="bold">
            {t('btn.try_sample')}
          </AppText>
        </Pressable>
      )}
      <View style={[styles.footer, { flexDirection: dir.row, borderColor: colors.divider }]}>
        <Icon name="lock" color={colors.textMuted} />
        <View style={styles.flex}>
          <AppText variant="caption" color="textMuted">
            {isWeb ? t('home.trust_footer.web') : t('home.trust_footer')}
          </AppText>
        </View>
      </View>
      <SamplePickerSheet
        visible={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(fixture, pages) => {
          setPickerOpen(false);
          openSample(fixture, pages);
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  cta: {
    gap: space.sm,
  },
  card: {
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderWidth: 2,
    borderRadius: radius.md,
    minHeight: size.button,
  },
  footer: {
    alignItems: 'center',
    gap: space.sm,
    paddingTop: space.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
