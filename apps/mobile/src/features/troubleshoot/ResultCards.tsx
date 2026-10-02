// S16 result cards (PRODUCT_SPEC S16): scam card first when `scam_risk` ≠ none; the credential
// guard emphasised red when `asks_for_credentials_or_payment`; "What this screen is"; "What the red
// text means" (quoted error LTR-isolated with an EN chip; hidden when null); "Do this next" (steps
// in order, the on-screen label as written in bold, each with a checkbox); "Careful"; red flags;
// "Ask a person" → S11 with `resource_tags` (primary when `needs_human_help`); confidence chip;
// the fixed general-information disclaimer; counts-only feedback. In scam mode the DB reporting
// resources follow the scam card (J-F) and "Save as proof" follows the screen summary.

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import type { TroubleshootResult, TroubleshootStep } from '@/api/types';
import { AppText, Bidi, BigButton, Card, ConfidenceChip, FeedbackRow, Icon } from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { Chip, ChipRow } from '@/features/help/Chip';
import { disclaimerKey } from '@/features/help/format';
import { ScamNotice } from '@/features/help/HelpForDocument';
import { memberName, savedAnnouncement } from '@/features/vault/members';
import { useDirection } from '@/i18n/direction';
import { keyExists } from '@/i18n/store';
import { useT } from '@/i18n/useT';

import { ScamReportResources } from './ScamReport';

export function askPersonHref(result: Pick<TroubleshootResult, 'resource_tags'>): Href {
  const tags = (result.resource_tags ?? []).join(',');
  return (tags ? `/help?tags=${encodeURIComponent(tags)}` : '/help') as Href;
}

/** The standing guard line; red and with the detection sentence when the screen asks for secrets. */
export function CredentialGuard({ detected }: { detected: boolean }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View
      role={detected ? 'alert' : 'note'}
      testID={detected ? 'credential-guard-detected' : 'credential-guard'}
      style={[
        styles.guard,
        { flexDirection: dir.row, borderColor: detected ? colors.danger : colors.divider },
        detected ? styles.guardStrong : null,
      ]}>
      <Icon name="lock" color={detected ? colors.danger : colors.textMuted} />
      <View style={styles.flex}>
        {detected ? (
          <AppText weight="bold" color="danger">
            {t('troubleshoot.credential_detected')}
          </AppText>
        ) : null}
        <AppText variant={detected ? 'body' : 'caption'} color={detected ? 'danger' : 'textMuted'}>
          {t('troubleshoot.credential_guard')}
        </AppText>
      </View>
    </View>
  );
}

