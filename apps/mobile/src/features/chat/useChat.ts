// `useChat` (ARCHITECTURE §3 features/chat; PRODUCT_SPEC S9). History lives only in memory on the
// device (per analysis; saved with the paper by the vault when the user saves). The request carries
// the compacted analysis context and the last ≤ `limits.max_chat_history` turns.

import { useCallback, useState } from 'react';
import { create } from 'zustand';

import { useApi, useServerConfig } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { AnalysisResult, ChatAnswer, ChatMessage } from '@/api/types';
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
let turnSeq = 0;

export function turnsToMessages(turns: readonly ChatTurn[]): ChatMessage[] {
  return turns.map((t) => ({ role: t.role, text: t.text }));
}

export interface UseChat {
  turns: ChatTurn[];
  sending: boolean;
  error: ApiError | null;
  maxQuestion: number;
  maxHistory: number;
  /** True once more turns exist than are sent (the "I remember the last 8 messages." note). */
  historyCapped: boolean;
  send(question: string): Promise<ChatAnswer | null>;
  dismissError(): void;
}

export function useChat(analysis: AnalysisResult): UseChat {
  const client = useApi();
  const { config } = useServerConfig();
  const id = analysis.analysis_id;
  const turns = useChatHistory((s) => s.byAnalysis[id] ?? EMPTY);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const maxHistory = config?.limits.max_chat_history ?? DEFAULT_MAX_HISTORY;
  const maxQuestion = config?.limits.max_question_chars ?? DEFAULT_MAX_QUESTION;

  const send = useCallback(
    async (question: string): Promise<ChatAnswer | null> => {
      const q = question.trim();
      if (!q || sending) return null;
      const history = turnsToMessages(useChatHistory.getState().byAnalysis[id] ?? EMPTY);
      const req = buildChatRequest({
        analysis,
        history,
        question: q,
        targetLanguage: useI18n.getState().tag,
        demoSampleId: useSession.getState().demoSampleId,
        maxHistory,
        maxQuestion,
      });
      turnSeq += 1;
      useChatHistory.getState().append(id, { id: `u${turnSeq}`, role: 'user', text: req.question });
      setSending(true);
      setError(null);
      try {
        const answer = await client.chat(req);
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
    [analysis, client, id, maxHistory, maxQuestion, sending],
  );

  return {
    turns,
    sending,
    error,
    maxQuestion,
    maxHistory,
    historyCapped: turns.length > maxHistory,
    send,
    dismissError: () => setError(null),
  };
}
