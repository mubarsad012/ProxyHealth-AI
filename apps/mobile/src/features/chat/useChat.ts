// `useChat` (ARCHITECTURE §3 features/chat; PRODUCT_SPEC S9). History lives only in memory on the
// device (per analysis; saved with the paper by the vault when the user saves). The request carries
// the compacted analysis context and the last ≤ `limits.max_chat_history` turns, and asks for the
// answer in the language the result itself was written in (`analysis.target_language`, which the
// S5 output-language chip may have set apart from the UI language).
// `ChatAnswer.safety` (D-14): an answer that triggers the emergency card calls `onEmergency` BEFORE
// it is added to the history, so S19 opens first and the answer waits underneath it.
// `chatAvailable(config)`: `/v1/config` `features.chat=false` (unpaid / mixed tier, D-01) means
// every chat turn would get 403, so the screen explains that instead of offering the box.

import { useCallback, useState } from 'react';
import { create } from 'zustand';

import { useApi, useServerConfig } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { AnalysisResult, ChatAnswer, ChatMessage, ServerConfig } from '@/api/types';
import { sampleIdForAnalysis } from '@/features/analysis/sampleOrigin';
import { emergencyTrigger } from '@/features/emergency';
import { useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';

import { buildChatRequest, DEFAULT_MAX_HISTORY, DEFAULT_MAX_QUESTION } from './context';

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  answer?: ChatAnswer;
}

interface ChatHistoryState {
  byAnalysis: Record<string, ChatTurn[]>;
  append(analysisId: string, turn: ChatTurn): void;
  clear(analysisId?: string): void;
}

export const useChatHistory = create<ChatHistoryState>()((set) => ({
  byAnalysis: {},
  append: (analysisId, turn) =>
    set((s) => ({ byAnalysis: { ...s.byAnalysis, [analysisId]: [...(s.byAnalysis[analysisId] ?? []), turn] } })),
  clear: (analysisId) =>
    set((s) => {
      if (!analysisId) return { byAnalysis: {} };
      const next = { ...s.byAnalysis };
      delete next[analysisId];
      return { byAnalysis: next };
    }),
}));

const EMPTY: ChatTurn[] = [];

/** The config at send time (the hook's copy may be one render old). */
function serverConfigNow(): Pick<ServerConfig, 'features'> | null {
  return useSession.getState().serverConfig;
}

let turnSeq = 0;

export function turnsToMessages(turns: readonly ChatTurn[]): ChatMessage[] {
  return turns.map((t) => ({ role: t.role, text: t.text }));
}

/**
 * False only when the server says chat is off (`features.chat=false`: unpaid / mixed tier). An
 * unknown config (offline, not loaded yet) keeps the box — the request itself then reports.
 */
export function chatAvailable(config: Pick<ServerConfig, 'features'> | null | undefined): boolean {
  return config?.features?.chat !== false;
}

/** A chat error that means "chat is off on this server" (the D-01 gate answered 403). */
export function isChatOffError(error: ApiError | null): boolean {
  return Boolean(error?.isUnpaidBlocked());
}

export interface UseChatOptions {
  /** Called with the emergency kinds BEFORE the answer is added to the history (S19 first). */
  onEmergency?(kinds: string[], answer: ChatAnswer): void;
}

export interface UseChat {
  turns: ChatTurn[];
  sending: boolean;
  error: ApiError | null;
  maxQuestion: number;
  maxHistory: number;
  /** False when `/v1/config` says chat is off (unpaid / mixed tier) or the server answered 403. */
  available: boolean;
  /** True once more turns exist than are sent (the "I remember the last 8 messages." note). */
  historyCapped: boolean;
  send(question: string): Promise<ChatAnswer | null>;
  dismissError(): void;
}

export function useChat(analysis: AnalysisResult, options: UseChatOptions = {}): UseChat {
  const client = useApi();
  const { config } = useServerConfig();
  const id = analysis.analysis_id;
  const turns = useChatHistory((s) => s.byAnalysis[id] ?? EMPTY);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const maxHistory = config?.limits.max_chat_history ?? DEFAULT_MAX_HISTORY;
  const maxQuestion = config?.limits.max_question_chars ?? DEFAULT_MAX_QUESTION;
  const available = chatAvailable(config) && !isChatOffError(error);
  const { onEmergency } = options;

  const send = useCallback(
    async (question: string): Promise<ChatAnswer | null> => {
      const q = question.trim();
      if (!q || sending || !chatAvailable(serverConfigNow())) return null;
      const history = turnsToMessages(useChatHistory.getState().byAnalysis[id] ?? EMPTY);
      const req = buildChatRequest({
        analysis,
        history,
        question: q,
        targetLanguage: analysis.target_language || useI18n.getState().tag,
        // From the analysis itself, never the session's (possibly left-over) sample id (SEC-01).
        demoSampleId: sampleIdForAnalysis(analysis),
        maxHistory,
        maxQuestion,
      });
      turnSeq += 1;
      useChatHistory.getState().append(id, { id: `u${turnSeq}`, role: 'user', text: req.question });
      setSending(true);
      setError(null);
      try {
        const answer = await client.chat(req);
        const trig = emergencyTrigger(answer.safety);
        if (trig.triggered) onEmergency?.(trig.kinds, answer);
        turnSeq += 1;
        useChatHistory.getState().append(id, { id: `a${turnSeq}`, role: 'assistant', text: answer.answer, answer });
        return answer;
      } catch (e) {
        setError(toApiError(e));
        return null;
      } finally {
        setSending(false);
      }
    },
    [analysis, client, id, maxHistory, maxQuestion, onEmergency, sending],
  );

  return {
    turns,
    sending,
    error,
    maxQuestion,
    maxHistory,
    available,
    historyCapped: turns.length > maxHistory,
    send,
    dismissError: () => setError(null),
  };
}
