// Match results grouped "Near you" / "Anywhere in the U.S." (by `serves.scope`), then
// "Always available" (`national_fallbacks`), then `notes_keys` info lines and the fixed
// general-information disclaimer (PRODUCT_SPEC S11). Broken links are never shown.

import { StyleSheet, View } from 'react-native';

import type { ResourceMatch, ResourceMatchResponse } from '@/api/types';
import { AppText, Heading, Icon } from '@/design/components';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

import { disclaimerKey, isVisible } from './format';
import { ResourceCard } from './ResourceCard';

export interface ResourceListProps {
  data: ResourceMatchResponse;
  /** The person has told us their state (Settings). */
  regionKnown: boolean;
  checkState?: Record<string, boolean>;
  onToggleCheck?(id: string, checked: boolean): void;
  focusId?: string | null;
  onLscAlternative?(): void;
  /** Results of "If that is not you, try these instead", shown under the main results. */
  lscAlternative?: ResourceMatchResponse | null;
}

function InfoLine({ text }: { text: string }) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View style={[styles.info, { flexDirection: dir.row }]}>
      <Icon name="info" size={20} color={colors.textMuted} />
      <View style={styles.flex}>
        <AppText variant="caption" color="textMuted">
          {text}
        </AppText>
      </View>
    </View>
  );
}

export function ResourceList({
  data,
  regionKnown,
  checkState,
  onToggleCheck,
  focusId,
  onLscAlternative,
  lscAlternative,
}: ResourceListProps) {
  const t = useT();
  const visible = (data.results ?? []).filter((m) => isVisible(m.resource));
  const near = visible.filter((m) => m.resource.serves?.scope !== 'national');
  const anywhere = visible.filter((m) => m.resource.serves?.scope === 'national');
  const shownIds = new Set(visible.map((m) => m.resource.id));
  const fallbacks = (data.national_fallbacks ?? []).filter((r) => isVisible(r) && !shownIds.has(r.id));
  const firstId = visible[0]?.resource.id ?? fallbacks[0]?.id ?? null;
  const altResults = (lscAlternative?.results ?? []).filter((m) => isVisible(m.resource) && !shownIds.has(m.resource.id));

  const card = (m: ResourceMatch) => (
    <ResourceCard
      key={m.resource.id}
      resource={m.resource}
      whyKeys={m.why_keys}
      why={m.why}
      eligibilityNoteKey={m.eligibility_note_key}
      checklist={m.checklist}
      checkState={checkState}
      onToggleCheck={onToggleCheck}
      focused={focusId ? focusId === m.resource.id : m.resource.id === firstId}
      primary={m.resource.id === firstId}
      onLscAlternative={onLscAlternative}
    />
  );

  return (
    <View style={styles.list}>
      {regionKnown && near.length === 0 ? <InfoLine text={t('state.no_local')} /> : null}
      {near.length ? (
        <View style={styles.group}>
          <Heading level={2}>{t('help.near_you')}</Heading>
          {near.map(card)}
        </View>
      ) : null}
      {anywhere.length ? (
        <View style={styles.group}>
          <Heading level={2}>{t('help.anywhere_in_us')}</Heading>
          {anywhere.map(card)}
        </View>
      ) : null}
      {altResults.length ? (
        <View style={styles.group} testID="lsc-alternative">
          <Heading level={2}>{t('help.lsc_alternative')}</Heading>
          {altResults.map(card)}
        </View>
      ) : null}
      {fallbacks.length ? (
        <View style={styles.group}>
          <Heading level={2}>{t('help.always')}</Heading>
          {fallbacks.map((r) => (
            <ResourceCard
              key={r.id}
              resource={r}
              primary={r.id === firstId}
              focused={focusId === r.id}
              eligibilityNoteKey={r.status_note_key}
              onLscAlternative={onLscAlternative}
            />
          ))}
        </View>
      ) : null}
      {(data.notes_keys ?? []).map((k) => (
        <InfoLine key={k} text={t(k)} />
      ))}
      <InfoLine text={t(disclaimerKey(data.disclaimer_kind))} />
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: space.xl,
  },
  group: {
    gap: space.md,
  },
  info: {
    gap: space.sm,
    alignItems: 'flex-start',
  },
  flex: {
    flex: 1,
  },
});
