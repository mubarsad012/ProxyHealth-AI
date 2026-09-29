// External link (moved from the template's components/external-link.tsx, BUILD_PLAN §5.5).
// Native: opens http(s) URLs in the in-app browser (expo-web-browser `openBrowserAsync`, verified
// against https://docs.expo.dev/versions/v57.0.0/sdk/webbrowser/); `tel:`/`sms:`/`mailto:` go to
// the system via `Linking`. Web: a new tab. URLs only ever come from the paper or the vetted
// resource DB (ARCHITECTURE §7) — this component never builds one.

import { openBrowserAsync, WebBrowserPresentationStyle } from 'expo-web-browser';
import type { ReactNode } from 'react';
import { Linking, Platform, Pressable } from 'react-native';

import { AppText, type TextVariant } from '@/design/components/Text';
import { size } from '@/design/tokens';

export interface ExternalLinkProps {
  href: string;
  children: ReactNode;
  variant?: TextVariant;
  accessibilityHint?: string;
}

export async function openExternal(href: string): Promise<void> {
  const isHttp = /^https?:\/\//i.test(href);
  if (Platform.OS !== 'web' && isHttp) {
    await openBrowserAsync(href, { presentationStyle: WebBrowserPresentationStyle.AUTOMATIC });
    return;
  }
  if (Platform.OS === 'web' && isHttp && typeof window !== 'undefined') {
    window.open(href, '_blank', 'noopener,noreferrer');
    return;
  }
  await Linking.openURL(href);
}

export function ExternalLink({ href, children, variant = 'body', accessibilityHint }: ExternalLinkProps) {
  return (
    <Pressable
      role="link"
      accessibilityHint={accessibilityHint}
      hitSlop={size.hitSlop}
      onPress={() => {
        void openExternal(href).catch(() => undefined);
      }}>
      <AppText variant={variant} color="link" style={{ textDecorationLine: 'underline' }}>
        {children}
      </AppText>
    </Pressable>
  );
}
