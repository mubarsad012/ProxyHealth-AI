/**
 * @jest-environment jsdom
 */
// The web line after "Remind me" (react-native-web's Alert and announceForAccessibility do nothing):
// a status box that is filled after insertion, replaces an earlier one and goes away by itself.

import { showWebNotice, WEB_NOTICE_ID, WEB_NOTICE_MS } from './notice';

describe('showWebNotice', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.useRealTimers();
    document.body.innerHTML = '';
  });

  it('adds one status box with the message, then removes it', () => {
    showWebNotice('first', document);
    const box = showWebNotice('second', document);
    expect(document.querySelectorAll(`#${WEB_NOTICE_ID}`)).toHaveLength(1);
    expect(box?.getAttribute('role')).toBe('status');
    expect(box?.getAttribute('aria-live')).toBe('polite');
    jest.advanceTimersByTime(60);
    expect(document.getElementById(WEB_NOTICE_ID)?.textContent).toBe('second');
    jest.advanceTimersByTime(WEB_NOTICE_MS);
    expect(document.getElementById(WEB_NOTICE_ID)).toBeNull();
  });

  it('a tap dismisses it; no document → nothing happens', () => {
    const box = showWebNotice('hello', document);
    box?.click();
    expect(document.getElementById(WEB_NOTICE_ID)).toBeNull();
    expect(showWebNotice('x', null)).toBeNull();
  });
});
