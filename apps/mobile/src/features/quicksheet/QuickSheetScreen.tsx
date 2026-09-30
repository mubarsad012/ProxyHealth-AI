// S15 Quick sheet (PRODUCT_SPEC S15): a text-only preview built client-side from the analysis +
// the last resource list for this paper, then per platform — native: Share PDF (expo-print →
// expo-sharing, gated by isAvailableAsync); web: Download PDF (server render → <a download>) and
// Print (browser dialog); everywhere: Copy text and Read aloud. Works offline except the web PDF.

import { useEffect, useMemo, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { AnalysisResult, Resource, ResourceMatch } from '@/api/types';
import { AppText, BigButton, ErrorState, FeedbackRow, Heading, Screen } from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useRegion } from '@/features/help/RegionControl';
import { buildMatchRequestForAnalysis, lastMatchForDocument, offlineMatchResponse } from '@/features/help/request';
import { useResourceMatch } from '@/features/help/useResourceMatch';
import { usePackMeta, useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';
import { speak, stop, useSpeaking } from '@/lib/tts';

import { buildQuickSheetText, quickSheetPlainText, toQuickSheetRequest } from './build';
import { loadQuickSheetFonts } from './fontData';
import { buildQuickSheetHtml } from './html';
import { downloadServerPdf } from './serverPdf';
import { canShareFiles, copyQuickSheetText, printQuickSheet, shareQuickSheetPdf } from './share';

export interface QuickSheetScreenProps {
  analysis: AnalysisResult;
  documentId?: string;
}

const isWeb = Platform.OS === 'web';

/** Matched resources first (DB entries only), then national fallbacks; ≤ 8 in the builder. */
export function resourcesFor(results: ResourceMatch[], fallbacks: Resource[]): Resource[] {
  return [...results.map((m) => m.resource), ...fallbacks];
}

export function QuickSheetScreen({ analysis, documentId }: QuickSheetScreenProps) {
  const t = useT();
  const meta = usePackMeta();
  const client = useApi();
  const { colors } = useTheme();
  const region = useRegion();
  const { online } = useOnline();
  const speaking = useSpeaking();
  const docId = documentId ?? analysis.analysis_id;
  const req = useMemo(
    () => buildMatchRequestForAnalysis(analysis, { region, language: meta.tag }),
    [analysis, region, meta.tag],
  );
  const match = useResourceMatch(req, { documentId: docId });
  // Last list for this paper, else (offline / server error) the bundled DB subset for its tags.
  const data =
    match.data ??
    lastMatchForDocument(docId) ??
    lastMatchForDocument(analysis.analysis_id) ??
    (match.error ? offlineMatchResponse(req) : null);
  const sheet = useMemo(() => {
    const results = data?.results ?? analysis.resource_preview ?? [];
    return buildQuickSheetText(analysis, resourcesFor(results, data?.national_fallbacks ?? []), t, {
      checklist: results.flatMap((m) => m.checklist ?? []),
    });
  }, [analysis, data, t]);
  const text = useMemo(() => quickSheetPlainText(sheet), [sheet]);
  const [shareAvailable, setShareAvailable] = useState<boolean | null>(isWeb ? false : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isWeb) return;
    let cancelled = false;
    void canShareFiles().then((ok) => {
      if (!cancelled) setShareAvailable(ok);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const html = async () =>
    buildQuickSheetHtml(sheet, {
      dir: meta.direction,
      lang: meta.tag,
      fontFamily: meta.fontHint,
      fontFaces: await loadQuickSheetFonts(meta.fontHint),
    });

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const onShare = () =>
    run(async () => {
      const outcome = await shareQuickSheetPdf(await html(), sheet.title);
      if (outcome === 'unavailable') setShareAvailable(false);
    });
  const onPrint = () => run(async () => printQuickSheet(await html()));
  const onDownload = () =>
    run(() =>
      downloadServerPdf(
        client,
        toQuickSheetRequest(sheet, { languageTag: meta.tag, direction: meta.direction, fontHint: meta.fontHint }),
      ),
    );
  const onCopy = () => {
    // First statement in the gesture (web clipboard rule).
    void copyQuickSheetText(text).then((ok) => setCopied(ok));
  };
  const onReadAloud = () => {
    if (speaking) void stop();
    else void speak(text, meta.tag, 'quicksheet');
  };

  const copyPrimary = !isWeb && shareAvailable === false;
  return (
    <Screen title={t('btn.quick_sheet')} back testID="quicksheet">
      <View style={styles.wrap}>
        <View style={[styles.sheet, { borderColor: colors.border, backgroundColor: colors.surfaceRaised }]} role="document">
          <Heading level={1} variant="title">
            {sheet.title}
          </Heading>
          {sheet.sections.map((s, i) => (
            <View key={`${s.heading_en}-${i}`} style={styles.section} role="region" accessibilityLabel={s.heading}>
              <Heading level={2} variant="bodyLarge">
                {s.heading}
              </Heading>
              {s.heading_en && s.heading_en !== s.heading ? (
                <AppText variant="caption" color="textMuted" lang="en" align="auto" style={styles.ltr}>
                  {s.heading_en}
                </AppText>
              ) : null}
              {s.lines.map((line, j) => (
                <AppText key={j}>{line}</AppText>
              ))}
            </View>
          ))}
          <AppText variant="caption" color="textMuted">
            {sheet.footer}
          </AppText>
        </View>

        {copyPrimary ? <AppText role="status">{t('state.share_unavailable')}</AppText> : null}
        {isWeb && !online ? <AppText role="status">{t('state.offline_disabled')}</AppText> : null}
        {copied ? <AppText role="status">{t('quicksheet.copied')}</AppText> : null}
        {error ? <ErrorState error={error} onRetry={isWeb ? onDownload : onShare} /> : null}

        {isWeb ? (
          <>
            <BigButton
              label={t('btn.download_pdf')}
              icon="papers"
              variant="primary"
              size={72}
              onPress={onDownload}
              disabled={busy || !online}
              testID="quicksheet-download"
            />
            <BigButton label={t('btn.print')} icon="papers" variant="secondary" size={56} onPress={onPrint} disabled={busy} />
          </>
        ) : shareAvailable !== false ? (
          <BigButton
            label={t('btn.share_pdf')}
            icon="papers"
            variant="primary"
            size={72}
            onPress={onShare}
            disabled={busy || shareAvailable === null}
            testID="quicksheet-share"
          />
        ) : null}
        <BigButton
          label={t('btn.copy_text')}
          icon={copied ? 'check' : 'papers'}
          variant={copyPrimary ? 'primary' : 'secondary'}
          size={copyPrimary ? 72 : 56}
          onPress={onCopy}
          testID="quicksheet-copy"
        />
        <BigButton
          label={t(speaking ? 'btn.stop' : 'btn.read_aloud')}
          icon={speaking ? 'stop' : 'speaker'}
          variant="secondary"
          size={56}
          onPress={onReadAloud}
        />
        <FeedbackRow surface="quicksheet" documentType={analysis.document_type} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  sheet: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.lg,
    gap: space.md,
  },
  section: {
    gap: space.xs,
  },
  ltr: {
    writingDirection: 'ltr',
    textAlign: 'left',
  },
});
