// S9 — Ask about this paper (`/result/[id]/chat`). Grounded answers with quote chips (→ S8),
// fixed refusal/referral templates, suggested-question chips, a speaker and "Was this clear?" on
// every assistant bubble. `ChatAnswer.safety.emergency` opens the S19 card over the chat.

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import type { AnalysisResult, ChatAnswer } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { FeedbackRow } from '@/design/components/FeedbackRow';
import { Interpolated } from '@/design/components/Interpolated';
import { Screen } from '@/design/components/Screen';
import { SpeakButton } from '@/design/components/SpeakButton';
import { ErrorState } from '@/design/components/States';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { emergencyTrigger } from '@/features/emergency';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';

import { referKey, referShowsHelp, refusalKey, starterQuestions } from './refusalTemplates';
import { type ChatTurn, useChat } from './useChat';

/** The text an assistant bubble shows: answer first, then the fixed template (S9 rule). */
export function assistantLines(answer: ChatAnswer, t: (k: string) => string): string[] {
  const lines: string[] = [];
  const refusal = refusalKey(answer.refusal_kind);
  if (answer.answer.trim()) lines.push(answer.answer);
  if (refusal) lines.push(t(refusal));
  if (answer.not_in_document) lines.push(t('chat.not_in_document'));
  const refer = referKey(answer.refer_to_professional);
  if (refer) lines.push(t(refer));
  return lines;
}

function Bubble({ turn, analysis, onQuote }: { turn: ChatTurn; analysis: AnalysisResult; onQuote(span: string, page: number): void }) {
  const t = useT();
  const meta = usePackMeta();
  const { colors } = useTheme();
  const dir = useDirection();
  const mine = turn.role === 'user';
  const a = turn.answer;
  const lines = a ? assistantLines(a, t) : [turn.text];
  const text = lines.join(' ');
  return (
    <View
      testID={`chat-${turn.id}`}
      style={[
        styles.bubble,
        { alignSelf: mine ? dir.alignEnd : dir.alignStart, backgroundColor: mine ? colors.secondary : colors.surface, borderColor: colors.divider },
      ]}>
      {lines.map((l, i) => (
        <AppText key={i} lang={analysis.target_language}>
          {l}
        </AppText>
      ))}
      {a?.grounded_quotes.map((q) => (
        <Pressable
          key={`${q.span_id}-${q.page}`}
          role="button"
          accessibilityLabel={t('chat.from_your_paper', { page: q.page, text: q.text })}
          onPress={() => onQuote(q.span_id, q.page)}
          style={[styles.quote, { borderColor: colors.border }]}>
          <Interpolated
            variant="caption"
            template={t('chat.from_your_paper')}
            vars={{ page: q.page, text: q.text }}
            ltrKeys={['page', 'text']}
          />
        </Pressable>
      ))}
      {a && referShowsHelp(a.refer_to_professional) ? (
        <BigButton label={t('btn.get_help')} icon="help" variant="secondary" size={56} onPress={() => router.push('/help' as Href)} />
      ) : null}
      {mine ? null : (
        <View style={[styles.tools, { flexDirection: dir.row }]}>
          <SpeakButton text={text} lang={meta.tag} />
          <View style={styles.flex}>
            <FeedbackRow surface="chat" documentType={analysis.document_type} documentCategory={analysis.category} modelId={a?.model_meta.model_id ?? null} />
          </View>
        </View>
      )}
    </View>
  );
}

export function ChatScreen({ analysis }: { analysis: AnalysisResult }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const { online } = useOnline();
  const chat = useChat(analysis);
  const [draft, setDraft] = useState('');
  const last = [...chat.turns].reverse().find((x) => x.answer)?.answer ?? null;
  const chips = last?.suggested_questions.length ? last.suggested_questions : starterQuestions(analysis, t);

  const openQuote = (span: string, page: number) =>
    router.push(`/result/${encodeURIComponent(analysis.analysis_id)}/source?block=${encodeURIComponent(span)}&page=${page}` as Href);

  const ask = (q: string) => {
    setDraft('');
    void chat.send(q).then((answer) => {
      const trig = emergencyTrigger(answer?.safety);
      if (trig.triggered) router.push(`/emergency?kinds=${trig.kinds.join(',')}` as Href);
    });
  };

  const footer = (
    <View style={styles.inputWrap}>
      <AppText weight="bold">{t('chat.input_label')}</AppText>
      <View style={[styles.inputRow, { flexDirection: dir.row }]}>
        <TextInput
          testID="chat-input"
          accessibilityLabel={t('chat.input_label')}
          value={draft}
          editable={online && !chat.sending}
          maxLength={chat.maxQuestion}
          multiline
          onChangeText={setDraft}
          style={[styles.input, { borderColor: colors.border, color: colors.text, textAlign: dir.textAlign, writingDirection: dir.writingDirection }]}
        />
        <BigButton label={t('btn.send')} icon="chevron-right" variant="primary" size={56} disabled={!online || chat.sending || !draft.trim()} onPress={() => ask(draft)} />
      </View>
      <AppText variant="caption" color="textMuted">
        <Bidi dir="ltr">{`${draft.length}/${chat.maxQuestion}`}</Bidi>
      </AppText>
    </View>
  );

  return (
    <Screen back footer={footer} testID="chat-screen">
      <AppText color="textMuted">{t('chat.scope')}</AppText>
      {online ? null : <AppText role="status">{t('state.offline_disabled')}</AppText>}
      {chat.historyCapped ? <AppText color="textMuted">{t('chat.history_cap')}</AppText> : null}
      {chat.turns.map((turn) => (
        <Bubble key={turn.id} turn={turn} analysis={analysis} onQuote={openQuote} />
      ))}
      {chat.sending ? <AppText role="status" color="textMuted">{t('reading.step2')}</AppText> : null}
      {chat.error ? <ErrorState error={chat.error} onRetry={chat.dismissError} /> : null}
      <View style={[styles.chips, { flexDirection: dir.row }]}>
        {chips.map((q) => (
          <Pressable
            key={q}
            role="button"
            accessibilityLabel={q}
            disabled={!online || chat.sending}
            onPress={() => ask(q)}
            style={[styles.chip, { borderColor: colors.primary, opacity: !online || chat.sending ? 0.5 : 1 }]}>
            <AppText variant="caption" color="primary" weight="bold">
              {q}
            </AppText>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  bubble: { maxWidth: '92%', borderWidth: 1, borderRadius: radius.lg, padding: space.md, gap: space.sm },
  quote: { borderWidth: 1, borderRadius: radius.md, padding: space.sm },
  tools: { alignItems: 'center', gap: space.sm },
  flex: { flex: 1 },
  chips: { flexWrap: 'wrap', gap: space.sm },
  chip: { minHeight: size.minTouch, justifyContent: 'center', borderWidth: 2, borderRadius: radius.pill, paddingHorizontal: space.md },
  inputWrap: { gap: space.xs },
  inputRow: { alignItems: 'flex-end', gap: space.sm },
  input: { flex: 1, minHeight: size.button, maxHeight: 160, borderWidth: 2, borderRadius: radius.md, padding: space.md, fontSize: 18 },
});
