// S7 items 2, 3 and 14: scam card (fixed copy + the vetted `scam_report` contacts it ends with —
// "Report it:" — + reason chips, D-13, J-F step 4), warning chips (fixed copy, §5.6) and red flags (fixed notices by `fixed_copy_key` (D-20), model flags with their quote,
// `injection_suspected` → `warning.injection_masked`), sorted by severity, most severe first.

import { StyleSheet, View } from 'react-native';

import type { RedFlag, Severity } from '@/api/types';
import { Card } from '@/design/components/Card';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { ScamReportResources } from '@/features/troubleshoot/ScamReport';
import { useDirection } from '@/i18n/direction';
import { keyExists, languageInfoFor } from '@/i18n/store';
import { useBidiText, usePackMeta, useT, type TFunction } from '@/i18n/useT';

import { warningChipKeys } from '../disclaimers';
import { type ResultCardProps, SourceText } from './shared';

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

export function sortRedFlags(flags: readonly RedFlag[]): RedFlag[] {
  return flags.slice().sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

/** True when the flag is shown as fixed copy (UI pack language), false for model text. */
export function redFlagIsFixedCopy(f: RedFlag): boolean {
  return f.kind === 'injection_suspected' || Boolean(f.fixed_copy_key && keyExists(f.fixed_copy_key));
}

/** Fixed copy for a flag when it has one (never model text for fixed notices). */
export function redFlagText(f: RedFlag, t: TFunction): string {
  if (f.kind === 'injection_suspected') return t('warning.injection_masked');
  if (f.fixed_copy_key && keyExists(f.fixed_copy_key)) return t(f.fixed_copy_key);
  return f.text;
}

export function RedFlagsCard({ analysis }: ResultCardProps) {
  const t = useT();
  const bt = useBidiText();
  const { colors } = useTheme();
  const dir = useDirection();
  const flags = sortRedFlags(analysis.red_flags);
  const injection = analysis.verification.injection_masked && !flags.some((f) => f.kind === 'injection_suspected');
  if (!flags.length && !injection) return null;
  const texts = flags.map((f) => redFlagText(f, t));
  if (injection) texts.push(t('warning.injection_masked'));
  return (
    <Card id="card-red-flags" headingKey="card.red_flags" lang={analysis.target_language} speakText={texts.join('. ')}>
      {flags.map((f, i) => (
        <View key={`rf-${i}`} testID={`red-flag-${f.kind}`} style={[styles.flag, { flexDirection: dir.row, borderTopColor: colors.divider }]}>
          <Icon name="flag" color={f.severity === 'high' ? colors.danger : colors.warning} />
          <View style={styles.flex}>
            <AppText weight={f.severity === 'high' ? 'bold' : 'regular'}>{bt(redFlagText(f, t))}</AppText>
            {f.source_quote && !f.fixed_copy_key && f.kind !== 'injection_suspected' ? (
              <SourceText lang={analysis.detected_language} variant="caption">{`“${f.source_quote}”`}</SourceText>
            ) : null}
          </View>
        </View>
      ))}
      {injection ? <AppText>{t('warning.injection_masked')}</AppText> : null}
    </Card>
  );
}

export function ScamCard({ analysis }: ResultCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  if (analysis.scam_risk !== 'likely' && analysis.scam_risk !== 'possible') return null;
  const key = analysis.scam_risk === 'likely' ? 'scam.card.likely' : 'scam.card.possible';
  const reasons = analysis.scam_reasons.filter((r) => keyExists(r)).map((r) => t(r));
  return (
    <Card
      id="card-scam"
      headingKey="card.red_flags"
      lang={analysis.target_language}
      speakText={[t(key), ...reasons].join('. ')}
      accentColor={colors.danger}>
      <View style={[styles.flag, { flexDirection: dir.row }]}>
        <Icon name="alert" color={colors.danger} size={28} />
        <View style={styles.flex}>
          <AppText weight="bold">{t(key)}</AppText>
        </View>
      </View>
      {/* Where to report it: DHS OIG / FTC from the vetted DB (bundled subset offline), never model text. */}
      <ScamReportResources risk={analysis.scam_risk} />
      {reasons.length ? (
        <View style={[styles.chips, { flexDirection: dir.row }]}>
          {reasons.map((r) => (
            <View key={r} style={[styles.chip, { borderColor: colors.danger }]}>
              <AppText variant="caption" weight="bold" color="danger">
                {r}
              </AppText>
            </View>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

export function WarningChips({ analysis }: ResultCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const meta = usePackMeta();
  const tier = meta.tag === analysis.target_language ? meta.tier : languageInfoFor(analysis.target_language).tier;
  const keys = warningChipKeys(analysis.warnings, { packTier: tier });
  const unreadable = analysis.quality.pages_unreadable;
  if (!keys.length && !unreadable.length) return null;
  return (
    <View testID="warning-chips" role="list" style={[styles.chips, { flexDirection: dir.row }]}>
      {keys.map((k) => (
        <View key={k} role="listitem" style={[styles.chip, { borderColor: colors.warning, flexDirection: dir.row }]}>
          <Icon name="alert" size={18} color={colors.warning} />
          <AppText variant="caption">{t(k)}</AppText>
        </View>
      ))}
      {unreadable.map((n) => (
        <View key={`pu-${n}`} role="listitem" style={[styles.chip, { borderColor: colors.warning, flexDirection: dir.row }]}>
          <Icon name="alert" size={18} color={colors.warning} />
          <AppText variant="caption">{t('state.page_unreadable', { n })}</AppText>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  flag: {
    gap: space.sm,
    alignItems: 'flex-start',
    paddingTop: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  flex: {
    flex: 1,
    gap: space.xs,
  },
  chips: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    maxWidth: '100%',
  },
});
