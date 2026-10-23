// Hear-it mode (PRODUCT_SPEC S7 item 18 `btn.read_all`; settings.hearItMode auto-plays on open):
// the result read aloud card by card in the fixed S7 order, with the emergency card first when
// triggered. Verbatim values are read as printed; unverified items are not read as facts.
// Each part is read in the language it is written in (D-26): fixed copy (headings, banners,
// disclaimers, fixed red-flag notices) in the UI pack, the model's text (summary, demands, plan,
// model red flags) in `analysis.target_language` — the S5 output-language chip can make the two
// differ. Adjacent parts in the same language are read as one item, as before the chip.

import type { AnalysisResult } from '@/api/types';
import { digitGroupedForSpeech } from '@/features/emergency/EmergencyCard';
import type { SpeechItem } from '@/features/speech/sequential';
import type { TFunction } from '@/i18n/useT';

import { disclaimerKey, footerKeys } from './disclaimers';
import { redFlagIsFixedCopy, redFlagText, sortRedFlags } from './cards/SafetyCards';
import { localizeUrgencyDate } from './estimatedDate';
import { urgencySpeech } from './urgencyCopy';

interface Part {
  lang: string;
  text: string;
}

/** One card's parts as speech items: adjacent same-language parts joined with ". ". */
function cardItems(id: string, parts: Part[]): SpeechItem[] {
  const items: SpeechItem[] = [];
  for (const p of parts) {
    const last = items[items.length - 1];
    if (last && last.lang === p.lang) last.text = `${last.text}. ${p.text}`;
    else items.push({ id, lang: p.lang, text: p.text });
  }
  return items;
}

/** The language the model's text in `a` is written in (the S5 chip), else the UI pack. */
export function paperSpeechLang(a: AnalysisResult, uiTag: string): string {
  return a.target_language || uiTag;
}

export function hearItItems(a: AnalysisResult, t: TFunction, uiTag: string, emergency: boolean): SpeechItem[] {
  const ui = uiTag;
  const paper = paperSpeechLang(a, uiTag);
  const items: SpeechItem[] = [];
  if (emergency) {
    items.push({
      id: 'emergency',
      lang: ui,
      // Numbers digit-grouped, as on S19 ("9 1 1", "1, 8 0 0, 2 2 2, 1 2 2 2").
      text: digitGroupedForSpeech(
        [t('emergency.title'), t('emergency.911'), t('emergency.988'), t('emergency.poison'), t('emergency.dv')].join(' '),
      ),
    });
  }
  if (a.scam_risk === 'likely' || a.scam_risk === 'possible') {
    items.push({ id: 'scam', lang: ui, text: t(a.scam_risk === 'likely' ? 'scam.card.likely' : 'scam.card.possible') });
  }
  // An estimated headline's `{date}` is ISO on the wire (CL-080(d)); read it as the banner shows it.
  items.push({ id: 'urgency', lang: ui, text: urgencySpeech(localizeUrgencyDate(a.urgency), t) });
  const disc = disclaimerKey(a.disclaimer_kind);
  if (disc) items.push({ id: 'disclaimer', lang: ui, text: t(disc) });
  items.push(
    ...cardItems('summary', [
      { lang: ui, text: t('card.what_is_this') },
      { lang: paper, text: `${a.summary.title}. ${a.summary.body}` },
    ]),
  );
  const demands = a.demands.filter((d) => d.verified);
  items.push(
    ...(demands.length
      ? cardItems('demands', [
          { lang: ui, text: t('card.asking_for') },
          { lang: paper, text: demands.map((d) => `${d.text} ${d.value_verbatim}`).join('. ') },
        ])
      : [{ id: 'demands', lang: ui, text: t('card.asking_nothing') }]),
  );
  if (a.plan_steps.length) {
    items.push(
      ...cardItems('plan', [
        { lang: ui, text: t('card.plan') },
        { lang: paper, text: a.plan_steps.map((s, i) => `${i + 1}. ${s.text}`).join(' ') },
      ]),
    );
  }
  if (a.red_flags.length) {
    items.push(
      ...cardItems('red_flags', [
        { lang: ui, text: t('card.red_flags') },
        ...sortRedFlags(a.red_flags).map((f) => ({ lang: redFlagIsFixedCopy(f) ? ui : paper, text: redFlagText(f, t) })),
      ]),
    );
  }
  items.push({ id: 'footer', lang: ui, text: footerKeys(a).map((k) => t(k)).join(' ') });
  return items;
}
