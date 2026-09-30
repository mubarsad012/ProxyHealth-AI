// Saved-paper rows for S12/S13 (PRODUCT_SPEC S12): title, category word, saved date, next-date
// badge, "Not read yet" / "Sample" chips, member dot; tap → S7 from storage; long-press (or the
// options button / screen-reader actions) → Move to another person · Delete this paper (confirm).

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { Interpolated } from '@/design/components/Interpolated';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { formatDay } from '@/features/reminders/format';
import { toIsoDay } from '@/features/reminders/schedule';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { DocumentRow, Member } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import { deleteDocument, moveDocuments, openStoredDocument, readLaterPages } from './actions';
import { categoryWord, isSampleAnalysis } from './documents';
import { useDocument } from './hooks';
import { MemberPickerSheet } from './MemberParts';
import { memberName } from './members';
import { ConfirmDialog, Sheet } from './Sheet';

/** `createdAt` is stored as a UTC instant; the row shows the device's LOCAL day it was saved. */
function savedDay(createdAt: string): string {
  const d = new Date(createdAt);
  return Number.isNaN(d.getTime()) ? createdAt.slice(0, 10) : toIsoDay(d);
}

function Tag({ text }: { text: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.tag, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <AppText variant="caption" weight="bold">
        {text}
      </AppText>
    </View>
  );
}

interface RowProps {
  row: DocumentRow;
  member?: Member;
  showMember: boolean;
  onOptions(row: DocumentRow): void;
}

function DocumentRowView({ row, member, showMember, onOptions }: RowProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const vault = useVault();
  const tag = useSettings((s) => s.languageTag);
  const { doc } = useDocument(row.id);
  const notRead = doc !== null && !doc.analysis;
  const sample = isSampleAnalysis(doc?.analysis);
  const readNow = async () => {
    const pages = await readLaterPages(vault, row.id);
    if (pages.length === 0) return;
    const session = useSession.getState();
    session.setDemoSampleId(null);
    session.setCurrentAnalysis(null);
    session.setPages(pages);
    router.push('/scan/review' as Href);
  };
  // A "Not read yet" row with kept pages opens S5 with those pages; everything else opens S7.
  const openRow = () => (notRead && doc?.keepPages ? void readNow() : openStoredDocument(row.id));
  return (
    <View style={[styles.row, { borderColor: colors.divider, backgroundColor: colors.surface }]}>
      <View style={[styles.rowTop, { flexDirection: dir.row }]}>
        <Pressable
          testID={`paper-row-${row.id}`}
          role="button"
          accessibilityLabel={row.title}
          accessibilityActions={[
            { name: 'activate', label: row.title },
            { name: 'longpress', label: `${t('btn.move_member')}, ${t('btn.delete_paper')}` },
          ]}
          onAccessibilityAction={(e) => (e.nativeEvent.actionName === 'longpress' ? onOptions(row) : openRow())}
          onPress={openRow}
          onLongPress={() => onOptions(row)}
          style={[styles.rowMain, { flexDirection: dir.row }]}>
          <Icon name="papers" color={colors.primary} size={size.iconLarge} />
          <View style={styles.flex}>
            <AppText weight="bold">{row.title}</AppText>
            <AppText variant="caption" color="textMuted">
              {categoryWord(row.category, t)} · {formatDay(savedDay(row.createdAt), tag)}
            </AppText>
            {row.nextDateIso ? (
              <View style={[styles.inline, { flexDirection: dir.row }]}>
                <Icon name="calendar" color={colors.text} size={20} />
                <Interpolated
                  variant="caption"
                  weight="bold"
                  template={t('vault.next_date')}
                  vars={{ date: formatDay(row.nextDateIso, tag) }}
                  ltrKeys={[]}
                />
              </View>
            ) : null}
            <View style={[styles.inline, { flexDirection: dir.row }]}>
              {showMember && member ? (
                <View style={[styles.inline, { flexDirection: dir.row }]}>
                  <View style={[styles.dot, { backgroundColor: member.color }]} />
                  <AppText variant="caption">{memberName(member, t)}</AppText>
                </View>
              ) : null}
              {notRead ? <Tag text={t('vault.not_read_yet')} /> : null}
              {sample ? <Tag text={t('vault.sample_tag')} /> : null}
            </View>
          </View>
        </Pressable>
        <Pressable
          testID={`paper-options-${row.id}`}
          role="button"
          accessibilityLabel={`${t('btn.move_member')}, ${t('btn.delete_paper')}`}
          hitSlop={size.hitSlop}
          onPress={() => onOptions(row)}
          style={styles.options}>
          <Icon name="chevron-down" color={colors.textMuted} />
        </Pressable>
      </View>
      {notRead && doc?.keepPages ? (
        <BigButton label={t('btn.read_now')} icon="camera" variant="secondary" size={56} onPress={() => void readNow()} />
      ) : null}
    </View>
  );
}

export interface DocumentListProps {
  rows: DocumentRow[];
  members: Member[];
  showMember: boolean;
}

export function DocumentList({ rows, members, showMember }: DocumentListProps) {
  const t = useT();
  const vault = useVault();
  const [target, setTarget] = useState<DocumentRow | null>(null);
  const [mode, setMode] = useState<'menu' | 'move' | 'delete' | null>(null);
  const close = () => {
    setMode(null);
    setTarget(null);
  };
  const byId = new Map(members.map((m) => [m.id, m]));
  return (
    <View style={styles.list}>
      {rows.map((row) => (
        <DocumentRowView
          key={row.id}
          row={row}
          member={byId.get(row.memberId)}
          showMember={showMember}
          onOptions={(r) => {
            setTarget(r);
            setMode('menu');
          }}
        />
      ))}
      <Sheet visible={mode === 'menu' && target !== null} title={target?.title ?? ''} onClose={close} testID="paper-menu">
        <BigButton label={t('btn.move_member')} icon="people" variant="secondary" size={56} onPress={() => setMode('move')} />
        <BigButton
          testID="paper-menu-delete"
          label={t('btn.delete_paper')}
          icon="close"
          variant="danger"
          size={56}
          onPress={() => setMode('delete')}
        />
      </Sheet>
      <MemberPickerSheet
        visible={mode === 'move' && target !== null}
        title={t('btn.move_member')}
        members={members}
        excludeId={target?.memberId}
        onClose={close}
        onPick={(memberId) => {
          if (target) void moveDocuments(vault, [target.id], memberId);
          close();
        }}
      />
      <ConfirmDialog
        testID="paper-delete-confirm"
        visible={mode === 'delete' && target !== null}
        title={t('vault.delete_confirm')}
        confirmLabel={t('btn.delete_paper')}
        cancelLabel={t('btn.cancel')}
        danger
        onCancel={close}
        onConfirm={() => {
          if (target) void deleteDocument(vault, target.id);
          close();
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: space.md,
  },
  row: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.sm,
  },
  rowTop: {
    alignItems: 'flex-start',
    gap: space.sm,
  },
  rowMain: {
    flex: 1,
    alignItems: 'flex-start',
    gap: space.md,
    minHeight: size.button,
  },
  flex: {
    flex: 1,
    gap: space.xxs,
  },
  inline: {
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  tag: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
  },
  options: {
    width: size.minTouch,
    height: size.minTouch,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
