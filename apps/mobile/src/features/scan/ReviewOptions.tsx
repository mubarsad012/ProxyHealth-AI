// S5 should-haves (PRODUCT_SPEC S5 "Components"): the output-language chip (defaults to the UI
// language; opens the language grid in a sheet), the optional "I think this is a…" document-hint
// chip row (≤ 8 common `DocumentType` values + "Not sure"; a tie-breaker only on the server), and
// the optional, collapsed "Whose paper is this?" member selector (vault members, default Me). A
// sample hides the hint and the member selector (S5 sample state). Choices live in `choices.ts`.

import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useServerConfig } from '@/api/config';
import type { DocumentType } from '@/api/types';
import { Collapsible } from '@/design/components/Collapsible';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { gridLanguages } from '@/features/onboarding/languageGrid';
import { ME_MEMBER_ID, MemberChip, Sheet, useMembers } from '@/features/vault';
import { useDirection } from '@/i18n/direction';
import { languageInfoFor } from '@/i18n/store';
import { usePackMeta, useT } from '@/i18n/useT';

import { DOCUMENT_HINTS, documentHintKey, useScanChoices } from './choices';

export const OUTPUT_LANGUAGE_KEY = 'review.output_language';
export const OUTPUT_LANGUAGE_TITLE_KEY = 'review.output_language_title';

/** The language a result will be written in: the S5 choice, else the UI language. */
export function effectiveOutputLanguage(choice: string | null, uiTag: string): string {
  return choice ?? uiTag;
}

function Chip({ label, selected, onPress, testID, lang }: { label: string; selected: boolean; onPress(): void; testID?: string; lang?: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      role="radio"
      aria-checked={selected}
      accessibilityState={{ checked: selected, selected }}
      accessibilityLabel={label}
      hitSlop={size.hitSlop / 2}
      onPress={onPress}
      style={[
        styles.chip,
        { borderColor: selected ? colors.primary : colors.border, borderWidth: selected ? 3 : 1, backgroundColor: selected ? colors.secondary : colors.surface },
      ]}>
      <AppText variant="caption" weight={selected ? 'bold' : 'regular'} lang={lang}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function OutputLanguageChip() {
  const t = useT();
  const meta = usePackMeta();
  const dir = useDirection();
  const { colors } = useTheme();
  const { config } = useServerConfig();
  const choice = useScanChoices((s) => s.outputLanguage);
  const setChoice = useScanChoices((s) => s.setOutputLanguage);
  const [open, setOpen] = useState(false);
  const tag = effectiveOutputLanguage(choice, meta.tag);
  const name = languageInfoFor(tag).name_native;
  const languages = open ? gridLanguages(config?.languages) : [];
  return (
    <View>
      <Pressable
        testID="review-output-language"
        role="button"
        accessibilityLabel={t(OUTPUT_LANGUAGE_KEY, { language: name })}
        hitSlop={size.hitSlop}
        onPress={() => setOpen(true)}
        style={[styles.outputChip, { flexDirection: dir.row, borderColor: colors.primary }]}>
        <Icon name="globe" size={20} color={colors.primary} />
        <AppText weight="bold" color="primary">
          {t(OUTPUT_LANGUAGE_KEY, { language: name })}
        </AppText>
      </Pressable>
      <Sheet visible={open} title={t(OUTPUT_LANGUAGE_TITLE_KEY)} onClose={() => setOpen(false)} testID="output-language-sheet">
        <View role="radiogroup" style={styles.list}>
          {languages.map((l) => {
            const selected = l.tag === tag;
            return (
              <Pressable
                key={l.tag}
                testID={`output-language-${l.tag}`}
                role="radio"
                aria-checked={selected}
                accessibilityState={{ checked: selected, selected }}
                accessibilityLabel={l.name_native === l.name_en ? l.name_native : `${l.name_native}, ${l.name_en}`}
                onPress={() => {
                  setChoice(l.tag === meta.tag ? null : l.tag);
                  setOpen(false);
                }}
                style={[styles.langRow, { flexDirection: dir.row, borderColor: selected ? colors.primary : colors.divider }]}>
                <View style={styles.flex}>
                  <AppText weight="bold" lang={l.tag}>
                    {l.name_native}
                  </AppText>
                  {l.name_en !== l.name_native ? (
                    <AppText variant="caption" color="textMuted" lang="en">
                      {l.name_en}
                    </AppText>
                  ) : null}
                </View>
                {selected ? <Icon name="check" color={colors.primary} /> : null}
              </Pressable>
            );
          })}
        </View>
      </Sheet>
    </View>
  );
}

export function DocumentHintChips() {
  const t = useT();
  const dir = useDirection();
  const hint = useScanChoices((s) => s.documentHint);
  const setHint = useScanChoices((s) => s.setDocumentHint);
  const options: (DocumentType | null)[] = [...DOCUMENT_HINTS, null];
  return (
    <View style={styles.block} testID="review-document-hint">
      <AppText weight="bold">{t('review.document_hint')}</AppText>
      <View role="radiogroup" accessibilityLabel={t('review.document_hint')} style={[styles.chips, { flexDirection: dir.row }]}>
        {options.map((o) => (
          <Chip
            key={o ?? 'not_sure'}
            testID={`review-hint-${o ?? 'not_sure'}`}
            label={t(documentHintKey(o))}
            selected={hint === o}
            onPress={() => setHint(hint === o ? null : o)}
          />
        ))}
      </View>
    </View>
  );
}

function MemberChoices() {
  const dir = useDirection();
  const { members } = useMembers();
  const memberId = useScanChoices((s) => s.memberId);
  const setMember = useScanChoices((s) => s.setMemberId);
  const selected = memberId ?? ME_MEMBER_ID;
  return (
    <View role="radiogroup" style={[styles.chips, { flexDirection: dir.row }]}>
      {members.map((m) => (
        <MemberChip
          key={m.id}
          member={m}
          selected={m.id === selected}
          testID={`review-member-${m.id}`}
          onPress={() => setMember(m.id === ME_MEMBER_ID ? null : m.id)}
        />
      ))}
    </View>
  );
}

export function WhosePaper() {
  const t = useT();
  const memberId = useScanChoices((s) => s.memberId);
  return (
    <View testID="review-whose-paper">
      <Collapsible title={t('vault.whose_paper_optional')} initiallyOpen={Boolean(memberId)}>
        <MemberChoices />
      </Collapsible>
    </View>
  );
}

/** The three S5 options in spec order; `sample` keeps only the output-language chip. */
export function ReviewOptions({ sample }: { sample: boolean }) {
  return (
    <View style={styles.block}>
      <OutputLanguageChip />
      {sample ? null : <DocumentHintChips />}
      {sample ? null : <WhosePaper />}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: space.sm },
  chips: { flexWrap: 'wrap', gap: space.sm },
  chip: { minHeight: size.minTouch, justifyContent: 'center', borderRadius: radius.pill, paddingHorizontal: space.md },
  outputChip: {
    alignSelf: 'flex-start',
    minHeight: size.minTouch,
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 2,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
  list: { gap: space.xs },
  langRow: { minHeight: size.minTouch, alignItems: 'center', gap: space.sm, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: space.xs },
  flex: { flex: 1 },
});
