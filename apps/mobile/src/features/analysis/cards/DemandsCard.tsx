// Card 2 — "What is it asking for?" (PRODUCT_SPEC S7 item 8). One row per VERIFIED demand: kind
// icon, plain text, the value exactly as printed (LTR-isolated, bold), role word, date rendering
// by `DateInfo.kind`, the anchored fact row, "Remind me" only when `reminder_eligible`, and
// "Call (number from your paper)" only for a contact number printed on the page.

import { StyleSheet, View } from 'react-native';

import type { Demand } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { Card } from '@/design/components/Card';
import { Icon } from '@/design/components/Icon';
import { Interpolated } from '@/design/components/Interpolated';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { keyExists } from '@/i18n/store';
import { useBidiText, usePackMeta, useT, type TFunction } from '@/i18n/useT';
import { extraDateLine } from '@/lib/dates';
import { useSettings } from '@/store/settings';

import { printedPhoneHref } from '../urgencyCopy';
import { DEMAND_ICONS, FactRow, type ResultCardProps, type ResultHandlers, SourceText } from './shared';

export function roleWord(role: string | null, t: TFunction): string | null {
  if (!role || role === 'other') return null;
  const key = `role.${role}`;
  return keyExists(key) ? t(key) : null;
}

/** A reminder button is offered only for verified, reminder-eligible demands (never unverified). */
export function canRemind(d: Demand): boolean {
  return d.verified && d.reminder_eligible;
}

function DateLines({ d, handlers, lang }: { d: Demand; handlers: ResultHandlers; lang: string }) {
  const t = useT();
  const meta = usePackMeta();
  const order = useSettings((s) => s.preferences.dateFormat);
  const date = d.date;
  if (!date) return null;
  if (date.kind === 'estimated') {
    return (
      <View style={styles.lines}>
        <AppText>
          {t('demand.estimate_prefix')} {date.formula ? <Bidi dir="auto">{date.formula}</Bidi> : null}
        </AppText>
        {date.anchor_quote ? (
          <Interpolated
            template={t('demand.anchor')}
            vars={{ anchor_quote: date.anchor_quote }}
            ltrKeys={['anchor_quote']}
            color="textMuted"
          />
        ) : null}
        <AppText weight="bold">{t('demand.confirm_with_sender')}</AppText>
        {date.rule_source_url ? (
          <AppText
            color="link"
            role="link"
            onPress={() => handlers.onOpenUrl?.(date.rule_source_url ?? '')}
            accessibilityHint={date.rule_source_url}>
            {t('demand.rule_link')}
          </AppText>
        ) : null}
        {date.rule_verification === 'likely' ? <AppText color="textMuted">{t('demand.rule_likely')}</AppText> : null}
      </View>
    );
  }
  if (date.kind === 'unresolved') {
    return <AppText weight="bold">{t('demand.ask_sender_date')}</AppText>;
  }
  const extra = extraDateLine(date, meta.digitSystem, order);
  return (
    <View style={styles.lines}>
      {date.time_text ? (
        <SourceText lang={lang}>{date.time_text}</SourceText>
      ) : null}
      {extra ? <AppText color="textMuted">{extra}</AppText> : null}
    </View>
  );
}

export interface DemandRowProps extends ResultCardProps {
  demand: Demand;
}

export function DemandRow({ analysis, pages, handlers, demand: d }: DemandRowProps) {
  const t = useT();
  const bt = useBidiText();
  const { colors } = useTheme();
  const dir = useDirection();
  const role = roleWord(d.role, t);
  const phone = printedPhoneHref(d);
  return (
    <View testID={`demand-${d.id}`} style={[styles.row, { borderTopColor: colors.divider }]}>
      <View style={[styles.head, { flexDirection: dir.row }]}>
        <Icon name={DEMAND_ICONS[d.kind]} color={colors.primary} />
        <View style={styles.flex}>
          {role ? (
            <AppText variant="caption" weight="bold" color="textMuted">
              {role}
            </AppText>
          ) : null}
          <AppText lang={analysis.target_language}>{bt(d.text)}</AppText>
        </View>
      </View>
      <SourceText lang={analysis.detected_language} dir="ltr" variant="bodyLarge" weight="bold">
        {d.value_verbatim}
      </SourceText>
      <DateLines d={d} handlers={handlers} lang={analysis.detected_language} />
      {d.documents.length ? (
        <View style={styles.lines}>
          {d.documents.map((doc, i) => (
            <AppText key={`${d.id}-doc-${i}`}>
              {'• '}
              <Bidi dir="auto">{doc}</Bidi>
            </AppText>
          ))}
        </View>
      ) : null}
      {d.ambiguity_note ? (
        <AppText color="textMuted" style={styles.italic}>
          {d.ambiguity_note}
        </AppText>
      ) : null}
      <FactRow
        analysis={analysis}
        pages={pages}
        spanIds={d.span_ids}
        page={d.page}
        quote={d.source_quote}
        confidence={d.confidence}
        handlers={handlers}
        testID={`fact-${d.id}`}
      />
      {canRemind(d) && handlers.onRemind ? (
        <BigButton
          testID={`remind-${d.id}`}
          label={t('btn.remind_me')}
          icon="calendar"
          variant="primary"
          size={56}
          onPress={() => handlers.onRemind?.(d)}
        />
      ) : null}
      {phone && handlers.onCall ? (
        <BigButton label={t('btn.call_printed')} icon="phone" variant="secondary" size={56} onPress={() => handlers.onCall?.(phone)} />
      ) : null}
    </View>
  );
}

export function demandsSpeech(demands: Demand[]): string {
  return demands.map((d) => `${d.text} ${d.value_verbatim}`).join('. ');
}

export function DemandsCard(props: ResultCardProps) {
  const t = useT();
  const demands = props.analysis.demands.filter((d) => d.verified);
  return (
    <Card
      id="card-asking-for"
      headingKey="card.asking_for"
      lang={props.analysis.target_language}
      speakText={demands.length ? demandsSpeech(demands) : t('card.asking_nothing')}>
      {demands.length ? (
        demands.map((d) => <DemandRow key={d.id} {...props} demand={d} />)
      ) : (
        <AppText>{t('card.asking_nothing')}</AppText>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.sm,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  head: {
    gap: space.sm,
    alignItems: 'flex-start',
  },
  flex: {
    flex: 1,
  },
  lines: {
    gap: space.xs,
  },
  italic: {
    fontStyle: 'italic',
  },
});
