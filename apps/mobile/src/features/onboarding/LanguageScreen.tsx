// S1 — Which language? (PRODUCT_SPEC S1). One tap on a chip; any language reachable through the
// "My language is not here" box. Bundled packs switch instantly (offline); other tags and typed
// names go through S1b (`/onboarding/adapting`). Opened from S17 with `?from=settings`.

import { type Href, router } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { useServerConfig } from '@/api/config';
import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { Screen } from '@/design/components/Screen';
import { AppText, Heading, useTextStyle, webLangProps } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { switchLanguage } from '@/i18n/language';
import { suggestedTag } from '@/i18n/locale';
import { useT } from '@/i18n/useT';
import { useOnline } from '@/lib/network';
import { type TextSize, useSettings } from '@/store/settings';

import { useConsentDecision } from './consentState';
import { type GridLanguage, gridLanguages, matchTyped, typedQueryUsable, withSuggestionFirst } from './languageGrid';

const NEXT_SIZE: Record<TextSize, TextSize> = { normal: 'large', large: 'xl', xl: 'normal' };

export function adaptingHref(query: string, from: 'onboarding' | 'settings'): Href {
  return `/onboarding/adapting?q=${encodeURIComponent(query)}&from=${from}` as Href;
}

/** Where to go after a language is active. */
export function afterLanguageHref(from: 'onboarding' | 'settings', decision: string): Href {
  if (from === 'settings') return '/(tabs)/settings' as Href;
  return (decision === 'none' ? '/onboarding/consent' : '/(tabs)') as Href;
}

export interface LanguageScreenProps {
  from?: 'onboarding' | 'settings';
  navigate?(href: Href): void;
}

export function LanguageScreen({ from = 'onboarding', navigate = (h) => router.replace(h) }: LanguageScreenProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const { config } = useServerConfig();
  const { online } = useOnline();
  const decision = useConsentDecision((s) => s.decision);
  const currentTag = useSettings((s) => (s.languageDecided ? s.languageTag : null));
  const textSize = useSettings((s) => s.textSize);
  const setSetting = useSettings((s) => s.set);
  const inputStyle = useTextStyle('bodyLarge');

  const list = useMemo(() => gridLanguages(config?.languages), [config?.languages]);
  const { suggested, others } = useMemo(() => withSuggestionFirst(list, suggestedTag()), [list]);
  const [selected, setSelected] = useState<string | null>(currentTag ?? suggested?.tag ?? null);
  const [typed, setTyped] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canContinue = Boolean(selected) || typedQueryUsable(typed);

  const onContinue = async () => {
    setMessage(null);
    const typedMatch = typedQueryUsable(typed) ? matchTyped(list, typed) : null;
    const choice: GridLanguage | null = typedMatch ?? (typedQueryUsable(typed) ? null : list.find((l) => l.tag === selected) ?? null);
    if (choice?.offline) {
      setBusy(true);
      try {
        await switchLanguage(choice.tag);
        navigate(afterLanguageHref(from, decision));
      } finally {
        setBusy(false);
      }
      return;
    }
    const query = choice ? choice.tag : typed.trim();
    if (!online) {
      setMessage(t('state.lang_needs_internet'));
      return;
    }
    navigate(adaptingHref(query, from));
  };

  const chip = (l: GridLanguage, i: number, n: number) => {
    const isSel = selected === l.tag && !typedQueryUsable(typed);
    return (
      <Pressable
        key={l.tag}
        testID={`lang-chip-${l.tag}`}
        role="radio"
        aria-checked={isSel}
        accessibilityState={{ selected: isSel, checked: isSel }}
        accessibilityLabel={`${l.name_native}, ${l.name_en}, ${i + 1} / ${n}`}
        accessibilityLanguage={l.tag}
        hitSlop={size.hitSlop / 2}
        onPress={() => {
          setSelected(l.tag);
          setTyped('');
          setMessage(null);
        }}
        style={[
          styles.chip,
          {
            borderColor: isSel ? colors.primary : colors.border,
            backgroundColor: isSel ? colors.secondary : colors.surface,
          },
          isSel ? styles.chipSelected : null,
        ]}>
        <AppText variant="bodyLarge" weight="bold" lang={l.tag} fontHint={l.font_hint ?? null} align="center" {...webLangProps(l.tag, 'auto')}>
          {l.name_native}
        </AppText>
        {l.name_en !== l.name_native ? (
          <AppText variant="caption" color="textMuted" align="center">
            {l.name_en}
          </AppText>
        ) : null}
        {l.machine_translated ? (
          <AppText variant="caption" color="textMuted" align="center">
            {t('lang.machine_translated_dot')}
          </AppText>
        ) : null}
      </Pressable>
    );
  };

  return (
    <Screen back={from === 'settings'} testID="language-screen">
      <View style={[styles.titleRow, { flexDirection: dir.row }]}>
        <View style={styles.flex}>
          <Heading level={1}>{t('lang.title')}</Heading>
        </View>
        <Pressable
          role="button"
          accessibilityLabel={t('settings.text_size')}
          accessibilityValue={{ text: t(`settings.text_size_${textSize}`) }}
          hitSlop={size.hitSlop}
          onPress={() => setSetting('textSize', NEXT_SIZE[textSize])}
          style={[styles.aa, { borderColor: colors.border }]}>
          <Icon name="text-size" color={colors.primary} />
        </Pressable>
      </View>
      {suggested ? (
        <View style={styles.section}>
          <AppText weight="bold">{t('lang.suggested')}</AppText>
          <View role="radiogroup" style={[styles.grid, { flexDirection: dir.row }]}>
            {chip(suggested, 0, 1)}
          </View>
        </View>
      ) : null}
      <View role="radiogroup" style={[styles.grid, { flexDirection: dir.row }]}>
        {others.map((l, i) => chip(l, i, others.length))}
      </View>
      <View style={styles.section}>
        <AppText weight="bold">{t('lang.not_here')}</AppText>
        <TextInput
          testID="lang-typed"
          value={typed}
          onChangeText={(v) => {
            setTyped(v.slice(0, 60));
            setMessage(null);
          }}
          placeholder={t('lang.type_hint')}
          placeholderTextColor={colors.textMuted}
          accessibilityLabel={t('lang.not_here')}
          accessibilityHint={t('lang.type_hint')}
          autoCorrect={false}
          maxLength={60}
          style={[
            inputStyle,
            styles.input,
            { color: colors.text, borderColor: colors.border, textAlign: dir.textAlign, writingDirection: dir.writingDirection },
          ]}
        />
      </View>
      {message ? (
        <View role="alert">
          <AppText color="danger">{message}</AppText>
        </View>
      ) : null}
      <BigButton
        testID="lang-continue"
        label={t('btn.continue')}
        variant="primary"
        size={72}
        disabled={!canContinue || busy}
        onPress={() => void onContinue()}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  titleRow: {
    alignItems: 'center',
    gap: space.md,
  },
  aa: {
    width: size.button,
    height: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  section: {
    gap: space.sm,
  },
  grid: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    minHeight: size.button,
    minWidth: 140,
    flexGrow: 1,
    flexBasis: '45%',
    justifyContent: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  chipSelected: {
    borderWidth: 3,
  },
  input: {
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
});
