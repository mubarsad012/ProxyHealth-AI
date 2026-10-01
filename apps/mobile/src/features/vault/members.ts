// Family members (PRODUCT_SPEC §9.2–§9.3, D-24): "Me" (id `me`, created on the first save, never
// deletable, renamable) plus people the user adds with a name (≤ 40 chars), one of 8 colours and
// auto initials. Helpers only (the two copy helpers read `Platform.OS`); the vault stores the rows.

import { Platform } from 'react-native';

import type { Member } from '@/storage/index';
import { ME_MEMBER_ID } from '@/storage/rows';

import { nativeOnlyClaimUnsafe } from './platformCopy';

export { ME_MEMBER_ID };

export const MEMBER_NAME_MAX = 40;

/** Eight swatches, each ≥ 4.5:1 against white so white initials stay readable. */
export const MEMBER_COLORS = [
  '#0B4F8A',
  '#A61B1B',
  '#175E33',
  '#8A5200',
  '#6B2FA0',
  '#00616B',
  '#A1285E',
  '#3E4C5A',
] as const;

type Translate = (key: string, vars?: Record<string, string | number>) => string;

/** Up to two letters from the first two words; scripts without case keep their first character. */
export function initials(name: string): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 0);
  if (words.length === 0) return '';
  const first = (w: string) => Array.from(w)[0] ?? '';
  const letters = words.length === 1 ? first(words[0]) : first(words[0]) + first(words[words.length - 1]);
  return letters.toLocaleUpperCase();
}

export function isMe(memberId: string | null | undefined): boolean {
  return memberId === ME_MEMBER_ID;
}

/** Display name: the member's name, or "Me" for the unnamed default member. */
export function memberName(member: Pick<Member, 'id' | 'name'> | null | undefined, t: Translate): string {
  if (!member) return t('vault.me');
  const name = member.name.trim();
  if (name) return name;
  return isMe(member.id) ? t('vault.me') : '';
}

/** "Me" first (even before its row exists), then everyone else by creation time. */
export function withMe(members: Member[]): Member[] {
  const me = members.find((m) => isMe(m.id)) ?? {
    id: ME_MEMBER_ID,
    name: '',
    color: MEMBER_COLORS[0],
    createdAt: '',
  };
  const others = members
    .filter((m) => !isMe(m.id))
    .sort((a, b) => (a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0));
  return [me, ...others];
}

export function cleanMemberName(name: string): string {
  return name.replace(/\s+/g, ' ').trim().slice(0, MEMBER_NAME_MAX);
}

/** A colour no one uses yet (falls back to cycling the palette). */
export function nextColor(members: Pick<Member, 'color'>[]): string {
  const used = new Set(members.map((m) => m.color));
  return MEMBER_COLORS.find((c) => !used.has(c)) ?? MEMBER_COLORS[members.length % MEMBER_COLORS.length];
}

/** S12/S13 empty-state line that is literally true per platform (§9.5): web `vault.empty.web`
 *  (CL-042); iOS the D-22 interim line until the vault is excluded from iCloud Backup
 *  (COMPLIANCE_PRIVACY §10.2 — `vault.empty` says "stay only on this phone"); Android `vault.empty`. */
export function emptyVaultText(t: Translate, os: string = Platform.OS): string {
  if (os === 'web') return t('vault.empty.web');
  if (nativeOnlyClaimUnsafe(os)) return t('vault.privacy_native');
  return t('vault.empty');
}

/** "Saved…" announcement after a save: `vault.saved` says "on this phone", so web announces only
 *  `vault.saved_to` (CL-042). */
export function savedAnnouncement(t: Translate, member: string): string {
  const to = t('vault.saved_to', { member });
  return Platform.OS === 'web' ? to : `${t('vault.saved')} ${to}`;
}
