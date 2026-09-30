// S10 — Show the clerk (`/result/[id]/clerk`, `id = generic` for the no-analysis card; D-18,
// PRODUCT_SPEC §8). The card is ALWAYS LTR English, forced high contrast (black on white, 7:1+),
// ≥ 24 pt body / 32 pt greeting, no font-scaling cap. `session.clerkMode` hides the header and tab
// bar; the only exit is the 1.5 s hold on "Back to me" (in the user's language and direction).

import * as Clipboard from 'expo-clipboard';
import { type Href, router, Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import { BackHandler, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { AnalysisResult } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { palette, radius, size, space } from '@/design/tokens';
import { hasEnglishVoice } from '@/features/speech/fallback';
import { useDirection } from '@/i18n/direction';
import { fontFamilyFor } from '@/i18n/fonts';
import { usePackMeta, useT } from '@/i18n/useT';
import { resolveVoice, speak, stop, useSpeaking } from '@/lib/tts';
import { useSession } from '@/store/session';

import {
  type ClerkCard,
  clerkCardFromAnalysis,
  clerkCopyText,
  CLERK_OWN_WORDS_MAX,
  CLERK_PRESETS,
  type ClerkNeed,
  genericClerkCard,
} from './clerkModel';
import { LongPressExit } from './LongPressExit';

const HC = palette.highContrast;

/** Web DOM attributes RN does not type (`dir`, `lang`). */
const LTR_EN_WEB = (Platform.OS === 'web' ? { dir: 'ltr', lang: 'en' } : {}) as object;

function CardText({ children, greeting }: { children: string; greeting?: boolean }) {
  const fontSize = greeting ? 32 : 24;
  const family = fontFamilyFor('NotoSans', greeting ? 'bold' : 'regular');
  return (
    <Text
      allowFontScaling
      accessibilityLanguage="en-US"
      {...LTR_EN_WEB}
      style={[
        styles.cardText,
        { fontSize, lineHeight: Math.round(fontSize * 1.4) },
        family ? { fontFamily: family } : { fontWeight: greeting ? '700' : '400' },
      ]}>
      {children}
    </Text>
  );
}

/** "What this card says" disclosure. WP4's `Collapsible` follows the app theme (light text in dark
 *  mode), which vanishes on this forced white page, so the clerk screen draws its own with the
 *  high-contrast palette in every colour scheme (S10, 7:1+). Same a11y contract as `Collapsible`. */
function ClerkDisclosure({ title, children }: { title: string; children: string }) {
  const [open, setOpen] = useState(false);
  const dir = useDirection();
  return (
    <View testID="clerk-what-it-says">
      <Pressable
        role="button"
        aria-expanded={open}
        accessibilityState={{ expanded: open }}
        accessibilityLabel={title}
        hitSlop={size.hitSlop}
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => [styles.disclosure, { flexDirection: dir.row, opacity: pressed ? 0.7 : 1 }]}>
        <Icon name={open ? 'chevron-down' : 'chevron-right'} color={HC.text} size={20} />
        <View style={styles.flex}>
          <AppText weight="bold" colorValue={HC.text}>
            {title}
          </AppText>
        </View>
      </Pressable>
      {open ? (
        <View style={styles.disclosureBody}>
          <AppText colorValue={HC.text}>{children}</AppText>
        </View>
      ) : null}
    </View>
  );
}

/** Split the fixed template so the greeting ("Hello. I speak X.") renders at 32 pt. */
export function splitGreeting(line: string): [string, string] {
  const m = /^(Hello\.\s*I speak [^.]+\.)\s*(.*)$/s.exec(line);
  return m ? [m[1], m[2]] : ['', line];
}

export interface ClerkScreenProps {
  analysis: AnalysisResult | null;
}

export function ClerkScreen({ analysis }: ClerkScreenProps) {
  const t = useT();
  const meta = usePackMeta();
  const dir = useDirection();
  const insets = useSafeAreaInsets();
  const speaking = useSpeaking();
  const [need, setNeed] = useState<ClerkNeed>({ kind: 'default' });
  const [own, setOwn] = useState('');
  const [englishVoice, setEnglishVoice] = useState(false);
  const card: ClerkCard = analysis ? clerkCardFromAnalysis(analysis, t) : genericClerkCard(meta.tag, need, t);

  useEffect(() => {
    useSession.getState().setClerkMode(true);
    let alive = true;
    void resolveVoice('en')
      .then((v) => alive && setEnglishVoice(hasEnglishVoice(v)))
      .catch(() => alive && setEnglishVoice(false));
    const sub = Platform.OS === 'android' ? BackHandler.addEventListener('hardwareBackPress', () => true) : null;
    return () => {
      alive = false;
      sub?.remove();
      void stop();
      useSession.getState().setClerkMode(false);
    };
  }, []);

  const exit = () => {
    useSession.getState().setClerkMode(false);
    if (router.canGoBack()) router.back();
    else router.replace('/' as Href);
  };

  const [first, ...rest] = card.english;
  const [greeting, remainder] = splitGreeting(first ?? '');

  return (
    <View testID="clerk-screen" style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
      <Stack.Screen options={{ gestureEnabled: false, headerShown: false }} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <View testID="clerk-card" style={styles.card} {...LTR_EN_WEB}>
          {greeting ? <CardText greeting>{greeting}</CardText> : null}
          {remainder ? <CardText>{remainder}</CardText> : null}
          {rest.map((l, i) => (
            <CardText key={`l-${i}`}>{l}</CardText>
          ))}
          {card.ownWords ? (
            <AppText variant="caption" colorValue={HC.text}>
              {t('clerk.own_words')}
            </AppText>
          ) : null}
        </View>
        <AppText colorValue={HC.text}>{t('clerk.brightness_tip')}</AppText>
        <View style={styles.controls}>
          {analysis ? null : (
            <View style={styles.presets}>
              <View style={[styles.chips, { flexDirection: dir.row }]}>
                {CLERK_PRESETS.map((p) => {
                  const on = need.kind === 'preset' && need.preset === p;
                  return (
                    <Pressable
                      key={p}
                      role="button"
                      accessibilityState={{ selected: on }}
                      accessibilityLabel={t(`clerk.preset.${p}`)}
                      onPress={() => setNeed(on ? { kind: 'default' } : { kind: 'preset', preset: p })}
                      style={[styles.chip, { backgroundColor: on ? HC.primary : HC.background }]}>
                      <AppText colorValue={on ? HC.onPrimary : HC.text}>{t(`clerk.preset.${p}`)}</AppText>
                    </Pressable>
                  );
                })}
              </View>
              <AppText weight="bold" colorValue={HC.text}>
                {t('clerk.own_words')}
              </AppText>
              <TextInput
                accessibilityLabel={t('clerk.own_words')}
                value={own}
                maxLength={CLERK_OWN_WORDS_MAX}
                onChangeText={(v) => {
                  setOwn(v);
                  setNeed(v.trim() ? { kind: 'own', text: v } : { kind: 'default' });
                }}
                style={[styles.input, { textAlign: dir.textAlign, writingDirection: dir.writingDirection }]}
              />
            </View>
          )}
          {englishVoice ? (
            <BigButton
              label={speaking ? t('btn.stop') : t('btn.read_aloud_en')}
              icon={speaking ? 'stop' : 'speaker'}
              variant="secondary"
              size={56}
              onPress={() => {
                if (speaking) void stop();
                else void speak(card.english.join(' '), 'en');
              }}
            />
          ) : null}
          <BigButton
            label={t('btn.copy_text')}
            icon="papers"
            variant={Platform.OS === 'web' ? 'primary' : 'secondary'}
            size={56}
            onPress={() => {
              void Clipboard.setStringAsync(clerkCopyText(card));
            }}
          />
          <ClerkDisclosure title={t('clerk.what_it_says')}>{card.translated}</ClerkDisclosure>
          <LongPressExit onExit={exit} />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: HC.background },
  scroll: { padding: space.xl, gap: space.xl, maxWidth: 760, width: '100%', alignSelf: 'center' },
  card: { gap: space.lg, borderWidth: 3, borderColor: HC.border, borderRadius: radius.lg, padding: space.xl, backgroundColor: HC.background },
  cardText: { color: HC.text, textAlign: 'left', writingDirection: 'ltr' },
  controls: { gap: space.md },
  presets: { gap: space.sm },
  chips: { flexWrap: 'wrap', gap: space.sm },
  chip: { minHeight: size.minTouch, justifyContent: 'center', borderWidth: 2, borderColor: HC.border, borderRadius: radius.pill, paddingHorizontal: space.md },
  disclosure: { minHeight: size.minTouch, alignItems: 'center', gap: space.sm },
  flex: { flex: 1 },
  disclosureBody: { marginTop: space.sm, padding: space.lg, borderWidth: 2, borderColor: HC.border, borderRadius: radius.md, backgroundColor: HC.background },
  input: { minHeight: size.button, borderWidth: 2, borderColor: HC.border, borderRadius: radius.md, padding: space.md, fontSize: 18, color: HC.text },
});
