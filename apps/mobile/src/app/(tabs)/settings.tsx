// S17 — Settings (PRODUCT_SPEC S17). Language + voice, reading, region, tone and calendar, how your
// paper is handled, then WP6's `VaultAndDataSettings` seam (saved papers, sample mode, withdraw,
// Delete everything), about, and the developer section outside production builds.

import { type Href, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useServerConfig } from '@/api/config';
import { isolate } from '@/design/components/Bidi';
import { Interpolated } from '@/design/components/Interpolated';
import { BigButton } from '@/design/components/BigButton';
import { Screen } from '@/design/components/Screen';
import { ChoiceChips, LinkRow, SettingsSection, SwitchRow, ToggleChip } from '@/design/components/SettingsRows';
import { AppText } from '@/design/components/Text';
import { TierBadge } from '@/design/components/TierBadge';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { PrivacyNotice } from '@/features/onboarding/PrivacyNotice';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { VaultAndDataSettings } from '@/features/settings';
import { useDirection, useRestartPending } from '@/i18n/direction';
import { useLanguage } from '@/i18n/language';
import { BASE_STRINGS } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { getInstallId, rotateInstallId } from '@/lib/ids';
import { env, isProduction } from '@/lib/platform';
import { getVoices, speak, type Voice } from '@/lib/tts';
import { useSession } from '@/store/session';
import { type DateFormatPref, type TextSize, useSettings } from '@/store/settings';

import { AboutSection, DeveloperSection, RegionSection } from '@/features/onboarding/SettingsSections';

const RATES = [0.8, 0.9, 1.0, 1.1, 1.2] as const;
const CALENDAR_NOTES = ['ramadan', 'eid', 'sabbath', 'lent', 'lunar_new_year', 'diwali', 'nowruz'] as const;

function LanguageSection() {
  const t = useT();
  const { pack, info } = useLanguage();
  const restartPending = useRestartPending();
  const voiceId = useSettings((s) => s.voiceId);
  const voiceRate = useSettings((s) => s.voiceRate);
  const hearItMode = useSettings((s) => s.hearItMode);
  const set = useSettings((s) => s.set);
  const [voices, setVoices] = useState<Voice[]>([]);
  useEffect(() => {
    let cancelled = false;
    const tags = [info.tts_tag, info.tts_fallback_tag, pack.tag]
      .filter((x): x is string => Boolean(x))
      .map((x) => x.split('-')[0].toLowerCase());
    void getVoices().then((all) => {
      if (!cancelled) setVoices(all.filter((v) => tags.includes(v.language.split(/[-_]/)[0].toLowerCase())).slice(0, 8));
    });
    return () => {
      cancelled = true;
    };
  }, [info.tts_tag, info.tts_fallback_tag, pack.tag]);
  const label = pack.reviewed_by
    ? t('settings.reviewed_by', { name: pack.reviewed_by })
    : pack.machine_translated
      ? t('settings.machine_translated')
      : undefined;
  return (
    <SettingsSection title={t('settings.language')} testID="settings-language">
      <LinkRow
        testID="settings-language-row"
        label={pack.name_native}
        value={label}
        onPress={() => router.push('/onboarding/language?from=settings' as Href)}
      />
      {restartPending ? (
        <View role="status">
          <AppText weight="bold">{t('direction.restart_pending')}</AppText>
        </View>
      ) : null}
      <ChoiceChips
        label={t('settings.voice')}
        options={[{ value: '', label: t('settings.voice_default') }, ...voices.map((v) => ({ value: v.identifier, label: v.name }))]}
        value={voiceId ?? ''}
        onChange={(v) => set('voiceId', v === '' ? null : v)}
      />
      <ChoiceChips
        label={t('settings.voice_rate')}
        options={RATES.map((r) => ({ value: r, label: isolate(`${r.toFixed(1)}×`) }))}
        value={voiceRate}
        onChange={(v) => set('voiceRate', v)}
      />
      <BigButton
        label={t('btn.test_voice')}
        icon="speaker"
        variant="secondary"
        size={56}
        onPress={() => void speak(t('app.tagline'), pack.tag)}
      />
      <SwitchRow label={t('settings.hear_mode_default')} value={hearItMode} onChange={(v) => set('hearItMode', v)} />
    </SettingsSection>
  );
}

function ReadingSection() {
  const t = useT();
  const textSize = useSettings((s) => s.textSize);
  const highContrast = useSettings((s) => s.highContrast);
  const set = useSettings((s) => s.set);
  const sizes: TextSize[] = ['normal', 'large', 'xl'];
  return (
    <SettingsSection title={t('settings.reading')} testID="settings-reading">
      <ChoiceChips
        label={t('settings.text_size')}
        options={sizes.map((s) => ({ value: s, label: t(`settings.text_size_${s}`) }))}
        value={textSize}
        onChange={(v) => set('textSize', v)}
        testIDPrefix="text-size"
      />
      <AppText>{t('app.tagline')}</AppText>
      <SwitchRow
        testID="settings-high-contrast"
        label={t('settings.high_contrast')}
        value={highContrast}
        onChange={(v) => set('highContrast', v)}
      />
      <AppText variant="caption" color="textMuted">
        {t('settings.reduce_motion_note')}
      </AppText>
    </SettingsSection>
  );
}

