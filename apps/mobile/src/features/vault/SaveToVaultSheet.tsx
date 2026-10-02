// S7 "Save" → "Whose paper is this?" (PRODUCT_SPEC §9.3 "Save", D-22/D-24). Saving is opt-in:
// NOTHING is written — not the paper, not a new member — until the user taps Save in this sheet.
// "Add someone" collects a name + colour locally and creates the member only at Save. Page images
// follow Settings → "Keep page images" (default on native, off web); "Hide ID numbers" masks
// A-numbers / receipt numbers in the stored copy. A page with "Hide parts" boxes keeps its image
// only on web, where `preparePages` burned the boxes into the display page (D-19; native sends
// `masks[]` and keeps the original photo in the session, so that page is saved without an image).
// Three uses, one sheet (the member choice defaults to "Me"):
//   • a result (`analysis`);
//   • "Save to read later" (`readLaterId`, no `analysis` — the row is stored with `analysis: null`);
//   • a caller-built copy (`buildDocument`, e.g. S16 "Save as proof"), built for the chosen member.

import { useState } from 'react';
import { AccessibilityInfo, Platform, StyleSheet, View } from 'react-native';

import type { AnalysisResult } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { AppText } from '@/design/components/Text';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { StoredDocument, StoredPageInput } from '@/storage/index';
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
  /** The result being saved. Omitted (or null) for "Save to read later" and `buildDocument` saves. */
  analysis?: AnalysisResult | null;
  /** Session pages (page images follow Settings → "Keep page images"). */
  pages?: CapturedPage[];
  /** `savedFor` is the chosen member's display name (for "Saved for {member}"). */
  onSaved(documentId: string, savedFor: string): void;
  onCancel(): void;
  /** "Save to read later": no analysis yet; the caller supplies the id. */
  readLaterId?: string;
  /** Preselected member (e.g. chosen on S5). */
  initialMemberId?: string | null;
  /** Caller-built stored copy for the chosen member (S16 "Save as proof"). */
  buildDocument?(memberId: string, now: Date): { doc: StoredDocument; pages: StoredPageInput[] };
}

/** What the sheet will write for `memberId`, or null when it has nothing to save. */
export function documentToSave(
  props: Pick<SaveToVaultSheetProps, 'analysis' | 'pages' | 'readLaterId' | 'buildDocument'>,
  opts: { memberId: string; keepPages: boolean; hideIds: boolean; now: Date; t: (key: string, vars?: Record<string, string | number>) => string; web: boolean },
): { doc: StoredDocument; pages: StoredPageInput[] } | null {
  if (props.buildDocument) return props.buildDocument(opts.memberId, opts.now);
  const analysis = props.readLaterId ? null : (props.analysis ?? null);
  if (!analysis && !props.readLaterId) return null;
  return buildStoredDocument({
    analysis,
    pages: props.pages ?? [],
    memberId: opts.memberId,
    keepPages: opts.keepPages,
    hideIds: opts.hideIds,
    now: opts.now,
    t: opts.t,
    documentId: props.readLaterId,
    // Web result pages come from `preparePages` (boxes burned on a canvas); "read later" pages
    // and every native page still hold the original pixels.
    masksBurnedIn: opts.web && !props.readLaterId,
  });
}

const PENDING_ID = '__pending_new_member__';

export function SaveToVaultSheet(props: SaveToVaultSheetProps) {
  const { analysis, onSaved, onCancel, readLaterId, initialMemberId, buildDocument } = props;
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
  const canSave = Boolean(buildDocument || readLaterId || analysis);

  const save = async () => {
    if (busy || !canSave) return;
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
      const built = documentToSave(props, { memberId, keepPages, hideIds, now: new Date(), t, web: Platform.OS === 'web' });
      if (!built) throw new Error('nothing to save');
      await vault.documents.save(built.doc, built.pages);
      bumpVault();
      try {
        AccessibilityInfo.announceForAccessibility(savedAnnouncement(t, savedFor));
      } catch {
        // best-effort announcement
      }
      onSaved(built.doc.id, savedFor);
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
              disabled={busy || !canSave}
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
