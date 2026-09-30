// S19 emergency card (D-14, PRODUCT_SPEC S19, COMPLIANCE_PRIVACY §7). Fixed copy only — never
// model text. Four rows with 72 pt call/text buttons (`tel:` / `sms:`), numbers LTR-isolated, a
// speaker on every line. On desktop web the numbers are shown large with "Use a phone to call."

import { Linking, Platform, StyleSheet, View } from 'react-native';

import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useVoiceNotice } from '@/features/speech';
import { useDirection } from '@/i18n/direction';
import { keyExists } from '@/i18n/store';
import { usePackMeta, useT, type TFunction } from '@/i18n/useT';

export interface EmergencyRow {
  id: '911' | '988' | 'poison' | 'dv';
  lineKey: string;
  display: string;
  actions: { labelKey: string; href: string; icon: 'phone' | 'info' }[];
}

/** The four fixed rows (order is part of the spec). */
export const EMERGENCY_ROWS: readonly EmergencyRow[] = [
  { id: '911', lineKey: 'emergency.911', display: '911', actions: [{ labelKey: 'btn.call_911', href: 'tel:911', icon: 'phone' }] },
  {
    id: '988',
    lineKey: 'emergency.988',
    display: '988',
    actions: [
      { labelKey: 'btn.call_988', href: 'tel:988', icon: 'phone' },
      { labelKey: 'btn.text_988', href: 'sms:988', icon: 'info' },
    ],
  },
  {
    id: 'poison',
    lineKey: 'emergency.poison',
    display: '1-800-222-1222',
    actions: [{ labelKey: 'btn.call_poison', href: 'tel:18002221222', icon: 'phone' }],
  },
  {
    id: 'dv',
    lineKey: 'emergency.dv',
    display: '1-800-799-7233',
    actions: [
      { labelKey: 'btn.call_dv', href: 'tel:18007997233', icon: 'phone' },
      { labelKey: 'btn.text_dv', href: 'sms:88788?body=START', icon: 'info' },
    ],
  },
];

/** `emergency_kinds` → fixed words (unknown kinds are dropped, never shown raw). */
export function emergencyKindWords(kinds: string[], t: TFunction): string[] {
  const out: string[] = [];
  for (const k of kinds) {
    const key = `emergency.kind.${k}`;
    if (keyExists(key)) {
      const word = t(key);
      if (!out.includes(word)) out.push(word);
    }
  }
  return out;
}

/** Desktop browsers cannot dial: no touch points and a wide window. */
export function isDesktopWeb(): boolean {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined') return false;
  const touch = (navigator as Navigator & { maxTouchPoints?: number }).maxTouchPoints ?? 0;
  return touch === 0;
}

export function openHref(href: string): void {
  void Linking.openURL(href).catch(() => undefined);
}

export interface EmergencyCardProps {
  /** `Safety.emergency_kinds` values that drive the context line. */
  kinds: string[];
  onClose(): void;
  /** Rendered inside the S7 result (no Close button, not a modal). */
  inline?: boolean;
  /** `emergency.more_help` → S11. */
  onMoreHelp?(): void;
  /** True when a paper or a chat answer triggered the card (shows `emergency.triggered_by`). */
  triggered?: boolean;
}

export function EmergencyCard({ kinds, onClose, inline, onMoreHelp, triggered }: EmergencyCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const meta = usePackMeta();
  const desktop = isDesktopWeb();
  const words = emergencyKindWords(kinds, t);
  const showContext = (triggered ?? kinds.length > 0) && words.length > 0;
  const contextLine = showContext ? t('emergency.triggered_by', { kinds: words.join(', ') }) : null;
  // Honest TTS line (D-26), resolved up front so a Dari user learns before tapping that the lines
  // will be read with a Farsi voice. Inline in S7 the result footer already shows the same line.
  const voiceNotice = useVoiceNotice(meta.tag);
  return (
    <View
      testID="emergency-card"
      role="region"
      accessibilityLabel={t('emergency.title')}
      style={[styles.card, { borderColor: colors.danger, backgroundColor: colors.surfaceRaised }]}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <View style={styles.flex}>
          <Heading level={inline ? 2 : 1}>{t('emergency.title')}</Heading>
        </View>
        <SpeakButton text={t('emergency.title')} lang={meta.tag} />
      </View>
      {voiceNotice && !inline ? (
        <AppText variant="caption" color="textMuted" role="status" testID="tts-fallback-notice">
          {voiceNotice}
        </AppText>
      ) : null}
      {contextLine ? (
        <View style={[styles.row, { flexDirection: dir.row }]}>
          <View style={styles.flex}>
            <AppText weight="bold">{contextLine}</AppText>
          </View>
          <SpeakButton text={contextLine} lang={meta.tag} />
        </View>
      ) : null}
      {EMERGENCY_ROWS.map((row) => (
        <View key={row.id} testID={`emergency-row-${row.id}`} style={[styles.block, { borderTopColor: colors.divider }]}>
          <View style={[styles.row, { flexDirection: dir.row }]}>
            <View style={styles.flex}>
              <AppText variant="bodyLarge">{t(row.lineKey)}</AppText>
            </View>
            <SpeakButton text={t(row.lineKey)} lang={meta.tag} />
          </View>
          {desktop ? (
            <Bidi dir="ltr" variant="display" weight="bold">
              {row.display}
            </Bidi>
          ) : null}
          {row.actions.map((a) => (
            <BigButton
              key={a.href}
              label={t(a.labelKey)}
              icon={a.icon}
              variant={a.icon === 'phone' ? 'danger' : 'secondary'}
              size={72}
              onPress={() => openHref(a.href)}
            />
          ))}
        </View>
      ))}
      {desktop ? <AppText color="textMuted">{t('emergency.desktop_note')}</AppText> : null}
      <AppText color="textMuted">{t('emergency.free_us')}</AppText>
      {onMoreHelp ? (
        <BigButton label={t('emergency.more_help')} icon="help" variant="secondary" size={56} onPress={onMoreHelp} />
      ) : null}
      {inline ? null : <BigButton label={t('btn.close')} icon="close" variant="secondary" size={56} onPress={onClose} />}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 3,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
  },
  row: {
    alignItems: 'center',
    gap: space.md,
  },
  flex: {
    flex: 1,
  },
  block: {
    gap: space.sm,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