function ToneSection() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const prefs = useSettings((s) => s.preferences);
  const setPreferences = useSettings((s) => s.setPreferences);
  const [custom, setCustom] = useState('');
  const toggleNote = (note: string) => {
    const has = prefs.calendarNotes.includes(note);
    if (!has && prefs.calendarNotes.length >= 5) return;
    setPreferences({ calendarNotes: has ? prefs.calendarNotes.filter((n) => n !== note) : [...prefs.calendarNotes, note] });
  };
  // The stored value is the English name (sent as `Preferences.calendar_notes`); the chip shows the pack word.
  const known = CALENDAR_NOTES.map((k) => ({ value: BASE_STRINGS[`settings.cal.${k}`] ?? k, label: t(`settings.cal.${k}`) }));
  const customNotes = prefs.calendarNotes
    .filter((n) => !known.some((k) => k.value === n))
    .map((n) => ({ value: n, label: n }));
  return (
    <SettingsSection title={t('settings.tone')} testID="settings-tone">
      <ChoiceChips
        options={[
          { value: 'plain', label: t('settings.tone_plain') },
          { value: 'formal', label: t('settings.tone_formal') },
        ]}
        value={prefs.tone}
        onChange={(v) => setPreferences({ tone: v as 'plain' | 'formal' })}
      />
      <AppText weight="bold">{t('settings.calendar_notes')}</AppText>
      <View style={[styles.wrap, { flexDirection: dir.row }]}>
        {[...known, ...customNotes].map((note) => (
          <ToggleChip
            key={note.value}
            label={note.label}
            on={prefs.calendarNotes.includes(note.value)}
            onPress={() => toggleNote(note.value)}
          />
        ))}
      </View>
      <View style={[styles.inline, { flexDirection: dir.row }]}>
        <TextInput
          value={custom}
          onChangeText={(v) => setCustom(v.slice(0, 40))}
          maxLength={40}
          placeholder={t('settings.calendar_add')}
          placeholderTextColor={colors.textMuted}
          accessibilityLabel={t('settings.calendar_add')}
          style={[styles.input, { color: colors.text, borderColor: colors.border, textAlign: dir.textAlign }]}
        />
        <BigButton
          label={t('btn.save')}
          variant="secondary"
          size={56}
          disabled={custom.trim().length === 0 || prefs.calendarNotes.length >= 5}
          onPress={() => {
            toggleNote(custom.trim());
            setCustom('');
          }}
        />
      </View>
      <ChoiceChips
        label={t('settings.date_format')}
        options={(['auto', 'mdy', 'dmy'] as DateFormatPref[]).map((f) => ({ value: f, label: t(`settings.date_format_${f}`) }))}
        value={prefs.dateFormat}
        onChange={(v) => setPreferences({ dateFormat: v })}
      />
      <AppText variant="caption" color="textMuted">
        {t('settings.tone_why')}
      </AppText>
    </SettingsSection>
  );
}

function DataSection() {
  const t = useT();
  const tier = useSession((s) => s.tier);
  const consent = useSession((s) => s.consent);
  const decision = useConsentDecision((s) => s.decision);
  const [notice, setNotice] = useState(false);
  return (
    <SettingsSection title={t('settings.data')} testID="settings-data">
      <TierBadge tier={tier} />
      {consent && decision === 'accepted' ? (
        <Interpolated template={t('settings.consent_accepted_on')} vars={{ date: consent.accepted_at.slice(0, 10) }} />
      ) : (
        <AppText>{t('settings.consent_not_given')}</AppText>
      )}
      <LinkRow label={t('btn.read_privacy')} onPress={() => setNotice(true)} />
      <LinkRow label={t('btn.review_consent')} onPress={() => router.push('/onboarding/consent' as Href)} />
      <PrivacyNotice visible={notice} onClose={() => setNotice(false)} />
    </SettingsSection>
  );
}

export default function SettingsScreen() {
  const t = useT();
  const { config, cached } = useServerConfig();
  return (
    <Screen title={t('tabs.settings')} testID="settings-screen">
      <LanguageSection />
      <ReadingSection />
      <RegionSection />
      <ToneSection />
      <DataSection />
      <VaultAndDataSettings />
      <AboutSection config={config} cached={cached} />
      {isProduction ? null : (
        <DeveloperSection
          apiUrl={env.apiUrl}
          config={config}
          getInstallId={getInstallId}
          rotateInstallId={rotateInstallId}
        />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  inline: {
    alignItems: 'center',
    gap: space.sm,
  },
  input: {
    flex: 1,
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    fontSize: 18,
  },
});
