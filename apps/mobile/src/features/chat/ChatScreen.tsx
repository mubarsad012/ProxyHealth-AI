// S9 — Ask about this paper (`/result/[id]/chat`). Grounded answers with quote chips (→ S8),
// fixed refusal/referral templates, suggested-question chips, a speaker and "Was this clear?" on
// every assistant bubble. `ChatAnswer.safety.emergency` opens the S19 card over the chat.

import { type Href, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import type { AnalysisResult, ChatAnswer } from '@/api/types';
import { Bidi, stripIsolates } from '@/design/components/Bidi';
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
import { useTtsFallbackNotice } from '@/features/speech';
import { useDirection } from '@/i18n/direction';
import { useBidiText, usePackMeta, useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';

import { referKey, referShowsHelp, refusalKey, starterQuestions } from './refusalTemplates';
import { type ChatTurn, useChat } from './useChat';

/** Compare sentences without case, spacing, bidi isolates or joiners. */
function sentenceKey(text: string): string {
  return stripIsolates(text)
    .replace(/[\s\u200c\u200d\u200e\u200f]+/g, '')
    .toLowerCase();
}

/**
 * The text an assistant bubble shows: answer first, then the fixed templates (S9 rule). The server
 * owns "The paper does not say." (`chat_pipeline.with_not_in_document` puts the pack sentence in
 * `answer` exactly once), so the client never appends `chat.not_in_document` to an answer; only an
 * empty non-refusal answer falls back to it. A template the answer already contains (the server's
 * fixed `out_of_scope` reply) is not repeated.
 */
export function assistantLines(answer: ChatAnswer, t: (k: string) => string): string[] {
  const lines: string[] = [];
  const body = answer.answer.trim() ? answer.answer : '';
  const refusal = refusalKey(answer.refusal_kind);
  if (body) lines.push(body);
  const add = (text: string) => {
    const key = sentenceKey(text);
    if (key && !lines.some((l) => sentenceKey(l).includes(key))) lines.push(text);
  };
  if (refusal) add(t(refusal));
  if (answer.not_in_document && !body && !refusal) add(t('chat.not_in_document'));
  const refer = referKey(answer.refer_to_professional);
  if (refer) add(t(refer));
  return lines;
}

function Bubble({ turn, analysis, onQuote }: { turn: ChatTurn; analysis: AnalysisResult; onQuote(span: string, page: number): void }) {
  const t = useT();
  const bt = useBidiText();
  const meta = usePackMeta();
  const { colors } = useTheme();
  const dir = useDirection();
  const mine = turn.role === 'user';
  const a = turn.answer;
  const lines = a ? assistantLines(a, t) : [turn.text];
  const text = stripIsolates(lines.join(' '));
  // Honest TTS line (D-26) under this bubble's speaker when the pack's own voice is missing.
  const voice = useTtsFallbackNotice(meta.tag);
  return (
    <View
      testID={`chat-${turn.id}`}
      style={[
        styles.bubble,
        { alignSelf: mine ? dir.alignEnd : dir.alignStart, backgroundColor: mine ? colors.secondary : colors.surface, borderColor: colors.divider },
      ]}>
      {lines.map((l, i) => (
        <AppText key={i} lang={analysis.target_language}>
          {bt(l)}
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
          <SpeakButton text={text} lang={meta.tag} onResolved={voice.onResolved} />
          <View style={styles.flex}>
            <FeedbackRow surface="chat" documentType={analysis.document_type} documentCategory={analysis.category} modelId={a?.model_meta.model_id ?? null} />
          </View>
        </View>
      )}
      {!mine && voice.notice ? (
        <AppText variant="caption" color="textMuted" role="status" testID="tts-fallback-notice">
          {voice.notice}
        </AppText>
      ) : null}
    </View>
  );
}

export interface ChatScreenProps {
  analysis: AnalysisResult;
  /** A prompt tapped on S7 (`?q=`): asked once when the screen opens online. */
  initialQuestion?: string | null;
}

export function ChatScreen({ analysis, initialQuestion }: ChatScreenProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const { online } = useOnline();
  const chat = useChat(analysis);
  const [draft, setDraft] = useState('');
  const askedInitial = useRef(false);
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

  useEffect(() => {
    const q = initialQuestion?.trim();
    if (!q || askedInitial.current || !online) return;
    askedInitial.current = true;
    ask(q);
    // `ask` is recreated every render; the ref makes this run once per screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion, online]);

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
