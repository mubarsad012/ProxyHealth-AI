// Privacy copy that must be literally true on the platform it is shown on (PRODUCT_SPEC §9.5,
// COMPLIANCE_PRIVACY §10.2 / §17, D-22, D-23).
//
//   • Web keeps papers in this browser, not "on this phone": `<key>.web` variants (CL-047(a)).
//   • iOS: saved papers live under the app's Documents folder (expo-sqlite `Documents/SQLite`,
//     page JPEGs in `Paths.document/vault`), which iCloud Backup copies by default. Until the vault
//     is verifiably excluded from backup (COMPLIANCE_PRIVACY §10.2 gate, Q16), iOS never says papers
//     stay "only" on this phone; it shows the D-22 interim copy (`vault.privacy_native`).
//   • Android: `android.allowBackup: false`, so "stay only on this phone" is true.

import { Platform } from 'react-native';

import { keyExists } from '@/i18n/store';

type Translate = (key: string, vars?: Record<string, string | number>) => string;

/**
 * Flip to true only once a dev build has verified `NSURLIsExcludedFromBackupKey` on the vault
 * directory and the SQLite folder (COMPLIANCE_PRIVACY §10.2; recorded in the RUNBOOK).
 */
export const IOS_VAULT_BACKUP_EXCLUDED = false;

/** True where "Papers you save stay only on this phone" would not be literally true on native. */
export function nativeOnlyClaimUnsafe(os: string = Platform.OS): boolean {
  return os === 'ios' && !IOS_VAULT_BACKUP_EXCLUDED;
}

/**
 * `<key>.web` on web, else `key`. The web key is used whenever the active pack or the English base
 * has it (an English web sentence beats a translated one that says "on this phone"); only if it is
 * missing everywhere does the native key show, so a raw key never reaches the screen.
 */
export function platformKey(key: string, os: string = Platform.OS): string {
  if (os !== 'web') return key;
  const web = `${key}.web`;
  return keyExists(web) ? web : key;
}

/** `t(platformKey(key))`. */
export function platformText(t: Translate, key: string, vars?: Record<string, string | number>, os: string = Platform.OS): string {
  return t(platformKey(key, os), vars);
}

/** S3 trust footer: web → `home.trust_footer.web`; iOS → server line + the D-22 interim line. */
export function trustFooterText(t: Translate, os: string = Platform.OS): string {
  if (os === 'web') return t('home.trust_footer.web');
  if (nativeOnlyClaimUnsafe(os)) return `${t('vault.privacy_server')} ${t('vault.privacy_native')}`;
  return t('home.trust_footer');
}
