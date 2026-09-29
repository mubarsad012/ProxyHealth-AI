// Settings → saved papers, sample mode and "Delete everything" (PRODUCT_SPEC S17 items 5–8,
// §9.4–§9.5, D-22/D-23). Rendered by WP4's `(tabs)/settings.tsx` between "How your paper is
// handled" and "About".
//   5 `settings.papers`: keep page images, hide ID numbers, lock-screen detail; web only: keep on
//     this device (IndexedDB, after `vault.web_keep_confirm`) + clear when I close this tab.
//     App PIN is a SHOULD item and is not offered yet (never on web).
//   7 `settings.sample_mode`: toggle, locked on with `settings.sample_forced` when provider=mock.
//   6/8 withdraw consent ("Stop sending papers" → wipe offer) and Delete everything → confirm →
//     `storage/wipe.ts` (notifications, vault, secure store, settings, kv, install id, memory),
//     then back to S1.

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { SettingsSection, SwitchRow } from '@/design/components/SettingsRows';
import { AppText } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { resetSamplesCache } from '@/features/demo/sampleCache';
import { useSampleMode } from '@/features/demo/useSampleMode';
import { resetConsentState, useConsentDecision, withdrawConsent } from '@/features/onboarding/consentState';
import { ConfirmDialog } from '@/features/vault/Sheet';
import { bumpVault } from '@/features/vault/store';
import { useT } from '@/i18n/useT';
import { wipeEverything } from '@/storage/wipe';
import { useSettings } from '@/store/settings';

const isWeb = Platform.OS === 'web';

/** "Delete everything" in the order `storage/wipe.ts` fixes, then forget in-memory WP6 state. */
export async function deleteEverything(): Promise<void> {
  await wipeEverything();
  resetConsentState();
  resetSamplesCache();
  bumpVault();
}

function PapersSection() {
  const t = useT();
  const keepPages = useSettings((s) => s.keepPageImages);
  const hideIds = useSettings((s) => s.hideIdNumbers);
  const lockScreen = useSettings((s) => s.lockScreenDetail);
  const webPersist = useSettings((s) => s.webPersist);
  const clearOnClose = useSettings((s) => s.clearOnClose);
  const set = useSettings((s) => s.set);
  const patch = useSettings((s) => s.patch);
  const [confirmKeep, setConfirmKeep] = useState(false);
  return (
    <SettingsSection title={t('settings.papers')} testID="settings-papers">
      <SwitchRow
        testID="settings-keep-pages"
        label={t('settings.keep_pages')}
        explanation={t('settings.keep_pages_why')}
        value={keepPages}
        onChange={(v) => set('keepPageImages', v)}
      />
      <SwitchRow
        testID="settings-hide-ids"
        label={t('settings.hide_ids')}
        explanation={t('settings.hide_ids_why')}
        value={hideIds}
        onChange={(v) => set('hideIdNumbers', v)}
      />
      <SwitchRow
        testID="settings-lockscreen"
        label={t('settings.lockscreen_detail')}
        explanation={t('reminders.lockscreen_explain')}
        value={lockScreen}
        onChange={(v) => set('lockScreenDetail', v)}
      />
      {isWeb ? (
        <>
          <SwitchRow
            testID="settings-web-keep"
            label={t('settings.web_keep')}
            explanation={webPersist === 'indexeddb' ? t('vault.web_kept') : t('banner.web_session_only')}
            value={webPersist === 'indexeddb'}
            onChange={(v) => (v ? setConfirmKeep(true) : set('webPersist', 'session'))}
          />
          {webPersist === 'indexeddb' ? (
            <SwitchRow
              testID="settings-web-clear"
              label={t('settings.web_clear_on_close')}
              value={clearOnClose}
              onChange={(v) => set('clearOnClose', v)}
            />
          ) : null}
        </>
      ) : null}
      <AppText variant="caption" color="textMuted">
        {isWeb ? t('vault.privacy_web') : t('vault.privacy_native')} {t('vault.privacy_server')}
      </AppText>
      <ConfirmDialog
        testID="web-keep-confirm"
        visible={confirmKeep}
        title={t('settings.web_keep')}
        body={t('vault.web_keep_confirm')}
        confirmLabel={t('btn.yes')}
        cancelLabel={t('btn.cancel')}
        onCancel={() => setConfirmKeep(false)}
        onConfirm={() => {
          patch({ webPersist: 'indexeddb', clearOnClose: true });
          setConfirmKeep(false);
        }}
      />
    </SettingsSection>
  );
}

function SampleSection() {
  const t = useT();
  const sample = useSampleMode();
  return (
    <SettingsSection title={t('settings.sample_mode')} testID="settings-sample">
      <SwitchRow
        testID="settings-sample-toggle"
        label={t('settings.sample_toggle')}
        explanation={sample.forced ? t('settings.sample_forced') : t('settings.sample_why')}
        value={sample.enabled}
        disabled={sample.forced}
        onChange={(v) => sample.set(v)}
      />
    </SettingsSection>
  );
}

function DeleteSection() {
  const t = useT();
  const decision = useConsentDecision((s) => s.decision);
  const [offerWipe, setOfferWipe] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const wipeLabel = isWeb ? t('btn.delete_everything_web') : t('btn.delete_everything');
  const run = async () => {
    setBusy(true);
    try {
      await deleteEverything();
    } finally {
      setBusy(false);
      setConfirm(false);
      router.replace('/onboarding/language' as Href);
    }
  };
  return (
    <SettingsSection title={t('settings.delete_everything')} testID="settings-delete">
      {decision === 'accepted' ? (
        <BigButton
          testID="settings-withdraw"
          label={t('btn.withdraw_consent')}
          icon="stop"
          variant="secondary"
          size={56}
          onPress={() => void withdrawConsent().then(() => setOfferWipe(true))}
        />
      ) : null}
      {offerWipe ? (
        <View role="status" style={styles.offer}>
          <AppText weight="bold">{t('settings.wipe_offer')}</AppText>
          <BigButton label={wipeLabel} variant="danger" size={56} onPress={() => setConfirm(true)} />
          <BigButton label={t('settings.keep_saved')} variant="secondary" size={56} onPress={() => setOfferWipe(false)} />
        </View>
      ) : null}
      <BigButton
        testID="settings-delete-everything"
        label={wipeLabel}
        icon="close"
        variant="danger"
        size={56}
        onPress={() => setConfirm(true)}
      />
      <ConfirmDialog
        testID="wipe-confirm"
        visible={confirm}
        title={t('wipe.title')}
        body={t('wipe.body')}
        confirmLabel={t('wipe.confirm')}
        cancelLabel={t('btn.cancel')}
        danger
        busy={busy}
        onCancel={() => setConfirm(false)}
        onConfirm={() => void run()}
      />
    </SettingsSection>
  );
}

export function VaultAndDataSettings() {
  return (
    <View style={styles.wrap}>
      <PapersSection />
      <SampleSection />
      <DeleteSection />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  offer: {
    gap: space.sm,
  },
});
