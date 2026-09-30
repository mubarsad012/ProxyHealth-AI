// S9 grounded chat (API_CONTRACT §3.7, PRODUCT_SPEC S9, D-17): the request carries the compacted
// analysis context (≤ 60 000 chars, oldest pages dropped first) and at most the last 8 turns; the
// assistant bubble shows the answer, then the fixed refusal / "not in the paper" / referral
// templates; quote chips; "Get help" for lawyer/housing referrals; `safety.emergency` opens S19;
// a prompt tapped on S7 (`?q=`) is asked exactly once.

import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import type { ApiClient } from '@/api/client';
import type { AnalysisResult, ChatAnswer, ChatMessage, ChatRequest, PageText } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { bundledPackFor, EN_PACK, t, translate, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import { assistantLines, ChatScreen } from './ChatScreen';
import { buildChatRequest, compactOriginalText, historyForRequest } from './context';
import { referShowsHelp, starterQuestions } from './refusalTemplates';
import { useChatHistory } from './useChat';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
}));

// The expo-network jest mock's listener has no `remove()`; reachability is not under test here.
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

const analysis = JSON.parse(JSON.stringify(medicaidEn)) as AnalysisResult;

function answer(patch: Partial<ChatAnswer> = {}): ChatAnswer {
  return {
    request_id: 'r1',
    answer: 'The paper asks you to send proof of address.',
    grounded_span_ids: ['p1b5'],
    grounded_quotes: [{ span_id: 'p1b5', text: 'by October 14, 2026', page: 1 }],
    not_in_document: false,
    refusal_kind: 'none',
    refer_to_professional: 'none',
    distress_acknowledged: false,
    suggested_questions: ['What counts as proof?'],
    resource_tags: [],
    safety: { emergency: false, emergency_kinds: [], credential_or_payment_request: false },
    disclaimer_kind: 'benefits_information_only',
    warnings: [],
    model_meta: {
      provider: 'mock',
      tier: 'fast',
      model_id: 'mock',
      thinking_level: null,
      quality: 'full',
      analysis_mode: 'mock',
      data_use_tier: 'demo',
      demo: true,
      latency_ms: 0,
    },
    ...patch,
  } as ChatAnswer;
}

function chatClient(reply: (req: ChatRequest) => ChatAnswer): { client: ApiClient; log: ChatRequest[] } {
  const log: ChatRequest[] = [];
  const client = new Proxy({} as ApiClient, {
    get: (_t, prop) => {
      if (prop === 'chat') {
        return async (req: ChatRequest) => {
          log.push(req);
          return reply(req);
        };
      }
      if (prop === 'baseUrl') return 'http://127.0.0.1:8027';
      return () => Promise.reject(new Error('not used'));
    },
  });
  return { client, log };
}

async function renderChat(client: ApiClient, initialQuestion?: string) {
  return render(
    <AppProviders client={client} staticMetrics>
      <ChatScreen analysis={analysis} initialQuestion={initialQuestion} />
    </AppProviders>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  useChatHistory.getState().clear();
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
});

describe('chat request', () => {
  it('sends only the last 8 turns, each ≤ 1000 chars, and a trimmed question ≤ 1000 chars', () => {
    const history: ChatMessage[] = Array.from({ length: 12 }, (_, i) => ({
      role: i % 2 ? 'assistant' : 'user',
      text: i === 11 ? 'x'.repeat(1500) : `turn ${i}`,
    }));
    const req = buildChatRequest({ analysis, history, question: `  ${'q'.repeat(1200)}  `, targetLanguage: 'prs', demoSampleId: null });
    expect(req.messages).toHaveLength(8);
    expect(req.messages?.[0].text).toBe('turn 4');
    expect(req.messages?.[7].text).toHaveLength(1000);
    expect(req.question).toHaveLength(1000);
    expect(req.target_language).toBe('prs');
    expect(req.analysis.analysis_id).toBe(analysis.analysis_id);
    expect(historyForRequest(history, 3).map((m) => m.text.slice(0, 7))).toEqual(['turn 9', 'turn 10', 'xxxxxxx']);
  });

  it('compacts the transcript to the cap by dropping the oldest pages first', () => {
    const page = (n: number, chars: number): PageText => ({
      page: n,
      width: null,
      height: null,
      blocks: [{ id: `p${n}b1`, page: n, text: 'a'.repeat(chars), bbox: null, is_handwriting: false, is_unclear: false }],
    });
    const out = compactOriginalText([page(1, 40_000), page(2, 30_000), page(3, 20_000)]);
    expect(out.map((p) => p.page)).toEqual([2, 3]);
    const one = compactOriginalText([page(1, 70_000)]);
    expect(one).toEqual([{ ...page(1, 70_000), blocks: [] }]);
  });
});