function StepRow({ step, checked, onToggle }: { step: TroubleshootStep; checked: boolean; onToggle(): void }) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <Pressable
      role="checkbox"
      aria-checked={checked}
      accessibilityState={{ checked }}
      accessibilityLabel={step.text}
      hitSlop={size.hitSlop}
      onPress={onToggle}
      style={[styles.step, { flexDirection: dir.row }]}>
      <View style={[styles.box, { borderColor: colors.border, backgroundColor: checked ? colors.primary : 'transparent' }]}>
        {checked ? <Icon name="check" size={20} color={colors.onPrimary} /> : null}
      </View>
      <View style={styles.flex}>
        <AppText>{`${step.order}. ${step.text}`}</AppText>
        {step.ui_target_as_written ? (
          <View style={[styles.inline, { flexDirection: dir.row }]}>
            <Bidi weight="bold" variant="body">
              {step.ui_target_as_written}
            </Bidi>
            <Chip text="EN" lang="en" />
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

/** "Save as proof" (scam mode, a picked screenshot only). */
export interface EvidenceControl {
  onSave(): void;
  saved: boolean;
  busy: boolean;
  failed: boolean;
  /** Display name of the member the proof was saved for (defaults to "Me"). */
  member?: string;
}

export function EvidenceButton({ evidence }: { evidence: EvidenceControl }) {
  const t = useT();
  return (
    <View style={styles.wrap}>
      <BigButton
        label={t('btn.save_evidence')}
        icon={evidence.saved ? 'check' : 'papers'}
        variant="secondary"
        size={56}
        onPress={evidence.onSave}
        disabled={evidence.busy || evidence.saved}
        testID="troubleshoot-save-evidence"
      />
      {evidence.saved ? (
        // `vault.saved` ("It stays on this phone") is false on web, where the vault is memory-only
        // unless IndexedDB is opted in — the helper announces only `vault.saved_to` there (CL-042).
        <AppText role="status">{savedAnnouncement(t, evidence.member || memberName(null, t))}</AppText>
      ) : null}
      {evidence.failed ? (
        <AppText role="alert" color="danger">
          {t('err.internal')}
        </AppText>
      ) : null}
    </View>
  );
}

export function TroubleshootResultCards({
  result,
  evidence,
}: {
  result: TroubleshootResult;
  /** Present in scam mode when the person picked a screenshot (never for a sample). */
  evidence?: EvidenceControl | null;
}) {
  const t = useT();
  const { colors } = useTheme();
  const [done, setDone] = useState<Record<number, boolean>>({});
  const steps = [...(result.steps ?? [])].sort((a, b) => a.order - b.order);
  const cannotTell = result.confidence === 'low' && result.needs_human_help;
  const warnings = (result.warnings ?? []).map((w) => `warning.${w}`).filter((k) => keyExists(k));
  const speakSteps = steps.map((s) => `${s.order}. ${s.text}`).join(' ');

  return (
    <View style={styles.wrap} testID="troubleshoot-result">
      {result.scam_risk !== 'none' ? (
        <View style={styles.wrap}>
          <ScamNotice risk={result.scam_risk} />
          <ScamReportResources risk={result.scam_risk} />
          {result.scam_reasons?.length ? (
            <ChipRow>
              {result.scam_reasons
                .filter((r) => keyExists(`scam.${r}`))
                .map((r, i) => (
                  <Chip key={`${r}-${i}`} text={t(`scam.${r}`)} icon="alert" tone="danger" />
                ))}
            </ChipRow>
          ) : null}
        </View>
      ) : null}
      {result.asks_for_credentials_or_payment || result.safety?.credential_or_payment_request ? (
        <CredentialGuard detected />
      ) : null}
      {cannotTell ? (
        <AppText weight="bold" role="status">
          {t('state.cannot_tell')}
        </AppText>
      ) : null}
      {warnings.map((k, i) => (
        <AppText key={`${k}-${i}`} variant="caption" color="warning">
          {t(k)}
        </AppText>
      ))}
      <Card id="ts-screen" headingKey="troubleshoot.card_screen" speakText={result.screen_summary}>
        <AppText>{result.screen_summary}</AppText>
        <ConfidenceChip confidence={result.confidence} />
      </Card>
      {evidence ? <EvidenceButton evidence={evidence} /> : null}
      {result.error_text_quoted ? (
        <Card id="ts-error" headingKey="troubleshoot.card_error" speakText={result.error_meaning} accentColor={colors.danger}>
          <View style={[styles.quote, { borderColor: colors.danger }]}>
            <Bidi variant="body" weight="bold">
              {result.error_text_quoted}
            </Bidi>
            <Chip text="EN" lang="en" />
          </View>
          <AppText>{result.error_meaning}</AppText>
        </Card>
      ) : null}
      {steps.length ? (
        <Card id="ts-steps" headingKey="troubleshoot.card_steps" speakText={speakSteps}>
          {steps.map((s) => (
            <StepRow
              key={s.order}
              step={s}
              checked={Boolean(done[s.order])}
              onToggle={() => setDone((d) => ({ ...d, [s.order]: !d[s.order] }))}
            />
          ))}
        </Card>
      ) : null}
      {result.cautions?.length ? (
        <Card id="ts-cautions" headingKey="troubleshoot.card_cautions" speakText={result.cautions.join(' ')}>
          {result.cautions.map((c, i) => (
            <AppText key={`${c}-${i}`}>{c}</AppText>
          ))}
        </Card>
      ) : null}
      {result.red_flags?.length ? (
        <Card id="ts-red-flags" headingKey="card.red_flags" accentColor={colors.danger}>
          {result.red_flags.map((f, i) => (
            <AppText key={`${f.kind}-${i}`}>{f.fixed_copy_key && keyExists(f.fixed_copy_key) ? t(f.fixed_copy_key) : f.text}</AppText>
          ))}
        </Card>
      ) : null}
      <BigButton
        label={t('troubleshoot.ask_person')}
        icon="people"
        variant={result.needs_human_help ? 'primary' : 'secondary'}
        size={result.needs_human_help ? 72 : 56}
        onPress={() => router.push(askPersonHref(result))}
        testID="troubleshoot-ask-person"
      />
      <AppText variant="caption" color="textMuted">
        {t(disclaimerKey(result.disclaimer_kind))}
      </AppText>
      <FeedbackRow surface="troubleshoot" modelId={result.model_meta?.model_id ?? null} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  flex: {
    flex: 1,
    gap: space.xs,
  },
  guard: {
    gap: space.sm,
    alignItems: 'flex-start',
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
  },
  guardStrong: {
    borderWidth: 3,
  },
  step: {
    gap: space.md,
    alignItems: 'flex-start',
    minHeight: size.minTouch,
    paddingVertical: space.xs,
  },
  box: {
    width: 32,
    height: 32,
    borderWidth: 2,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inline: {
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
  },
  quote: {
    borderStartWidth: 4,
    paddingStart: space.md,
    gap: space.xs,
    alignItems: 'flex-start',
  },
});
