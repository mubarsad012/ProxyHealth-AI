// Card 1 — "What is this?" (PRODUCT_SPEC S7 item 7): title, ≤ 3-sentence body, the English body
// under it for Tier 3 / low-confidence packs, crop chips for `summary.span_ids`, and the sender
// line exactly as printed (LTR/auto isolated).

import { Pressable, StyleSheet, View } from 'react-native';

import { Bidi } from '@/design/components/Bidi';
import { Card } from '@/design/components/Card';
import { Interpolated } from '@/design/components/Interpolated';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useBidiText, usePackMeta, useT } from '@/i18n/useT';

import { blockById } from '../pageImages';
import type { ResultCardProps } from './shared';

/** Show `body_en` under the body for Tier 3 packs or low translation confidence. */
export function showEnglishBody(tier: number, translationConfidence: string, bodyEn: string, body: string): boolean {
  if (!bodyEn || bodyEn === body) return false;
  return tier >= 3 || translationConfidence === 'low';
}

export function SummaryCard({ analysis, handlers }: ResultCardProps) {
  const t = useT();
  const bt = useBidiText();
  const meta = usePackMeta();
  const { colors } = useTheme();
  const dir = useDirection();
  const s = analysis.summary;
  const english = showEnglishBody(meta.tier, analysis.translation_confidence, s.body_en, s.body);
  const sender = analysis.sender_as_written ? t('card.sender_as_written', { sender: analysis.sender_as_written }) : null;
  const speak = [s.title, s.body, sender].filter(Boolean).join('. ');
  return (
    <Card id="card-what-is-this" headingKey="card.what_is_this" lang={analysis.target_language} speakText={speak}>
      <Heading level={3}>{bt(s.title)}</Heading>
      <AppText lang={analysis.target_language}>{bt(s.body)}</AppText>
      {english ? (
        <View style={[styles.enRow, { flexDirection: dir.row }]}>
          <View style={[styles.enChip, { borderColor: colors.border }]}>
            <AppText variant="caption" weight="bold" color="textMuted">
              EN
            </AppText>
          </View>
          <View style={styles.flex}>
            <AppText variant="caption" color="textMuted" lang="en">
              {bt(s.body_en)}
            </AppText>
          </View>
        </View>
      ) : null}
      {analysis.sender_as_written ? (
        <Interpolated
          template={t('card.sender_as_written')}
          vars={{ sender: analysis.sender_as_written }}
          ltrKeys={['sender']}
        />
      ) : null}
      {s.span_ids.length ? (
        <View style={[styles.chips, { flexDirection: dir.row }]}>
          {s.span_ids.map((id) => {
            const b = blockById(analysis, id);
            if (!b) return null;
            const words = b.text.split(/\s+/).slice(0, 6).join(' ');
            return (
              <Pressable
                key={id}
                role="button"
                accessibilityLabel={b.text}
                hitSlop={size.hitSlop}
                disabled={!handlers.onOpenSource}
                onPress={() => handlers.onOpenSource?.({ block: id, page: b.page })}
                style={[styles.chip, { borderColor: colors.border }]}>
                <Bidi dir="auto" variant="caption">
                  {`“${words}${b.text.split(/\s+/).length > 6 ? '…' : ''}”`}
                </Bidi>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  enRow: {
    gap: space.sm,
    alignItems: 'flex-start',
  },
  enChip: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: space.xs,
  },
  flex: {
    flex: 1,
  },
  chips: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
});
