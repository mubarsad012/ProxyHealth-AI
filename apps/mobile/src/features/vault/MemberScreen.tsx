// S13 — Member detail (PRODUCT_SPEC S13): initials + colour header, "Change name", "Change color"
// (the Add-someone swatches; `vault.members.recolor`, CL-036), this person's papers, "Move all
// papers", and "Delete {name} and all their papers" behind a confirm (per-member wipe). "Me" can be
// renamed and recoloured but never deleted. "Me" is created on the first save (§9.2), so "Change
// name" and "Change color" appear once that row exists.

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { Heading } from '@/design/components/Text';
import { useScaled, useTheme } from '@/design/theme';
import { radius, size, space, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import { useVault } from '@/storage/StorageProvider';

import { deleteMember, moveDocuments } from './actions';
import { DocumentList } from './DocumentList';
import { useDocuments, useMembers } from './hooks';
import { Avatar, ColorSwatches, MemberPickerSheet } from './MemberParts';
import { cleanMemberName, emptyVaultText, isMe, MEMBER_NAME_MAX, memberName } from './members';
import { ConfirmDialog } from './Sheet';
import { bumpVault } from './store';

export function MemberScreen({ memberId }: { memberId: string }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const vault = useVault();
  const { members } = useMembers();
  const { rows, loading } = useDocuments({ memberId });
  const member = members.find((m) => m.id === memberId) ?? null;
  const name = memberName(member, t);
  // `withMe` shows a placeholder "Me" (createdAt '') until the first save creates the row.
  const canRename = member !== null && member.createdAt !== '';
  const scaled = useScaled();
  const [draft, setDraft] = useState<string | null>(null);
  const [recoloring, setRecoloring] = useState(false);
  const [moving, setMoving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const rename = async () => {
    const clean = cleanMemberName(draft ?? '');
    if (!clean) return;
    await vault.members.rename(memberId, clean);
    bumpVault();
    setDraft(null);
  };

  const recolor = async (color: string) => {
    setRecoloring(false);
    if (member && color.toLowerCase() === member.color.toLowerCase()) return;
    await vault.members.recolor(memberId, color);
    bumpVault();
  };

  return (
    <Screen title={name} back testID="member-screen">
      <View style={[styles.header, { flexDirection: dir.row }]}>
        <Avatar name={name} color={member?.color ?? colors.primary} big />
        <View style={styles.flex}>
          <Heading level={2}>{name}</Heading>
        </View>
      </View>
      {!canRename ? null : draft === null ? (
        <BigButton
          testID="member-rename"
          label={t('member.rename')}
          variant="secondary"
          size={56}
          onPress={() => setDraft(member?.name ?? '')}
        />
      ) : (
        <View style={styles.form}>
          <TextInput
            testID="member-rename-input"
            value={draft}
            onChangeText={(v) => setDraft(v.slice(0, MEMBER_NAME_MAX))}
            maxLength={MEMBER_NAME_MAX}
            placeholder={t('member.name')}
            placeholderTextColor={colors.textMuted}
            accessibilityLabel={t('member.rename')}
            style={[
              styles.input,
              {
                color: colors.text,
                borderColor: colors.border,
                textAlign: dir.textAlign,
                fontSize: scaled(typeScale.size.body),
              },
            ]}
          />
          <BigButton
            label={t('btn.save')}
            icon="check"
            variant="primary"
            size={56}
            disabled={cleanMemberName(draft).length === 0}
            onPress={() => void rename()}
          />
          <BigButton label={t('btn.cancel')} variant="secondary" size={56} onPress={() => setDraft(null)} />
        </View>
      )}
      {!canRename || !member ? null : !recoloring ? (
        <BigButton
          testID="member-recolor"
          label={t('member.color')}
          variant="secondary"
          size={56}
          onPress={() => setRecoloring(true)}
        />
      ) : (
        <View style={styles.form} testID="member-recolor-panel">
          <ColorSwatches testID="member-recolor-swatch" value={member.color} onChange={(c) => void recolor(c)} />
          <BigButton label={t('btn.cancel')} variant="secondary" size={56} onPress={() => setRecoloring(false)} />
        </View>
      )}
      {!loading && rows.length === 0 ? (
        <EmptyState icon="papers" text={emptyVaultText(t)} />
      ) : (
        <DocumentList rows={rows} members={members} showMember={false} />
      )}
      {rows.length > 0 && members.length > 1 ? (
        <BigButton
          testID="member-move-all"
          label={t('btn.move_all')}
          icon="people"
          variant="secondary"
          size={56}
          onPress={() => setMoving(true)}
        />
      ) : null}
      {isMe(memberId) || !member ? null : (
        <BigButton
          testID="member-delete"
          label={t('member.delete', { name })}
          icon="close"
          variant="danger"
          size={56}
          onPress={() => setConfirmDelete(true)}
        />
      )}
      <MemberPickerSheet
        visible={moving}
        title={t('btn.move_all')}
        members={members}
        excludeId={memberId}
        onClose={() => setMoving(false)}
        onPick={(target) => {
          setMoving(false);
          void moveDocuments(
            vault,
            rows.map((r) => r.id),
            target,
          );
        }}
      />
      <ConfirmDialog
        testID="member-delete-confirm"
        visible={confirmDelete}
        title={t('member.delete', { name })}
        body={t('member.delete_confirm', { name })}
        confirmLabel={t('member.delete', { name })}
        cancelLabel={t('btn.cancel')}
        danger
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          void deleteMember(vault, memberId).then(() => {
            if (router.canGoBack()) router.back();
            else router.replace('/papers' as Href);
          });
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: {
    alignItems: 'center',
    gap: space.md,
  },
  flex: {
    flex: 1,
  },
  form: {
    gap: space.sm,
  },
  input: {
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
});
