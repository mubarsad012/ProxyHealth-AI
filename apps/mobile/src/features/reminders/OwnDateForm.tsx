// S14 "Add my own date" (PRODUCT_SPEC §10.2): title ≤ 60 chars, a date (month / day / year number
// boxes — no date-picker package is installed, and these work the same on iOS, Android and web),
// optional note ≤ 100 chars. Same schedule rules as a paper's date; stored without a document.

import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { AppText } from '@/design/components/Text';
import { useScaled, useTheme } from '@/design/theme';
import { radius, size, space, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

import { toIsoDay } from './schedule';
import { OWN_NOTE_MAX, OWN_TITLE_MAX, type OwnDateInput, validateOwnDate } from './service';

export interface OwnDateFormProps {
  /** Must call the reminders API synchronously (web downloads the .ics inside the tap). */
  onSubmit(input: OwnDateInput): void;
  onCancel(): void;
}

function digits(v: string, max: number): string {
  return v.replace(/\D/g, '').slice(0, max);
}

export function OwnDateForm({ onSubmit, onCancel }: OwnDateFormProps) {
  const t = useT();
  const { colors } = useTheme();
  const scaled = useScaled();
  const dir = useDirection();
  const [week] = useState(() => new Date(Date.now() + 7 * 24 * 60 * 60 * 1000));
  const [title, setTitle] = useState('');
  const [month, setMonth] = useState(String(week.getMonth() + 1));
  const [day, setDay] = useState(String(week.getDate()));
  const [year, setYear] = useState(String(week.getFullYear()));
  const [note, setNote] = useState('');
  const [error, setError] = useState<'title' | 'date' | null>(null);

  const inputStyle = [
    styles.input,
    { color: colors.text, borderColor: colors.border, fontSize: scaled(typeScale.size.body) },
  ];
  const submit = () => {
    const y = Number(year);
    const m = Number(month);
    const d = Number(day);
    const candidate = new Date(y, m - 1, d);
    const valid = candidate.getFullYear() === y && candidate.getMonth() === m - 1 && candidate.getDate() === d;
    const input: OwnDateInput = { title, dateIso: valid ? toIsoDay(candidate) : '', note };
    const check = valid ? validateOwnDate(input, new Date()) : 'date';
    if (check !== 'ok') {
      setError(check);
      return;
    }
    setError(null);
    onSubmit(input);
  };

  return (
    <View style={styles.form} testID="own-date-form">
      <AppText weight="bold">{t('reminders.own_title')}</AppText>
      <TextInput
        testID="own-date-title"
        value={title}
        onChangeText={(v) => setTitle(v.slice(0, OWN_TITLE_MAX))}
        maxLength={OWN_TITLE_MAX}
        accessibilityLabel={t('reminders.own_title')}
        style={[...inputStyle, { textAlign: dir.textAlign }]}
      />
      <View style={[styles.dateRow, { flexDirection: dir.row }]}>
        {(
          [
            ['reminders.month', month, setMonth, 2],
            ['reminders.day', day, setDay, 2],
            ['reminders.year', year, setYear, 4],
          ] as const
        ).map(([key, value, setter, max]) => (
          <View key={key} style={styles.datePart}>
            <AppText variant="caption">{t(key)}</AppText>
            <TextInput
              testID={`own-date-${key.split('.')[1]}`}
              value={value}
              onChangeText={(v) => setter(digits(v, max))}
              keyboardType="number-pad"
              maxLength={max}
              accessibilityLabel={t(key)}
              style={[...inputStyle, styles.center]}
            />
          </View>
        ))}
      </View>
      <AppText weight="bold">{t('reminders.own_note')}</AppText>
      <TextInput
        testID="own-date-note"
        value={note}
        onChangeText={(v) => setNote(v.slice(0, OWN_NOTE_MAX))}
        maxLength={OWN_NOTE_MAX}
        accessibilityLabel={t('reminders.own_note')}
        style={[...inputStyle, { textAlign: dir.textAlign }]}
      />
      {error ? (
        <View role="alert">
          <AppText color="danger" weight="bold">
            {error === 'date' ? t('reminders.bad_date') : t('reminders.own_title')}
          </AppText>
        </View>
      ) : null}
      <BigButton testID="own-date-save" label={t('btn.save')} icon="calendar" variant="primary" size={56} onPress={submit} />
      <BigButton label={t('btn.cancel')} variant="secondary" size={56} onPress={onCancel} />
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: space.sm,
  },
  input: {
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
  center: {
    textAlign: 'center',
  },
  dateRow: {
    gap: space.sm,
  },
  datePart: {
    flex: 1,
    gap: space.xxs,
  },
});
