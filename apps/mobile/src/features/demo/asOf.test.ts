// The sample papers' fixed "today" on the client must be the server's DEMO_AS_OF and the day the
// `demo.as_of_note` line names; `sampleNow` keeps the time of day and moves only the calendar day.

import { DEMO_AS_OF_ISO, DEMO_AS_OF_NOTE, isSampleAnalysis, sampleNow } from './asOf';

// No Node types in this app's tsconfig: read files through jest like design/focus.test.ts.
function readRepoFile(fromApps: string): string {
  const fs = jest.requireActual<{ readFileSync(path: string, enc: 'utf8'): string }>('fs');
  const testPath = expect.getState().testPath ?? '';
  const apps = testPath.replace(/mobile[\\/]src[\\/]features[\\/]demo[\\/]asOf\.test\.ts$/, '');
  return fs.readFileSync(`${apps}${fromApps}`, 'utf8');
}

describe('sample as-of day', () => {
  it('matches apps/api/proxyhealth_api/demo/as_of.py and the English note', () => {
    const py = readRepoFile('api/proxyhealth_api/demo/as_of.py');
    const m = /^DEMO_AS_OF = date\((\d{4}), (\d{1,2}), (\d{1,2})\)/m.exec(py);
    expect(m).not.toBeNull();
    const [, y, mo, d] = m as RegExpExecArray;
    expect(DEMO_AS_OF_ISO).toBe(`${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`);
    const en = JSON.parse(readRepoFile('mobile/src/i18n/packs/en.json')) as Record<string, string>;
    const named = new Date(Number(y), Number(mo) - 1, Number(d)).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
    expect(en[DEMO_AS_OF_NOTE]).toContain(named);
  });

  it('sampleNow keeps the local time of day on the as-of day', () => {
    const at = sampleNow(new Date(2026, 9, 22, 15, 30, 5, 7));
    expect([at.getFullYear(), at.getMonth() + 1, at.getDate()]).toEqual([2026, 10, 2]);
    expect([at.getHours(), at.getMinutes(), at.getSeconds(), at.getMilliseconds()]).toEqual([15, 30, 5, 7]);
  });

  it('detects a sample by the demo_sample warning or model_meta.demo', () => {
    expect(isSampleAnalysis({ warnings: ['demo_sample'], model_meta: { demo: false } } as never)).toBe(true);
    expect(isSampleAnalysis({ warnings: [], model_meta: { demo: true } } as never)).toBe(true);
    expect(isSampleAnalysis({ warnings: [], model_meta: { demo: false } } as never)).toBe(false);
    expect(isSampleAnalysis(null)).toBe(false);
  });
});
