// S14 — Reminders (PRODUCT_SPEC S14, §10.3). Grouped by paper with member dot, demand text, the
// printed value in <Bidi> + localized line, one on/off switch per reminder ("Passed" when past),
// "Add my own date", the lock-screen detail toggle, permission-denied and clock-skew notices.
// Web: explanation + "Add to calendar (.ics)" per paper and "Add all to calendar" (events are
// prepared ahead so the download runs inside the tap). Native: the same .ics via the share sheet.

import { useEffect, useMemo, useState } from 'react';
import { AccessibilityInfo, Platform, StyleSheet, View } from 'react-native';

import { useServerConfig } from '@/api/config';
import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { Screen } from '@/design/components/Screen';
import { SwitchRow } from '@/design/components/SettingsRows';
import { EmptyState } from '@/design/components/States';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useAllReminders, useMembers } from '@/features/vault/hooks';
import { memberName } from '@/features/vault/members';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { IcsEvent } from '@/lib/ics';
import { type NotificationPermission, notifications } from '@/lib/notifications';
import type { StoredDocument } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';
import { useSettings } from '@/store/settings';

import { formatDay, formatFireTime } from './format';
import { allReminders, groupReminderList, groupReminders, OWN_GROUP_KEY, type PaperGroup } from './groups';
import { OwnDateForm } from './OwnDateForm';
import { useReminders } from './useReminders';

const CLOCK_SKEW_MS = 24 * 60 * 60 * 1000;
const isWeb = Platform.OS === 'web';

