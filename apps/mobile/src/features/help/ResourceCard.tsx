// One resource card (PRODUCT_SPEC S11). Everything shown comes from the vetted DB entry or pack
// keys: name (+ name_note), what it does (EN chip on fallback), why-chips, cost, status note (the
// LSC note is never hidden) with "If that is not you", Call / Website, TTY / text / hours,
// languages, eligibility, warnings, "Verified on" (+ link-health / stale lines), the checklist,
// and counts-only feedback. Phones, URLs, hours and the "Verified on" date are LTR-isolated: after
// a Dari or Arabic word a bare "1-800-323-8603" or "2026-09-27" would show its groups reversed
// (UAX #9: digits after Arabic letters become Arabic numbers). The Call button's S11 screen-reader
// line "Call {organization}, {digits grouped}" (`callLabel`) rides as its accessibilityHint: BigButton
// (design/components, WP4) has no accessibilityLabel override yet, so its label is the visible
// "Call 1-800-…" text (CL-076 — when the prop lands, pass `callLabel` as the label and drop the hint).
// Chip / warning React keys are text + index (the same text may come twice).

import { Linking, StyleSheet, View } from 'react-native';

import type { ChecklistItem as ApiChecklistItem, Resource, StatusNoteKey } from '@/api/types';
import {
  Bidi,
  BigButton,
  Checklist,
  Collapsible,
  FeedbackRow,
  Heading,
  AppText,
  isolate,
  openExternal,
} from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';

import { Chip, ChipRow } from './Chip';
import {
  callLabel,
  COST_KEYS,
  formatPhone,
  isStale,
  languagesLine,
  linkNoteKey,
  localized,
  prepareText,
  telHref,
  whyText,
} from './format';

export interface ResourceCardProps {
  resource: Resource;
  whyKeys?: string[];
  why?: string[];
  eligibilityNoteKey?: StatusNoteKey | null;
  checklist?: ApiChecklistItem[];
  checkState?: Record<string, boolean>;
  onToggleCheck?(id: string, checked: boolean): void;
  /** Expand the checklist (focused card / first result). */
  focused?: boolean;
  /** The primary action of the screen (first result): Call is 72 pt. */
  primary?: boolean;
  onLscAlternative?(): void;
}

export function ResourceCard({
  resource,
  whyKeys = [],
  why = [],
  eligibilityNoteKey,
  checklist = [],
  checkState = {},
  onToggleCheck,
  focused,
  primary,
  onLscAlternative,
}: ResourceCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const meta = usePackMeta();
  const lang = meta.tag;
  const what = localized(resource.what_it_does, lang);
  const eligibility = localized(resource.eligibility_plain, lang);
  const noteKey = eligibilityNoteKey ?? resource.status_note_key ?? null;
  const whyChips = whyKeys
    .map((k, i) => whyText(k, why[i], t))
    .filter((w): w is string => Boolean(w));
  const linkNote = linkNoteKey(resource.link_health);
  const langs = languagesLine(resource.languages ?? [], t);
  const items = checklist
    .map((c) => ({ id: c.key, text: prepareText(c.key, c.text_en, t) }))
    .filter((c): c is { id: string; text: string } => Boolean(c.text));
  const nameLine = resource.name_note ? `${resource.name} (${resource.name_note})` : resource.name;
  const call = () => {
    if (resource.phone) void Linking.openURL(telHref(resource.phone));
  };

  return (
    <View
      role="region"
      accessibilityLabel={resource.name}
      nativeID={`resource-${resource.id}`}
      testID={`resource-${resource.id}`}
      style={[styles.card, { backgroundColor: colors.surface, borderColor: focused ? colors.primary : colors.divider }]}>
      <Heading level={3} variant="bodyLarge">
        {nameLine}
      </Heading>
      {what ? (
        <View style={[styles.inline, { flexDirection: dir.row }]}>
          <View style={styles.flex}>
            <AppText lang={what.english ? 'en' : undefined}>{what.text}</AppText>
          </View>
          {what.english && lang !== 'en' ? <Chip text="EN" lang="en" /> : null}
        </View>
      ) : null}
      <ChipRow>
        <Chip text={t(COST_KEYS[resource.cost] ?? 'resource.unknown_cost')} tone={resource.cost === 'free' ? 'success' : 'neutral'} />
        {whyChips.map((w, i) => (
          <Chip key={`${w}-${i}`} text={w} icon="check" />
        ))}
      </ChipRow>
      {noteKey ? (
        <View role="note" style={[styles.note, { borderColor: colors.warning }]}>
          <AppText>{t(`status_note.${noteKey}`)}</AppText>
          {noteKey === 'lsc_restricted' && onLscAlternative ? (
            <BigButton label={t('help.lsc_alternative')} variant="secondary" size={56} onPress={onLscAlternative} />
          ) : null}
        </View>
      ) : null}
      {resource.phone ? (
        <BigButton
          label={`${t('btn.call')} ${isolate(formatPhone(resource.phone))}`}
          icon="phone"
          variant={primary ? 'primary' : 'secondary'}
          size={primary ? 72 : 56}
          onPress={call}
          accessibilityHint={callLabel(resource, t)}
        />
      ) : null}
      {resource.url ? (
        <BigButton
          label={t('btn.website')}
          icon="globe"
          variant={primary && !resource.phone ? 'primary' : 'secondary'}
          size={primary && !resource.phone ? 72 : 56}
          onPress={() => void openExternal(resource.url)}
          accessibilityHint={resource.name}
        />
      ) : null}
      {resource.tty ? (
        <AppText variant="caption">{t('resource.tty', { number: isolate(formatPhone(resource.tty)) })}</AppText>
      ) : null}
      {resource.text_line ? <Bidi variant="caption">{resource.text_line}</Bidi> : null}
      {resource.hours ? <Bidi variant="caption">{resource.hours}</Bidi> : null}
      {langs ? <AppText variant="caption">{langs}</AppText> : null}
      {eligibility ? <AppText variant="caption" lang={eligibility.english ? 'en' : undefined}>{eligibility.text}</AppText> : null}
      {(resource.warnings ?? []).map((w, i) => (
        <AppText key={`${w}-${i}`} variant="caption" color="warning">
          {t(w)}
        </AppText>
      ))}
      <ChipRow>
        <Chip text={t('resource.verified_on', { date: isolate(resource.verified_on) })} icon="check" />
        {isStale(resource.verified_on) ? <Chip text={t('resource.stale')} tone="warning" /> : null}
        {linkNote ? <Chip text={t(linkNote)} tone="warning" /> : null}
      </ChipRow>
      {items.length ? (
        <Collapsible title={t('quicksheet.bring')} initiallyOpen={focused}>
          <Checklist items={items} state={checkState} onToggle={(id, on) => onToggleCheck?.(id, on)} />
        </Collapsible>
      ) : null}
      <FeedbackRow surface="resource" resourceId={resource.id} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.sm,
  },
  inline: {
    alignItems: 'flex-start',
    gap: space.sm,
  },
  flex: {
    flex: 1,
  },
  note: {
    borderStartWidth: 4,
    paddingStart: space.md,
    gap: space.sm,
  },
});
