// S7 — Result screen (route `/result/[id]`). The analysis comes from `session.currentAnalysis`
// first, then the vault (`useDocument`, WP6 seam); an unknown id shows the S18 copy. Sticky action
// bar: Save (WP6 `SaveToVaultSheet`), Show the clerk, Quick sheet, Read all aloud / Stop.

import { type Href, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import type { AnalysisResult, Demand, ResourceTag } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { openExternal } from '@/design/components/ExternalLink';
import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { AppText } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { emergencyTrigger } from '@/features/emergency';
import { sendFeedbackOnce } from '@/features/feedback';
import { useReminders } from '@/features/reminders';
import { useVoiceNotice } from '@/features/speech';
import { useSequentialSpeech } from '@/features/speech/sequential';
import { memberName, SaveToVaultSheet, useDocument, useMembers } from '@/features/vault';
import { useDirection } from '@/i18n/direction';
import { useBidiText, usePackMeta, useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';
import { type CapturedPage, useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import type { ResultViewHandlers } from './ResultView';
import { ResultView } from './ResultView';
import { hearItItems } from './hearItMode';
import { useStoredPages } from './storedPages';

export function resultHref(id: string, sub?: 'source' | 'chat' | 'clerk' | 'quicksheet' | 'help', query?: string): Href {
  const base = `/result/${encodeURIComponent(id)}${sub ? `/${sub}` : ''}`;
  return (query ? `${base}?${query}` : base) as Href;
}

/** The one line shown after "Remind me" (fixed copy per outcome). */
export function remindNotice(outcome: string, d: Demand, t: (k: string, v?: Record<string, string | number>) => string): string | null {
  switch (outcome) {
    case 'scheduled':
      return t('reminders.added', { date: d.value_verbatim });
    case 'ics':
      return t('reminders.web_explain');
    case 'denied':
      return t('reminders.permission_denied');
    case 'not_eligible':
      return d.date?.kind === 'estimated' ? t('reminders.estimate_blocked') : null;
    default:
      return null;
  }
}

/**
 * Resolve the analysis for a route id: session first, then the vault. For a vault document,
 * `pages` are its kept page files (`vault.pages.uri`) and `keepPages` is `doc.keepPages`.
 */
export function useAnalysisFor(id: string): {
  analysis: AnalysisResult | null;
  pages: CapturedPage[];
  loading: boolean;
  documentId: string | null;
  keepPages: boolean;
} {
  const current = useSession((s) => s.currentAnalysis);
  const pages = useSession((s) => s.pages);
  const fromSession = current && current.analysis_id === id ? current : null;
  const { doc, loading } = useDocument(fromSession ? '' : id);
  const storedPages = useStoredPages(fromSession ? null : (doc?.id ?? null), Boolean(doc?.keepPages));
  if (fromSession) return { analysis: fromSession, pages, loading: false, documentId: null, keepPages: true };
  return {
    analysis: doc?.analysis ?? null,
    pages: storedPages,
    loading,
    documentId: doc ? doc.id : null,
    keepPages: Boolean(doc?.keepPages),
  };
}

export function ResultScreen({ id }: { id: string }) {
  const t = useT();
  const bt = useBidiText();
  const meta = usePackMeta();
  const dir = useDirection();
  const { analysis, pages, loading, documentId } = useAnalysisFor(id);
  const { online } = useOnline();
  const client = useApi();
  const reminders = useReminders();
  const speech = useSequentialSpeech();
  const hearIt = useSettings((s) => s.hearItMode);
  const voiceNotice = useVoiceNotice(meta.tag);
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(documentId);
  const [notice, setNotice] = useState<string | null>(null);
  const autoPlayed = useRef(false);
  // "Saved for {member}" (S7 item 18 chip) is literally true on web and native alike (CL-042);
  // `vault.saved` ("It stays on this phone") is not true in a browser.
  const { doc: savedDoc } = useDocument(savedId ?? '');
  const { members } = useMembers();
  const savedLabel = t('vault.saved_to', {
    member: memberName(members.find((m) => m.id === savedDoc?.memberId) ?? null, t),
  });

  const readAll = () => {
    if (!analysis) return;
    if (speech.playing) {
      speech.stop();
      return;
    }
    void speech.play(hearItItems(analysis, t, meta.tag, emergencyTrigger(analysis.safety).triggered));
  };

  useEffect(() => {
    if (analysis && hearIt && !autoPlayed.current) {
      autoPlayed.current = true;
      void speech.play(hearItItems(analysis, t, meta.tag, emergencyTrigger(analysis.safety).triggered));
    }
  }, [analysis, hearIt, meta.tag, speech, t]);

  if (!analysis) {
    return (
      <Screen back title={t('app.name')} testID="result-screen">
        {loading ? null : (
          <EmptyState text={t('notfound.title')} actionLabel={t('btn.go_home')} onAction={() => router.replace('/' as Href)} />
        )}
      </Screen>
    );
  }

  const a = analysis;
  const handlers: ResultViewHandlers = {
    onOpenSource: ({ block, page }) =>
      router.push(resultHref(a.analysis_id, 'source', [block ? `block=${encodeURIComponent(block)}` : '', page ? `page=${page}` : ''].filter(Boolean).join('&'))),
    onRescan: () => router.push('/scan/review' as Href),
    onRemind: (d: Demand) => {
      void reminders
        .scheduleForDemand(a, d, savedId ?? undefined)
        .then((outcome) => setNotice(remindNotice(outcome, d, t)))
        .catch(() => setNotice(null));
    },
    onFindHelp: (tags: ResourceTag[]) => router.push(resultHref(a.analysis_id, 'help', `tags=${tags.join(',')}`)),
    onAsk: (q?: string) => router.push(resultHref(a.analysis_id, 'chat', q ? `q=${encodeURIComponent(q)}` : undefined)),
    onOpenUrl: (url) => void openExternal(url),
    onCall: (href) => void Linking.openURL(href).catch(() => undefined),
    onEmergencyMoreHelp: () => router.push('/help?emergency=1' as Href),
    onSeeAllHelp: () => router.push(resultHref(a.analysis_id, 'help')),
    onSetRegion: () => router.push('/settings' as Href),
    onVerifyResource: (rid) => router.push(resultHref(a.analysis_id, 'help', `focus=${encodeURIComponent(rid)}`)),
    onReportProblem: () => {
      void sendFeedbackOnce(
        client,
        { surface: 'summary', documentType: a.document_type, documentCategory: a.category, modelId: a.model_meta.model_id },
        'wrong_fact',
        meta.tag,
      ).then(() => setNotice(t('feedback.thanks')));
    },
  };

  const footer = (
    <View style={styles.footer}>
      {voiceNotice ? (
        <AppText variant="caption" color="textMuted" role="status" testID="tts-fallback-notice">
          {voiceNotice}
        </AppText>
      ) : null}
      <View style={[styles.bar, { flexDirection: dir.row }]}>
        <View style={styles.cell}>
          <BigButton
            label={savedId ? savedLabel : t('btn.save')}
            icon={savedId ? 'check' : 'papers'}
            variant="primary"
            size={56}
            disabled={Boolean(savedId)}
            onPress={() => setSaving(true)}
          />
        </View>
        <View style={styles.cell}>
          <BigButton label={t('btn.show_clerk')} icon="people" variant="secondary" size={56} onPress={() => router.push(resultHref(a.analysis_id, 'clerk'))} />
        </View>
        <View style={styles.cell}>
          <BigButton label={t('btn.quick_sheet')} icon="papers" variant="secondary" size={56} onPress={() => router.push(resultHref(a.analysis_id, 'quicksheet'))} />
        </View>
        <View style={styles.cell}>
          <BigButton
            label={speech.playing ? t('btn.stop') : t('btn.read_all')}
            icon={speech.playing ? 'stop' : 'speaker'}
            variant="secondary"
            size={56}
            onPress={readAll}
          />
        </View>
      </View>
    </View>
  );

  return (
    <Screen back title={bt(a.summary.title)} footer={footer} testID="result-screen">
      {notice ? (
        <AppText role="status" color="success">
          {notice}
        </AppText>
      ) : null}
      <ResultView analysis={a} pages={pages} handlers={handlers} offline={!online} />
      {saving ? (
        <SaveToVaultSheet
          analysis={a}
          pages={pages}
          onSaved={(docId) => {
            setSaving(false);
            setSavedId(docId);
          }}
          onCancel={() => setSaving(false)}
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  footer: {
    gap: space.xs,
  },
  bar: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  cell: {
    flexGrow: 1,
    flexBasis: 150,
  },
});
