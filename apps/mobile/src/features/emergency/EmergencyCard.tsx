// S19 emergency card (D-14, PRODUCT_SPEC S19, COMPLIANCE_PRIVACY §7). Fixed copy only — never
// model text. Four rows with 72 pt call/text buttons (`tel:` / `sms:`), numbers LTR-isolated, a
// speaker on every line. On desktop web the numbers are shown large with "Use a phone to call."
// The hotline numbers inside each line (`1-800-222-1222` in Arabic-script text) are isolated too:
// without it, bidi rule W2 turns the digit groups into Arabic numbers and the hyphens reorder them
// ("1222-222-800-1"), and on a phone that line is the only place the number is printed.
// Screen readers and the speaker get every number digit-grouped (`digitGroupedForSpeech`): "9 1 1",
// "1, 8 0 0, 2 2 2, 1 2 2 2" — never "nine hundred eleven" or "one thousand eight hundred…"
// (PRODUCT_SPEC S19 "numbers announced digit-grouped").

import type { ReactNode } from 'react';
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
  /** `call` → `tel:` (danger button, phone glyph); `text` → `sms:` (secondary; the icon set has
   *  no message glyph yet, and the old "info" circle suggested "more information"). */
  actions: { labelKey: string; href: string; kind: 'call' | 'text' }[];
}

/** The four fixed rows (order is part of the spec). */
export const EMERGENCY_ROWS: readonly EmergencyRow[] = [
  { id: '911', lineKey: 'emergency.911', display: '911', actions: [{ labelKey: 'btn.call_911', href: 'tel:911', kind: 'call' }] },
  {
    id: '988',
    lineKey: 'emergency.988',
    display: '988',
    actions: [
      { labelKey: 'btn.call_988', href: 'tel:988', kind: 'call' },
      { labelKey: 'btn.text_988', href: 'sms:988', kind: 'text' },
    ],
  },
  {
    id: 'poison',
    lineKey: 'emergency.poison',
    display: '1-800-222-1222',
    actions: [{ labelKey: 'btn.call_poison', href: 'tel:18002221222', kind: 'call' }],
  },
  {
    id: 'dv',
    lineKey: 'emergency.dv',
    display: '1-800-799-7233',
    actions: [
      { labelKey: 'btn.call_dv', href: 'tel:18007997233', kind: 'call' },
      { labelKey: 'btn.text_dv', href: 'sms:88788?body=START', kind: 'text' },
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

/** Phone-like runs: digit groups joined by hyphens (`1-800-222-1222`), ASCII or Arabic-Indic. */
const PHONE_RUN = /[0-9\u0660-\u0669\u06f0-\u06f9]+(?:[-\u2010\u2011][0-9\u0660-\u0669\u06f0-\u06f9]+)+/g;

/** Three or more digits in a row that are not part of a hyphenated phone run (`911`, `88788`). */
const DIGIT_RUN = /[0-9\u0660-\u0669\u06f0-\u06f9]{3,}/g;

function spaced(group: string): string {
  return [...group].join(' ');
}

/** A number as a screen reader / TTS voice should say it: digit by digit, groups set apart. */
export function spokenNumber(display: string): string {
  return display
    .split(/[-\u2010\u2011\s]+/)
    .filter(Boolean)
    .map(spaced)
    .join(', ');
}

/** The fixed line with every number digit-grouped for speech (`1-800-222-1222` → `1, 8 0 0, 2 2 2,
 *  1 2 2 2`; `911` → `9 1 1`). Shown text keeps the printed form. */
export function digitGroupedForSpeech(text: string): string {
  return text.replace(PHONE_RUN, (run) => spokenNumber(run)).replace(DIGIT_RUN, (run) => spaced(run));
}

/** Split a fixed line into text and phone-number parts (numbers get an LTR isolate). */
export function phoneParts(text: string): { text: string; phone: boolean }[] {
  const out: { text: string; phone: boolean }[] = [];
  let last = 0;
  for (const m of text.matchAll(PHONE_RUN)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ text: text.slice(last, at), phone: false });
    out.push({ text: m[0], phone: true });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), phone: false });
  return out;
}

/** The line with every phone number LTR-isolated (a `<Bidi dir="ltr">` span / LRI…PDI). */
export function withIsolatedPhones(text: string): ReactNode[] {
  return phoneParts(text).map((p, i) =>
    p.phone ? (
      <Bidi key={`n${i}`} dir="ltr">
        {p.text}
      </Bidi>
    ) : (
      p.text
    ),
  );
}

/** Desktop browsers cannot dial: no touch points and a wide window. */
export function isDesktopWeb(): boolean {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined') return false;
  const touch = (navigator as Navigator & { maxTouchPoints?: number }).maxTouchPoints ?? 0;
  return touch === 0;
}

/** The number a `tel:` / `sms:` action dials (`sms:88788?body=START` → `88788`). */
export function actionNumber(href: string): string {
  return href.replace(/^(tel|sms):/, '').replace(/\?.*$/, '');
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
              <AppText variant="bodyLarge" testID={`emergency-line-${row.id}`} accessibilityLabel={digitGroupedForSpeech(t(row.lineKey))}>
                {withIsolatedPhones(t(row.lineKey))}
              </AppText>
            </View>
            <SpeakButton text={digitGroupedForSpeech(t(row.lineKey))} lang={meta.tag} />
          </View>
          {desktop ? (
            <Bidi dir="ltr" variant="display" weight="bold" accessibilityLabel={spokenNumber(row.display)}>
              {row.display}
            </Bidi>
          ) : null}
          {row.actions.map((a) => (
            <BigButton
              key={a.href}
              testID={`emergency-action-${a.labelKey}`}
              label={t(a.labelKey)}
              icon={a.kind === 'call' ? 'phone' : undefined}
              variant={a.kind === 'call' ? 'danger' : 'secondary'}
              size={72}
              accessibilityHint={spokenNumber(a.kind === 'call' ? row.display : actionNumber(a.href))}
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
