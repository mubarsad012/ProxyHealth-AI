// S12 — My papers (family vault; PRODUCT_SPEC S12, §9). Member chips ("Me", people with initials +
// colour, "Add someone"), search over title / sender / category words, rows sorted by next date
// then newest (grouped by person when more than one person has papers), Reminders link, empty
// state, web session-only / IndexedDB labels and the literally-true privacy lines (§9.5).

import { type Href, router } from 'expo-router';
import { useMemo, useState } from 'react';
import { Platform, StyleSheet, TextInput, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { LinkRow } from '@/design/components/SettingsRows';
import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { AppText, Heading } from '@/design/components/Text';
import { useScaled, useTheme } from '@/design/theme';
import { radius, size, space, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import { useVault } from '@/storage/StorageProvider';
import { useSettings } from '@/store/settings';

import { DocumentList } from './DocumentList';
import { useDocuments, useMembers } from './hooks';
import { MemberChip, MemberForm } from './MemberParts';
import { emptyVaultText, memberName, nextColor } from './members';
import { Sheet } from './Sheet';
import { bumpVault } from './store';

export function StorageNotice() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const webPersist = useSettings((s) => s.webPersist);
  const lines =
    Platform.OS === 'web'
      ? [webPersist === 'indexeddb' ? t('vault.web_kept') : t('banner.web_session_only'), t('vault.privacy_web')]
      : [t('vault.privacy_native')];
  return (
    <View role="note" style={[styles.notice, { flexDirection: dir.row, borderColor: colors.divider }]}>
      <Icon name="lock" color={colors.textMuted} />
      <View style={styles.flex}>
        {lines.map((line) => (
          <AppText key={line} variant="caption" color="textMuted">
            {line}
          </AppText>
        ))}
        <AppText variant="caption" color="textMuted">
          {t('vault.privacy_server')}
        </AppText>
      </View>
    </View>
  );
}

export function PapersScreen() {
  const t = useT();
  const { colors } = useTheme();
  const scaled = useScaled();
  const dir = useDirection();
  const vault = useVault();
  const [query, setQuery] = useState('');
  const [adding, setAdding] = useState(false);
  const { members } = useMembers();
  const { rows, loading } = useDocuments({ query });
  const withPapers = useMemo(() => new Set(rows.map((r) => r.memberId)), [rows]);
  const grouped = withPapers.size > 1;
  const empty = !loading && rows.length === 0 && query.trim() === '';

  return (
    <Screen title={t('tabs.papers')} testID="papers-screen">
      <LinkRow testID="papers-reminders-link" label={t('btn.reminders')} onPress={() => router.push('/reminders' as Href)} />
      <View role="radiogroup" accessibilityLabel={t('tabs.papers')} style={[styles.chips, { flexDirection: dir.row }]}>
        {members.map((m) => (
          <MemberChip
            key={m.id}
            testID={`papers-member-${m.id}`}
            member={m}
            onPress={() => router.push(`/papers/member/${encodeURIComponent(m.id)}` as Href)}
          />
        ))}
        <BigButton
          testID="papers-add-member"
          label={t('vault.add_member')}
          icon="people"
          variant="secondary"
          size={56}
          onPress={() => setAdding(true)}
        />
      </View>
      {empty ? (
        <EmptyState
          icon="papers"
          text={emptyVaultText(t)}
          actionLabel={t('btn.scan')}
          onAction={() => router.push('/' as Href)}
        />
      ) : (
        <>
          <View style={[styles.search, { flexDirection: dir.row, borderColor: colors.border }]}>
            <Icon name="search" color={colors.textMuted} />
            <TextInput
              testID="papers-search"
              value={query}
              onChangeText={setQuery}
              placeholder={t('vault.search')}
              placeholderTextColor={colors.textMuted}
              accessibilityLabel={t('vault.search')}
              style={[styles.input, { color: colors.text, textAlign: dir.textAlign, fontSize: scaled(typeScale.size.body) }]}
            />
          </View>
          {rows.length === 0 && !loading ? <AppText color="textMuted">{t('vault.no_results')}</AppText> : null}
          {grouped
            ? members
                .filter((m) => withPapers.has(m.id))
                .map((m) => (
                  <View key={m.id} style={styles.group}>
                    <Heading level={2}>{memberName(m, t)}</Heading>
                    <DocumentList rows={rows.filter((r) => r.memberId === m.id)} members={members} showMember={false} />
                  </View>
                ))
            : <DocumentList rows={rows} members={members} showMember={false} />}
        </>
      )}
      <StorageNotice />
      <Sheet visible={adding} title={t('vault.add_member')} onClose={() => setAdding(false)} testID="papers-add-member-sheet">
        <MemberForm
          initialColor={nextColor(members)}
          submitLabel={t('btn.save')}
          onSubmit={(value) => {
            void vault.members.add(value).then(() => {
              bumpVault();
              setAdding(false);
            });
          }}
          onCancel={() => setAdding(false)}
        />
      </Sheet>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    gap: space.xxs,
  },
  chips: {
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.sm,
  },
  search: {
    alignItems: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    minHeight: size.button,
  },
  input: {
    flex: 1,
    minHeight: size.button,
  },
  group: {
    gap: space.md,
  },
  notice: {
    alignItems: 'flex-start',
    gap: space.sm,
    padding: space.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
});
