// EmptyState and ErrorState (PRODUCT_SPEC §5.3/§5.4): one sentence + one primary action; errors
// render `user_message_key` copy (never raw upstream text) with the §5.4 primary/secondary actions.
// `{minutes}` counts down informationally (WCAG 2.2.1: Retry stays tappable).

import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { type ApiError, errorMessageVars } from '@/api/errors';
import { BigButton } from '@/design/components/BigButton';
import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { keyExists } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { useSession } from '@/store/session';

export interface EmptyStateProps {
  text: string;
  icon?: IconName;
  actionLabel?: string;
  onAction?(): void;
}

export function EmptyState({ text, icon = 'info', actionLabel, onAction }: EmptyStateProps) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <Icon name={icon} size={40} color={colors.textMuted} />
      <AppText align="center">{text}</AppText>
      {actionLabel && onAction ? (
        <BigButton label={actionLabel} variant="primary" size={56} onPress={onAction} />
      ) : null}
    </View>
  );
}

export interface ErrorStateProps {
  error: ApiError;
  onRetry?(): void;
  onSaveLater?(): void;
  onCall211?(): void;
  onTrySample?(): void;
}

/** Which callback is the primary action for this error (PRODUCT_SPEC §5.4 table). */
export function primaryErrorAction(error: ApiError): 'retry' | 'sample' | 'none' {
  switch (error.code) {
    case 'unpaid_tier_real_documents_disabled':
    case 'provider_not_configured':
      return 'sample';
    case 'unauthorized':
    case 'not_found':
    case 'too_many_pages':
    case 'pdf_too_long':
    case 'payload_too_large':
    case 'unsupported_media_type':
    case 'pack_version_mismatch':
      return 'none';
    default:
      return 'retry';
  }
}

/** The pack key to render: the server's key when the pack knows it, else `err.<code>`, else internal. */
export function errorCopyKey(error: ApiError): string {
  if (keyExists(error.userMessageKey)) return error.userMessageKey;
  if (keyExists(`err.${error.code}`)) return `err.${error.code}`;
  return 'err.internal';
}

/** Seconds left until `seconds` from mount have passed (informational; the caller keys the
 *  component per error so a new error restarts the count). */
function useCountdown(seconds: number | null): number | null {
  const [deadline] = useState(() => (seconds ? Date.now() + seconds * 1000 : null));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return;
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= deadline) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [deadline]);
  if (!deadline) return null;
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

export function ErrorState(props: ErrorStateProps) {
  const e = props.error;
  return <ErrorStateBody key={`${e.code}|${e.requestId ?? ''}|${e.retryAfterSeconds ?? ''}`} {...props} />;
}

function ErrorStateBody({ error, onRetry, onSaveLater, onCall211, onTrySample }: ErrorStateProps) {
  const t = useT();
  const { colors } = useTheme();
  const limits = useSession((s) => s.serverConfig?.limits ?? null);
  // `err.ai_too_slow` (a local test model): a retry takes as long again, so no countdown invites
  // one, although the 503 envelope still carries the §0.1 default Retry-After.
  const left = useCountdown(error.userMessageKey === 'err.ai_too_slow' ? null : error.retryAfterSeconds);
  const vars = errorMessageVars(error, limits);
  if (left !== null) vars.minutes = Math.max(1, Math.ceil(left / 60));
  const primary = primaryErrorAction(error);
  const retryLabel =
    left && left > 0
      ? `${t('btn.retry')} (${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')})`
      : t('btn.retry');
  return (
    <View role="alert" style={styles.wrap}>
      <Icon name="alert" size={40} color={colors.warning} />
      <AppText align="center">{t(errorCopyKey(error), vars)}</AppText>
      {primary === 'retry' && onRetry ? (
        <BigButton label={retryLabel} icon="refresh" variant="primary" size={56} onPress={onRetry} />
      ) : null}
      {primary === 'sample' && onTrySample ? (
        <BigButton label={t('btn.try_sample')} icon="sample" variant="primary" size={56} onPress={onTrySample} />
      ) : null}
      {onSaveLater && error.code !== 'unpaid_tier_real_documents_disabled' ? (
        <BigButton label={t('btn.save_to_read_later')} variant="secondary" size={56} onPress={onSaveLater} />
      ) : null}
      {onCall211 && (error.isQuotaExhausted() || error.code === 'upstream_unavailable') ? (
        <BigButton label={t('btn.call_211')} icon="phone" variant="secondary" size={56} onPress={onCall211} />
      ) : null}
      {onTrySample && primary !== 'sample' ? (
        <BigButton label={t('btn.try_sample')} icon="sample" variant="secondary" size={56} onPress={onTrySample} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    gap: space.lg,
    padding: space.xl,
  },
});
