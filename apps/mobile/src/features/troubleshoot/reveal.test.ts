/**
 * @jest-environment jsdom
 */
// S16 web: a new result is scrolled into view and its first heading takes focus without a second
// scroll; anything that is not a DOM node is left alone.

import { revealOnWeb } from './reveal';

describe('revealOnWeb', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('scrolls the result to the top of the view and focuses its first heading', () => {
    document.body.innerHTML =
      '<div id="r"><div role="status">Sample</div><div role="heading" aria-level="2">What this screen is</div><h2>Later</h2></div>';
    const result = document.getElementById('r') as HTMLElement;
    const scroll = jest.fn();
    result.scrollIntoView = scroll;
    expect(revealOnWeb(result, { smooth: true })).toBe(true);
    expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    const heading = result.querySelector('[role="heading"]') as HTMLElement;
    expect(document.activeElement).toBe(heading);
    expect(heading.getAttribute('tabindex')).toBe('-1');
  });

  it('does not animate with reduce motion and ignores non-DOM nodes', () => {
    document.body.innerHTML = '<div id="r"><p>No heading</p></div>';
    const result = document.getElementById('r') as HTMLElement;
    const scroll = jest.fn();
    result.scrollIntoView = scroll;
    revealOnWeb(result, { smooth: false });
    expect(scroll).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' });
    expect(revealOnWeb({}, { smooth: true })).toBe(false);
    expect(revealOnWeb(null, { smooth: true })).toBe(false);
  });
});
