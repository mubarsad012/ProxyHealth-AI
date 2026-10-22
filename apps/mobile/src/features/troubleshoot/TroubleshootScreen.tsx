// S16 Stuck on a website? / Is this a scam? (PRODUCT_SPEC S16, D-13). Mode chips; the screenshot
// picker runs inside the gesture (web rule); optional goal (≤ limits.max_user_goal_chars) and
// portal hint; the standing credential guard; two-step progress; the emergency card first when
// `safety.emergency`; result cards. One image only — a PDF is never sent.
// Consent (S2, CL-070): without an accepted consent record "Pick a screenshot" and "Explain this
// screen" open S2 instead — the user's own screenshot never leaves the phone before consent (the
// server's 428 would come only after the bytes were uploaded). "Try a sample" stays open.
// "Hide parts" on the preview (S5's MaskEditor; boxes sent like S5: web burns them, native sends
// `masks[]`). "Save as proof" opens "Whose paper is this?" (default Me) and stores only the
// pixels that were sent with the boxes burned in (`masks.ts`).
// A new result is scrolled into view with focus on its first heading (`reveal.ts`), unless the
// emergency card opened first.

import { type Href, router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import type { MaskRect, PortalHint, TroubleshootMode } from '@/api/types';
import {
  AppText,
  Banner,
  BigButton,
  ChoiceChips,
  ErrorState,
  openEmergency,
  ProgressSteps,
  Screen,
} from '@/design/components';
import { useReduceMotion, useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { EmergencyCard, useEmergencyTrigger } from '@/features/emergency';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { ME_MEMBER_ID, memberName, SaveToVaultSheet, useMembers } from '@/features/vault';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';
import { platformName } from '@/lib/platform';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import { buildEvidenceDocument, canSaveEvidence } from './evidence';
import { prepareScreenshot } from './masks';
import { pickScreenshot, type Screenshot } from './pick';
import { buildTroubleshootRequest, MAX_GOAL_CHARS, PORTAL_HINTS, SAMPLE_SCREENSHOT_ID } from './request';
import { CredentialGuard, type EvidenceControl, TroubleshootResultCards } from './ResultCards';
import { revealResult } from './reveal';
import { ScreenshotPreview } from './ScreenshotPreview';
import { useTroubleshoot } from './useTroubleshoot';

interface EvidenceState {
  saved: boolean;
  busy: boolean;
  failed: boolean;
  /** Display name of the member the proof was saved for. */
  member?: string;
}

const NO_EVIDENCE: EvidenceState = { saved: false, busy: false, failed: false };

export interface TroubleshootScreenProps {
  initialMode?: TroubleshootMode;
}

export function TroubleshootScreen({ initialMode = 'portal' }: TroubleshootScreenProps) {
  const t = useT();
  const meta = usePackMeta();
  const dir = useDirection();
  const { colors, textFactor } = useTheme();
  const { online } = useOnline();
  const maxGoal = useSession((s) => s.serverConfig?.limits?.max_user_goal_chars) ?? MAX_GOAL_CHARS;
  const [mode, setMode] = useState<TroubleshootMode>(initialMode);
  const [shot, setShot] = useState<Screenshot | null>(null);
  const [goal, setGoal] = useState('');
  const [hint, setHint] = useState<PortalHint | null>(null);
  const [pickFailed, setPickFailed] = useState(false);
  const [emergencyClosed, setEmergencyClosed] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceState>(NO_EVIDENCE);
  const [masks, setMasks] = useState<MaskRect[]>([]);
  // The pixels that were sent for the current result, boxes burned in (null: none may be stored).
  const [proof, setProof] = useState<Screenshot | null>(null);
  const [prepFailed, setPrepFailed] = useState(false);
  const [askWhose, setAskWhose] = useState(false);
  const { members } = useMembers();
  const hideIds = useSettings((s) => s.hideIdNumbers);
  const ts = useTroubleshoot();
  const decision = useConsentDecision((s) => s.decision);
  const consent = useSession((s) => s.consent);
  // Same rule as Home `scan()`/`pick()`: a real screenshot needs an accepted consent record.
  const consentOk = decision === 'accepted' && consent !== null;
  const emergency = useEmergencyTrigger(ts.result?.safety ?? null);
  const resultId = ts.result?.request_id ?? null;
  const resultRef = useRef<View | null>(null);
  const reduceMotion = useReduceMotion();
  // A result can repeat its request_id (the recorded sample): reveal per arrival, not per id.
  const shownResult = ts.result;

  useEffect(() => {
    // D-14: the fixed emergency card opens first (modal route), then the result stays below.
    if (emergency.triggered && resultId) openEmergency();
  }, [emergency.triggered, resultId]);

  useEffect(() => {
    if (!shownResult || emergency.triggered) return;
    // After layout: the result's position is only known once it has rendered.
    const id = setTimeout(() => revealResult(resultRef.current, { smooth: !reduceMotion }), 50);
    return () => clearTimeout(id);
  }, [shownResult, emergency.triggered, reduceMotion]);

  const openConsent = () => router.push('/onboarding/consent' as Href);

  const onPick = () => {
    if (!consentOk) {
      openConsent(); // nothing is picked (or sent) before consent
      return;
    }
    const picking = pickScreenshot(); // first call: the web file dialog needs the gesture
    setPickFailed(false);
    void picking
      .then((s) => {
        if (s) {
          setShot(s);
          setMasks([]);
          setProof(null);
          setEvidence(NO_EVIDENCE);
          ts.reset();
        }
      })
      .catch(() => setPickFailed(true));
  };

  const common = { mode, goal, portalHint: hint, language: meta.tag, platform: platformName(), maxGoalChars: maxGoal };
  const onSubmit = () => {
    if (!shot) return;
    if (!consentOk) {
      // e.g. "Stop sending papers" after the pick: the picked screenshot is not sent.
      openConsent();
      return;
    }
    setPrepFailed(false);
    setEvidence(NO_EVIDENCE);
    void prepareScreenshot(shot, masks, common.platform)
      .then((prepared) => {
        setProof(prepared.proof);
        return ts.submit(buildTroubleshootRequest({ ...common, screenshot: prepared.input }));
      })
      // The boxes could not be burned in: nothing is sent.
      .catch(() => setPrepFailed(true));
  };
  const onMasks = (next: MaskRect[]) => {
    setMasks(next);
    // A result (and its proof copy) belongs to the boxes it was sent with.
    setProof(null);
    setEvidence(NO_EVIDENCE);
    ts.reset();
  };
  const onSample = () => {
    setShot(null);
    setMasks([]);
    setProof(null);
    setEvidence(NO_EVIDENCE);
    void ts.runSample(
      (screenshot) => buildTroubleshootRequest({ ...common, screenshot, demoSampleId: SAMPLE_SCREENSHOT_ID }),
      meta.tag,
    );
  };

  // "Save as proof" → "Whose paper is this?" (default Me); the sheet writes nothing until Save.
  const onSaveEvidence = () => {
    if (!canSaveEvidence(proof) || evidence.busy || evidence.saved) return;
    setAskWhose(true);
  };
  // Scam mode, a real picked screenshot, a real (non-demo) result: offer "Save as proof". Not while
  // `settings.hide_ids` is on: the proof is the screenshot image, and saves with that setting keep
  // no page images (vault/documents.ts `buildStoredDocument`). Not when the boxes could not be
  // burned into stored pixels (native with "Hide parts" boxes, `masks.ts`).
  const evidenceControl: EvidenceControl | null =
    mode === 'scam_check' &&
    !hideIds &&
    canSaveEvidence(proof) &&
    ts.result &&
    !ts.offlineSample &&
    !ts.result.model_meta?.demo
      ? {
          ...evidence,
          onSave: onSaveEvidence,
          member: evidence.member ?? memberName(members.find((m) => m.id === ME_MEMBER_ID) ?? null, t),
        }
      : null;
  const proofShot = canSaveEvidence(proof) ? proof : null;

  const loading = ts.status === 'loading';
  const title = mode === 'scam_check' ? t('troubleshoot.mode_scam') : t('home.tile_troubleshoot');
  return (
    <Screen title={title} back testID="troubleshoot">
      <View style={styles.wrap}>
        {ts.result && emergency.triggered && emergencyClosed !== resultId ? (
          <EmergencyCard kinds={emergency.kinds} onClose={() => setEmergencyClosed(resultId)} />
        ) : null}
        <ChoiceChips<TroubleshootMode>
          options={[
            { value: 'portal', label: t('troubleshoot.mode_portal') },
            { value: 'scam_check', label: t('troubleshoot.mode_scam') },
          ]}
          value={mode}
          onChange={(m) => {
            setMode(m);
            ts.reset();
          }}
          testIDPrefix="troubleshoot-mode"
        />
        <CredentialGuard detected={false} />
        {!online ? <Banner kind="offline" /> : null}
        <BigButton
          label={t('troubleshoot.pick_screenshot')}
          icon="image"
          variant={shot ? 'secondary' : 'primary'}
          size={shot ? 56 : 72}
          onPress={onPick}
          disabled={loading}
          testID="troubleshoot-pick"
        />
        {!consentOk ? (
          <Pressable
            testID="troubleshoot-consent-needed"
            role="link"
            onPress={openConsent}
            hitSlop={size.hitSlop}>
            <AppText color="link" weight="bold">
              {t('home.consent_needed')}
            </AppText>
          </Pressable>
        ) : null}
        {pickFailed ? <AppText role="alert">{t('state.unreadable_screenshot')}</AppText> : null}
        {shot ? <ScreenshotPreview shot={shot} masks={masks} onChangeMasks={onMasks} disabled={loading} /> : null}
        <View style={styles.field}>
          <AppText weight="bold" nativeID="ts-goal-label">
            {t('troubleshoot.goal_label')}
          </AppText>
          <TextInput
            value={goal}
            onChangeText={(v) => setGoal(Array.from(v).slice(0, maxGoal).join(''))}
            maxLength={maxGoal}
            multiline
            accessibilityLabel={t('troubleshoot.goal_label')}
            aria-labelledby="ts-goal-label"
            style={[
              styles.input,
              {
                borderColor: colors.border,
                color: colors.text,
                backgroundColor: colors.surfaceRaised,
                textAlign: dir.textAlign,
                writingDirection: dir.writingDirection,
                fontSize: Math.round(18 * textFactor),
              },
            ]}
          />
        </View>
        {mode === 'portal' ? (
          <ChoiceChips<PortalHint>
            options={PORTAL_HINTS.map((h) => ({ value: h, label: t(`portal.${h}`) }))}
            value={hint}
            onChange={setHint}
            testIDPrefix="troubleshoot-portal"
          />
        ) : null}
        <BigButton
          label={t(mode === 'scam_check' ? 'troubleshoot.cta_scam' : 'troubleshoot.cta')}
          sublabel={online ? undefined : t('state.offline_disabled')}
          icon="search"
          variant="primary"
          size={72}
          onPress={onSubmit}
          disabled={!shot || loading || !online}
          testID="troubleshoot-submit"
        />
        <BigButton
          label={t('btn.try_sample')}
          sublabel={t('fixture.portal_file_too_large')}
          icon="sample"
          variant="secondary"
          size={56}
          onPress={onSample}
          disabled={loading}
          testID="troubleshoot-sample"
        />
        {loading ? (
          <ProgressSteps steps={[t('troubleshoot.step_read'), t('troubleshoot.step_explain')]} active={ts.step} />
        ) : null}
        {prepFailed ? (
          <AppText role="alert" color="danger" testID="troubleshoot-prep-failed">
            {t('err.internal')}
          </AppText>
        ) : null}
        {ts.status === 'error' && ts.error ? (
          <ErrorState error={ts.error} onRetry={shot ? onSubmit : undefined} onTrySample={onSample} />
        ) : null}
        {ts.result ? (
          <View ref={resultRef} style={styles.wrap} testID="troubleshoot-result-block">
            {ts.result.model_meta?.demo || ts.offlineSample ? <Banner kind="demo" /> : null}
            <TroubleshootResultCards result={ts.result} evidence={evidenceControl} />
          </View>
        ) : null}
      </View>
      {askWhose && proofShot ? (
        <SaveToVaultSheet
          buildDocument={(memberId, now) => buildEvidenceDocument(proofShot, { title: t('vault.title_scam_check'), now, memberId })}
          onSaved={(_id, savedFor) => {
            setAskWhose(false);
            setEvidence({ saved: true, busy: false, failed: false, member: savedFor });
          }}
          onCancel={() => setAskWhose(false)}
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  field: {
    gap: space.xs,
  },
  input: {
    minHeight: size.button * 1.5,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md,
  },
});
