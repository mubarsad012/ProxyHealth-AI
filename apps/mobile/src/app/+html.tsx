// Web HTML shell (static export; ARCHITECTURE §3 `+html.tsx`). Runs in Node at export time only:
// no browser APIs here. `lang`/`dir` start as English/LTR; `i18n/direction.ts` updates them from the
// active pack on the client. The RN-Web root is pinned LTR so `row-reverse` mirrors exactly once
// (global.css). Copy comes from the English base pack (the only pack available at export time).

import { ScrollViewStyleReset } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

import { BASE_STRINGS } from '@/i18n/store';

const s = (key: string) => BASE_STRINGS[key] ?? key;

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en" dir="ltr">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover" />
        <meta name="theme-color" content="#0B4F8A" />
        <meta name="description" content={`${s('app.name')} — ${s('app.tagline')}`} />
        <title>{s('app.name')}</title>
        <ScrollViewStyleReset />
      </head>
      <body>
        <noscript>{s('app.needs_javascript')}</noscript>
        {children}
      </body>
    </html>
  );
}
