// Bottom sheet + confirm dialog used by the vault, reminders, sample picker and settings flows.
// RN `Modal` works on iOS, Android and web (react-native-web portals it to <body>); Alert.alert is
// a no-op on web, so every confirmation in WP6 uses `ConfirmDialog` instead. Scrollable body,
// 56 pt close button, mirrored rows, `role="dialog"` with the title as its label.

import type { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

export interface SheetProps {
  visible: boolean;
  title: string;
  onClose(): void;
  children: ReactNode;
  /** Sticky actions under the scrolling body. */
  footer?: ReactNode;
  testID?: string;
}

export function Sheet({ visible, title, onClose, children, footer, testID }: SheetProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
        <View
          testID={testID}
          role="dialog"
          aria-modal
          accessibilityLabel={title}
          style={[
            styles.panel,
            { backgroundColor: colors.background, borderColor: colors.divider, paddingBottom: space.lg + insets.bottom },
          ]}>
          <View style={[styles.header, { flexDirection: dir.row }]}>
            <View style={styles.flex}>
              <Heading level={2}>{title}</Heading>
            </View>
            <Pressable
              role="button"
              accessibilityLabel={t('btn.close')}
              hitSlop={size.hitSlop}
              onPress={onClose}
              style={styles.close}>
              <Icon name="close" color={colors.text} />
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            {children}
          </ScrollView>
          {footer ? <View style={styles.footer}>{footer}</View> : null}
        </View>
      </View>
    </Modal>
  );
}

export interface ConfirmDialogProps {
  visible: boolean;
  title: string;
  body?: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm(): void;
  onCancel(): void;
  testID?: string;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  const { visible, title, body, confirmLabel, cancelLabel, danger, busy, onConfirm, onCancel, testID } = props;
  return (
    <Sheet
      visible={visible}
      title={title}
      onClose={onCancel}
      testID={testID}
      footer={
        <View style={styles.actions}>
          <BigButton
            testID={testID ? `${testID}-confirm` : undefined}
            label={confirmLabel}
            variant={danger ? 'danger' : 'primary'}
            size={56}
            disabled={busy}
            onPress={onConfirm}
          />
          <BigButton label={cancelLabel} variant="secondary" size={56} disabled={busy} onPress={onCancel} />
        </View>
      }>
      {body ? <AppText>{body}</AppText> : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  panel: {
    maxHeight: '92%',
    width: '100%',
    maxWidth: 720,
    alignSelf: 'center',
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingTop: space.md,
  },
  header: {
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.screenGutter,
    minHeight: size.button,
  },
  flex: {
    flex: 1,
  },
  close: {
    width: size.minTouch,
    height: size.minTouch,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: {
    gap: space.lg,
    paddingHorizontal: space.screenGutter,
    paddingVertical: space.md,
  },
  footer: {
    paddingHorizontal: space.screenGutter,
    paddingTop: space.sm,
  },
  actions: {
    gap: space.sm,
  },
});
