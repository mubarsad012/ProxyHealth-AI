// S7 "Save" → "Whose paper is this?" (PRODUCT_SPEC §9.3 "Save", D-22/D-24). Saving is opt-in:
// NOTHING is written — not the paper, not a new member — until the user taps Save in this sheet.
// "Add someone" collects a name + colour locally and creates the member only at Save. Page images
// follow Settings → "Keep page images" (default on native, off web); "Hide ID numbers" masks
// A-numbers / receipt numbers in the stored copy. A page with "Hide parts" boxes keeps its image
// only on web, where `preparePages` burned the boxes into the display page (D-19; native sends
// `masks[]` and keeps the original photo in the session, so that page is saved without an image).
// Works for "Save to read later" too (analysis null + an explicit `documentId`).

import { useState } from 'react';
import { AccessibilityInfo, Platform, StyleSheet, View } from 'react-native';

import type { AnalysisResult } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { AppText } from '@/design/components/Text';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import { useVault } from '@/storage/StorageProvider';
import type { CapturedPage } from '@/store/session';
import { useSettings } from '@/store/settings';
import { space } from '@/design/tokens';

import { buildStoredDocument, isSampleAnalysis } from './documents';
import { useMembers } from './hooks';
import { MemberChip, MemberForm } from './MemberParts';
import { ME_MEMBER_ID, memberName, nextColor, savedAnnouncement } from './members';
import { Sheet } from './Sheet';
import { bumpVault } from './store';

export interface SaveToVaultSheetProps {
  analysis: AnalysisResult;
  pages: CapturedPage[];
  onSaved(documentId: string): void;
  onCancel(): void;
  /** "Save to read later": no analysis yet; the caller supplies the id. */
  readLaterId?: string;
  /** Preselected member (e.g. chosen on S5). */
  initialMemberId?: string | null;
}

const PENDING_ID = '__pending_new_member__';

export function SaveToVaultSheet(props: SaveToVaultSheetProps) {
  const { analysis, pages, onSaved, onCancel, readLaterId, initialMemberId } = props;
  const t = useT();
  const dir = useDirection();
  const vault = useVault();
  const { members } = useMembers();
  const keepPages = useSettings((s) => s.keepPageImages);
  const hideIds = useSettings((s) => s.hideIdNumbers);
  const [selected, setSelected] = useState<string>(initialMemberId ?? ME_MEMBER_ID);
  const [adding, setAdding] = useState(false);
  const [pending, setPending] = useState<{ name: string; color: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const save = async () => {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      let memberId = selected;
      let savedFor = memberName(members.find((m) => m.id === selected), t);
      if (selected === PENDING_ID && pending) {
        const created = await vault.members.add(pending);
        memberId = created.id;
        savedFor = created.name;
      }
      const { doc, pages: pageInputs } = buildStoredDocument({
        analysis: readLaterId ? null : analysis,
        pages,
        memberId,
        keepPages,
        hideIds,
        now: new Date(),
        t,
        documentId: readLaterId,
        // Web result pages come from `preparePages` (boxes burned on a canvas); "read later" pages
        // and every native page still hold the original pixels.
        masksBurnedIn: Platform.OS === 'web' && !readLaterId,
      });
      await vault.documents.save(doc, pageInputs);
      bumpVault();
      try {
        AccessibilityInfo.announceForAccessibility(savedAnnouncement(t, savedFor));
      } catch {
        // best-effort announcement
      }
      onSaved(doc.id);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const chips = members.map((m) => (
    <MemberChip
      key={m.id}
      testID={`save-member-${m.id}`}
      member={m}
      selected={selected === m.id}
      onPress={() => setSelected(m.id)}
    />
  ));
  if (pending) {
    chips.push(
      <MemberChip
        key={PENDING_ID}
        testID="save-member-new"
        member={{ id: PENDING_ID, name: pending.name, color: pending.color, createdAt: '' }}
        selected={selected === PENDING_ID}
        onPress={() => setSelected(PENDING_ID)}
      />,
    );
  }

  return (
    <Sheet
      visible
      testID="save-to-vault-sheet"
      title={readLaterId ? t('vault.whose_paper_optional') : t('vault.whose_paper')}
      onClose={onCancel}
      footer={
        adding ? null : (
          <View style={styles.actions}>
            <BigButton
              testID="save-to-vault-confirm"
              label={t('btn.save')}
              icon="check"
              variant="primary"
              size={72}
              disabled={busy}
              onPress={() => void save()}
            />
            <BigButton label={t('btn.cancel')} variant="secondary" size={56} disabled={busy} onPress={onCancel} />
          </View>
        )
      }>
      {isSampleAnalysis(analysis) && !readLaterId ? (
        <AppText variant="caption" color="textMuted">
          {t('vault.sample_tag')}
        </AppText>
      ) : null}
      <View role="radiogroup" accessibilityLabel={t('vault.whose_paper')} style={[styles.chips, { flexDirection: dir.row }]}>
        {chips}
      </View>
      {adding ? (
        <MemberForm
          initialColor={nextColor(members)}
          submitLabel={t('vault.add_member')}
          onSubmit={(value) => {
            setPending(value);
            setSelected(PENDING_ID);
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <BigButton
          testID="save-add-member"
          label={t('vault.add_member')}
          icon="people"
          variant="secondary"
          size={56}
          onPress={() => setAdding(true)}
        />
      )}
      <AppText variant="caption" color="textMuted">
        {Platform.OS === 'web' ? t('vault.privacy_web') : t('vault.privacy_native')}
      </AppText>
      {failed ? (
        <View role="alert">
          <AppText color="danger">{t('err.internal')}</AppText>
        </View>
      ) : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  chips: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  actions: {
    gap: space.sm,
  },
});
