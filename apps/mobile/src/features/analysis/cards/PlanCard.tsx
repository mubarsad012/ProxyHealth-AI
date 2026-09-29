// Card 3 — "Your step-by-step plan" (PRODUCT_SPEC S7 item 10): checklist of `plan_steps[]` with a
// kind icon per step and "Find help for this →" when a step carries resource tags. Checkbox state
// lives in the session until the paper is saved (then `vault.checklist`, WP6).

import { Pressable, StyleSheet, View } from 'react-native';
import { create } from 'zustand';

import { Checklist } from '@/design/components/Checklist';
import { Card } from '@/design/components/Card';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

import { PLAN_ICONS, type ResultCardProps } from './shared';

interface ChecklistSession {
  byAnalysis: Record<string, Record<string, boolean>>;
  set(analysisId: string, stepId: string, checked: boolean): void;
}

/** Memory-only checkbox state per analysis (cleared with the session). */
export const usePlanChecks = create<ChecklistSession>()((set) => ({
  byAnalysis: {},
  set: (analysisId, stepId, checked) =>
    set((s) => ({
      byAnalysis: { ...s.byAnalysis, [analysisId]: { ...(s.byAnalysis[analysisId] ?? {}), [stepId]: checked } },
    })),
}));

const EMPTY: Record<string, boolean> = {};

export function PlanCard({ analysis, handlers }: ResultCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const state = usePlanChecks((s) => s.byAnalysis[analysis.analysis_id] ?? EMPTY);
  const setCheck = usePlanChecks((s) => s.set);
  const steps = analysis.plan_steps;
  if (!steps.length) return null;
  return (
    <Card
      id="card-plan"
      headingKey="card.plan"
      lang={analysis.target_language}
      speakText={steps.map((s, i) => `${i + 1}. ${s.text}`).join(' ')}>
      {steps.map((step) => (
        <View key={step.id} testID={`plan-${step.id}`} style={styles.step}>
          <View style={[styles.row, { flexDirection: dir.row }]}>
            <Icon name={PLAN_ICONS[step.kind]} color={colors.primary} />
            <View style={styles.flex}>
              <Checklist
                items={[{ id: step.id, text: step.text }]}
                state={state}
                onToggle={(id, checked) => setCheck(analysis.analysis_id, id, checked)}
              />
            </View>
          </View>
          {step.resource_tags.length && handlers.onFindHelp ? (
            <Pressable
              role="button"
              accessibilityLabel={t('plan.find_help')}
              hitSlop={size.hitSlop}
              onPress={() => handlers.onFindHelp?.(step.resource_tags)}
              style={[styles.help, { alignSelf: dir.alignStart }]}>
              <AppText color="link" weight="bold">
                {t('plan.find_help')}
              </AppText>
            </Pressable>
          ) : null}
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  step: {
    gap: space.xs,
  },
  row: {
    gap: space.sm,
    alignItems: 'center',
  },
  flex: {
    flex: 1,
  },
  help: {
    minHeight: size.minTouch,
    justifyContent: 'center',
  },
});