describe('assistant bubble text', () => {
  it('answer first, then the fixed templates; the model never writes them', () => {
    const lines = assistantLines(
      answer({ refusal_kind: 'eligibility', not_in_document: true, refer_to_professional: 'lawyer_or_accredited_rep' }),
      t,
    );
    // "The paper does not say." is the server's (chat_pipeline.with_not_in_document); a refusal
    // speaks through its own template instead.
    expect(lines).toEqual([
      'The paper asks you to send proof of address.',
      t('chat.refusal.eligibility'),
      t('chat.refer.lawyer_or_accredited_rep'),
    ]);
    expect(assistantLines(answer({ answer: '  ', refusal_kind: 'drafting' }), t)).toEqual([t('chat.refusal.drafting')]);
    expect(referShowsHelp('housing_counselor')).toBe(true);
    expect(referShowsHelp('sender')).toBe(false);
  });

  it('shows "The paper does not say." once: the server sentence is never repeated', () => {
    const fixed = t('chat.not_in_document');
    const lines = assistantLines(answer({ answer: `${fixed} It is about: a Medicaid letter.`, not_in_document: true, grounded_quotes: [] }), t);
    expect(lines).toEqual([`${fixed} It is about: a Medicaid letter.`]);
    expect(lines.join(' ').split(fixed)).toHaveLength(2);
    // Only an empty non-refusal answer (an older server) falls back to the fixed key.
    expect(assistantLines(answer({ answer: '', not_in_document: true }), t)).toEqual([fixed]);
    // A template the answer already carries (the server's fixed out_of_scope reply) is not repeated.
    const oos = t('chat.refusal.out_of_scope');
    expect(assistantLines(answer({ answer: oos, refusal_kind: 'out_of_scope', not_in_document: true }), t)).toEqual([oos]);
  });

  it('renders the Dari sentence once in the bubble (prs pack)', async () => {
    const prs = bundledPackFor('prs')!;
    useI18n.getState().setPack(prs);
    try {
      const fixed = prs.strings['chat.not_in_document'];
      const lines = assistantLines(answer({ answer: `${fixed} درباره این است: X`, not_in_document: true }), (k) => translate(prs.strings, k));
      expect(lines).toHaveLength(1);
      expect(lines[0].split(fixed)).toHaveLength(2);
    } finally {
      useI18n.getState().setPack(EN_PACK);
    }
  });

  it('starter chips: questions_to_ask first, then fixed starters by demand kind, at most 5', () => {
    const chips = starterQuestions(analysis, t);
    expect(chips.slice(0, analysis.questions_to_ask.length)).toEqual(analysis.questions_to_ask.slice(0, 5));
    expect(chips).toContain(t('chat.starter.miss_date'));
    expect(chips.length).toBeLessThanOrEqual(5);
  });
});

describe('<ChatScreen>', () => {
  it('shows the scope line, sends a chip, renders quote chips + referral + Get help', async () => {
    const { client, log } = chatClient(() => answer({ refer_to_professional: 'lawyer_or_accredited_rep' }));
    const screen = await renderChat(client);
    expect(screen.getByText(t('chat.scope'))).toBeTruthy();
    const firstChip = starterQuestions(analysis, t)[0];
    await act(async () => {
      fireEvent.press(screen.getByLabelText(firstChip));
    });
    await waitFor(() => expect(screen.getByText('The paper asks you to send proof of address.')).toBeTruthy());
    expect(log).toHaveLength(1);
    expect(log[0].question).toBe(firstChip);
    expect(screen.getByText(t('chat.refer.lawyer_or_accredited_rep'))).toBeTruthy();
    expect(screen.getByText(t('btn.get_help'))).toBeTruthy();
    expect(screen.getByLabelText(t('chat.from_your_paper', { page: 1, text: 'by October 14, 2026' }))).toBeTruthy();
    // The next chips come from the last answer's suggested_questions.
    expect(screen.getByLabelText('What counts as proof?')).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();
  });

  it('ChatAnswer.safety.emergency opens the S19 card over the chat', async () => {
    const { client } = chatClient(() =>
      answer({ safety: { emergency: true, emergency_kinds: ['chest_pain'], credential_or_payment_request: false } }),
    );
    const screen = await renderChat(client);
    await act(async () => {
      fireEvent.press(screen.getByLabelText(starterQuestions(analysis, t)[0]));
    });
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/emergency?kinds=chest_pain'));
  });

  it('a prompt tapped on S7 is asked exactly once when the screen opens', async () => {
    const { client, log } = chatClient(() => answer());
    const screen = await renderChat(client, 'What happens if my form arrives after October 14?');
    await waitFor(() => expect(log).toHaveLength(1));
    expect(log[0].question).toBe('What happens if my form arrives after October 14?');
    await screen.rerender(
      <AppProviders client={client} staticMetrics>
        <ChatScreen analysis={analysis} initialQuestion="What happens if my form arrives after October 14?" />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText('The paper asks you to send proof of address.')).toBeTruthy());
    expect(log).toHaveLength(1);
  });
});
