// One short line after "Remind me" that the calling screen does not show itself ("This date has
// already passed", the sample-dates note). Native: an Alert. Web: `Alert.alert` is a no-op in
// react-native-web and `announceForAccessibility` too, so a small status box is added to the page
// (`role="status"`, filled after insertion so screen readers read it), removed after a few seconds
// or on tap. Colours are the light palette's text/background swapped (16.5:1), with a light border
// so the box stands out in the dark scheme too.

import { Alert } from 'react-native';

import { palette } from '@/design/tokens';
import { webDocument } from '@/lib/platform';

export const WEB_NOTICE_ID = 'ph-reminder-notice';
export const WEB_NOTICE_MS = 8000;

export function showWebNotice(message: string, doc: Document | null = webDocument()): HTMLElement | null {
  if (!doc?.body) return null;
  doc.getElementById(WEB_NOTICE_ID)?.remove();
  const box = doc.createElement('div');
  box.id = WEB_NOTICE_ID;
  box.setAttribute('role', 'status');
  box.setAttribute('aria-live', 'polite');
  box.setAttribute('dir', 'auto');
  Object.assign(box.style, {
    position: 'fixed',
    left: '16px',
    right: '16px',
    bottom: '24px',
    margin: '0 auto',
    maxWidth: '560px',
    boxSizing: 'border-box',
    padding: '14px 16px',
    borderRadius: '12px',
    border: `2px solid ${palette.light.background}`,
    background: palette.light.text,
    color: palette.light.background,
    fontFamily: 'var(--font-body, system-ui, sans-serif)',
    fontSize: '18px',
    lineHeight: '26px',
    textAlign: 'center',
    zIndex: '2147483647',
    cursor: 'pointer',
  });
  const remove = () => box.remove();
  box.addEventListener('click', remove);
  doc.body.appendChild(box);
  // Live regions announce changes, not the text they were inserted with.
  setTimeout(() => {
    box.textContent = message;
  }, 50);
  setTimeout(remove, WEB_NOTICE_MS);
  return box;
}

/** Shows `message` visibly on the current platform. `title`/`close` are already translated. */
export function showNotice(message: string, opts: { isWeb: boolean; title: string; close: string }): void {
  if (opts.isWeb) {
    showWebNotice(message);
    return;
  }
  try {
    Alert.alert(opts.title, message, [{ text: opts.close }]);
  } catch {
    // no native alert available (tests): nothing else to show
  }
}
