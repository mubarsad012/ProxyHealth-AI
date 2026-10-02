// Every expo-image <Image> in app code must opt out of the default 'disk' cache, because the images it shows
// are photos of the user's own papers (privacy, D-22: nothing saved unless the user taps Save).
// Node built-ins are loaded with require so this file needs no @types/node (not in tsconfig "types").
declare const require: (id: string) => any;
declare const __dirname: string;
const fs = require('fs');
const path = require('path');

function files(dir: string): string[] {
  return (fs.readdirSync(dir) as string[]).flatMap((name: string) => {
    const p: string = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) return files(p);
    return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [p] : [];
  });
}

test('expo-image Image elements set cachePolicy (never the disk default)', () => {
  const src: string = path.join(__dirname, '..', '..');
  const offenders: string[] = [];
  for (const f of files(src)) {
    const text: string = fs.readFileSync(f, 'utf8');
    if (!text.includes("from 'expo-image'")) continue;
    const tags: string[] = text.match(/<Image\b[\s\S]*?\/>/g) ?? [];
    for (const tag of tags) {
      if (!/cachePolicy="(memory|none)"/.test(tag)) offenders.push(`${f}: ${tag.slice(0, 80)}`);
    }
  }
  expect(offenders).toEqual([]);
});