function useDocs(documentIds: string[]): Map<string, StoredDocument | null> {
  const vault = useVault();
  const [docs, setDocs] = useState<Map<string, StoredDocument | null>>(new Map());
  const key = documentIds.join(',');
  useEffect(() => {
    let cancelled = false;
    void Promise.all(documentIds.map(async (id) => [id, await vault.documents.get(id).catch(() => null)] as const)).then(
      (entries) => {
        if (!cancelled) setDocs(new Map(entries));
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vault, key]);
  return docs;
}

function Notice({ text, tone }: { text: string; tone: 'warning' | 'info' }) {
  const { colors } = useTheme();
  return (
    <View role="status" style={[styles.notice, { borderColor: tone === 'warning' ? colors.warning : colors.divider }]}>
      <AppText variant="caption" weight={tone === 'warning' ? 'bold' : 'regular'}>
        {text}
      </AppText>
    </View>
  );
}

export function RemindersScreen({ focusDocumentId }: { focusDocumentId?: string | null }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const api = useReminders();
  const tag = useSettings((s) => s.languageTag);
  const lockScreenDetail = useSettings((s) => s.lockScreenDetail);
  const setSetting = useSettings((s) => s.set);
  const { config, cached } = useServerConfig();
  const { reminders, loading } = useAllReminders();
  const { members } = useMembers();
  const docIds = useMemo(
    () => [...new Set(reminders.map((r) => r.documentId).filter((id) => id.length > 0))].sort(),
    [reminders],
  );
  const docs = useDocs(docIds);
  const groups = useMemo(() => groupReminders(reminders, docs, focusDocumentId), [reminders, docs, focusDocumentId]);
  const [permission, setPermission] = useState<NotificationPermission>('unavailable');
  const [adding, setAdding] = useState(false);
  const [prepared, setPrepared] = useState<Record<string, IcsEvent[]>>({});
  const [clock, setClock] = useState<{ now: number; skewed: boolean }>({ now: 0, skewed: false });

  useEffect(() => {
    if (isWeb) return;
    void notifications.getPermission().then(setPermission);
  }, [reminders]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const out: Record<string, IcsEvent[]> = { all: await api.icsEventsFor(allReminders(groups)) };
      for (const g of groups) out[g.key] = await api.icsEventsFor(groupReminderList(g));
      if (cancelled) return;
      setPrepared(out);
      const now = Date.now();
      const serverTime = config?.server_time ? Date.parse(config.server_time) : NaN;
      // Only a fresh /v1/config answer can say the phone's clock is off (a cached one is old).
      const skewed = !cached && Number.isFinite(serverTime) && Math.abs(now - serverTime) > CLOCK_SKEW_MS;
      setClock({ now, skewed });
    })();
    return () => {
      cancelled = true;
    };
  }, [api, groups, config, cached]);

  const clockWrong = clock.skewed;
  const now = clock.now;

  const renderGroup = (g: PaperGroup) => {
    const member = g.memberId ? members.find((m) => m.id === g.memberId) : undefined;
    const events = prepared[g.key] ?? [];
    return (
      <View key={g.key} testID={`reminder-group-${g.key}`} style={[styles.group, { borderColor: colors.divider }]}>
        <View style={[styles.inline, { flexDirection: dir.row }]}>
          {member ? <View style={[styles.dot, { backgroundColor: member.color }]} /> : null}
          <View style={styles.flex}>
            <Heading level={2}>{g.key === OWN_GROUP_KEY ? t('reminders.own_group') : g.title}</Heading>
            {member ? <AppText variant="caption">{memberName(member, t)}</AppText> : null}
          </View>
        </View>
        {g.items.map((item) => (
          <View key={item.key} style={styles.item}>
            <AppText weight="bold">{item.text}</AppText>
            {item.verbatim ? <Bidi dir="ltr" variant="bodyLarge" weight="bold">{item.verbatim}</Bidi> : null}
            {!item.verbatim && item.eventDate ? <AppText>{formatDay(item.eventDate, tag)}</AppText> : null}
            {item.localizedLine ? <AppText color="textMuted">{item.localizedLine}</AppText> : null}
            {item.reminders.map((r) => {
              const past = Date.parse(r.fireAt) <= now;
              const label = `${t('reminders.fires_on', { date: formatFireTime(r.fireAt, tag) })} · ${
                past ? t('reminders.past') : r.enabled ? t('reminders.on') : t('reminders.off')
              }`;
              return (
                <View key={r.id} style={{ opacity: past ? 0.55 : 1 }}>
                  <SwitchRow
                    testID={`reminder-toggle-${r.id}`}
                    label={label}
                    value={r.enabled && !past}
                    disabled={past}
                    onChange={(on) => void api.setEnabled(r, on)}
                  />
                </View>
              );
            })}
          </View>
        ))}
        {events.length > 0 ? (
          <BigButton
            testID={`reminder-ics-${g.key}`}
            label={isWeb ? t('btn.download_ics') : t('btn.add_to_calendar')}
            icon="calendar"
            variant="secondary"
            size={56}
            onPress={() => void api.offerPrepared(events)}
          />
        ) : null}
      </View>
    );
  };

  return (
    <Screen title={t('btn.reminders')} back testID="reminders-screen">
      <SwitchRow
        testID="reminders-lockscreen"
        label={t('reminders.lockscreen_detail')}
        explanation={t('reminders.lockscreen_explain')}
        value={lockScreenDetail}
        onChange={(v) => setSetting('lockScreenDetail', v)}
      />
      {isWeb ? <Notice tone="info" text={t('reminders.web_explain')} /> : null}
      {!isWeb && permission === 'denied' ? (
        <View style={styles.item}>
          <Notice tone="warning" text={t('reminders.permission_denied')} />
          <BigButton label={t('btn.open_settings')} icon="settings" variant="secondary" size={56} onPress={() => void notifications.openSettings()} />
        </View>
      ) : null}
      {clockWrong ? <Notice tone="warning" text={t('reminders.clock_warning')} /> : null}
      {isWeb && (prepared.all ?? []).length > 1 ? (
        <BigButton
          testID="reminders-ics-all"
          label={t('btn.download_all_ics')}
          icon="calendar"
          variant="secondary"
          size={56}
          onPress={() => void api.offerPrepared(prepared.all ?? [])}
        />
      ) : null}
      {!loading && groups.length === 0 && !adding ? <EmptyState icon="calendar" text={t('reminders.empty')} /> : null}
      {groups.map(renderGroup)}
      {adding ? (
        <OwnDateForm
          onCancel={() => setAdding(false)}
          onSubmit={(input) => {
            const pending = api.addOwnDate(input);
            setAdding(false);
            void pending.then((outcome) => {
              if (outcome === 'not_eligible') return;
              try {
                AccessibilityInfo.announceForAccessibility(t('reminders.added', { date: formatDay(input.dateIso, tag) }));
              } catch {
                // best-effort
              }
            });
          }}
        />
      ) : (
        <BigButton
          testID="reminders-add-own"
          label={t('reminders.add_own')}
          icon="calendar-clock"
          variant="primary"
          size={72}
          onPress={() => setAdding(true)}
        />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  inline: {
    alignItems: 'center',
    gap: space.sm,
  },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 7,
  },
  group: {
    gap: space.md,
    paddingBottom: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  item: {
    gap: space.xs,
  },
  notice: {
    padding: space.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
});
