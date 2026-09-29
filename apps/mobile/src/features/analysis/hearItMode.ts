// Hear-it mode (PRODUCT_SPEC S7 item 18 `btn.read_all`; settings.hearItMode auto-plays on open):
// the result read aloud card by card in the fixed S7 order, with the emergency card first when
// triggered. Verbatim values are read as printed; unverified items are not read as facts.

import type { AnalysisResult } from '@/api/types';
import type { SpeechItem } from '@/features/speech/sequential';
import type { TFunction } from '@/i18n/useT';

import { disclaimerKey } from './disclaimers';
import { redFlagText, sortRedFlags } from './cards/SafetyCards';
import { urgencySpeech } from './urgencyCopy';

export function hearItItems(a: AnalysisResult, t: TFunction, uiTag: string, emergency: boolean): SpeechItem[] {
  const lang = uiTag;
  const items: SpeechItem[] = [];
  if (emergency) {
    items.push({
      id: 'emergency',
      lang,
      text: [t('emergency.title'), t('emergency.911'), t('emergency.988'), t('emergency.poison'), t('emergency.dv')].join(' '),
    });
  }
  if (a.scam_risk === 'likely' || a.scam_risk === 'possible') {
    items.push({ id: 'scam', lang, text: t(a.scam_risk === 'likely' ? 'scam.card.likely' : 'scam.card.possible') });
  }
  items.push({ id: 'urgency', lang, text: urgencySpeech(a.urgency, t) });
  const disc = disclaimerKey(a.disclaimer_kind);
  if (disc) items.push({ id: 'disclaimer', lang, text: t(disc) });
  items.push({ id: 'summary', lang, text: `${t('card.what_is_this')}. ${a.summary.title}. ${a.summary.body}` });
  const demands = a.demands.filter((d) => d.verified);
  items.push({
    id: 'demands',
    lang,
    text: demands.length
      ? `${t('card.asking_for')}. ${demands.map((d) => `${d.text} ${d.value_verbatim}`).join('. ')}`
      : t('card.asking_nothing'),
  });
  if (a.plan_steps.length) {
    items.push({
      id: 'plan',
      lang,
      text: `${t('card.plan')}. ${a.plan_steps.map((s, i) => `${i + 1}. ${s.text}`).join(' ')}`,
    });
  }
  if (a.red_flags.length) {
    items.push({ id: 'red_flags', lang, text: `${t('card.red_flags')}. ${sortRedFlags(a.red_flags).map((f) => redFlagText(f, t)).join('. ')}` });
  }
  items.push({ id: 'footer', lang, text: `${t('footer.ai_generated')} ${t('footer.verify_with_sender')}` });
  return items;
}
