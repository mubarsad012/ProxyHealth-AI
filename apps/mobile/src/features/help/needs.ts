// Need tiles on the Get help tab (PRODUCT_SPEC S11): 56 pt, icon + word, each mapping to
// `ResourceTag`s for `POST /v1/resources/match`. "Someone is in danger" also opens S19.

import type { ResourceTag } from '@/api/types';
import type { IconName } from '@/design/components';

export interface NeedTile {
  id: string;
  /** Pack key for the tile word. */
  key: string;
  icon: IconName;
  tags: ResourceTag[];
  /** Opens the emergency card (S19) as well. */
  emergency?: boolean;
  scam?: boolean;
}

export const NEED_TILES: readonly NeedTile[] = [
  { id: 'legal', key: 'need.legal', icon: 'people', tags: ['immigration_legal_help'] },
  { id: 'court', key: 'need.court', icon: 'calendar', tags: ['court_notice', 'removal_proceedings'] },
  { id: 'medical_bill', key: 'need.medical_bill', icon: 'papers', tags: ['medical_bill', 'charity_care'] },
  { id: 'insurance', key: 'need.insurance', icon: 'papers', tags: ['insurance_denial', 'medicare_appeal'] },
  { id: 'clinic', key: 'need.clinic', icon: 'help', tags: ['primary_care_uninsured'] },
  { id: 'food', key: 'need.food', icon: 'home', tags: ['food', 'snap', 'wic', 'school_meals'] },
  { id: 'housing', key: 'need.housing', icon: 'home', tags: ['eviction', 'housing_counseling', 'rent_assistance'] },
  { id: 'utilities', key: 'need.utilities', icon: 'alert', tags: ['utility_shutoff'] },
  {
    id: 'benefits',
    key: 'need.benefits',
    icon: 'papers',
    tags: ['benefits_navigation', 'medicaid_renewal', 'ssa_benefits'],
  },
  {
    id: 'school',
    key: 'need.school',
    icon: 'people',
    tags: ['school_enrollment', 'special_education', 'homeless_students'],
  },
  {
    id: 'work',
    key: 'need.work',
    icon: 'people',
    tags: ['workers_rights', 'wage_theft', 'discrimination', 'workplace_safety'],
  },
  { id: 'tax', key: 'need.tax', icon: 'papers', tags: ['tax_notice', 'itin'] },
  { id: 'scam', key: 'need.scam', icon: 'flag', tags: ['scam_report'], scam: true },
  {
    id: 'crisis',
    key: 'need.crisis',
    icon: 'phone',
    tags: ['crisis', 'domestic_violence', 'trafficking'],
    emergency: true,
  },
  { id: 'interpreter', key: 'need.interpreter', icon: 'globe', tags: ['language_access'] },
];

export function needById(id: string | null | undefined): NeedTile | null {
  return NEED_TILES.find((n) => n.id === id) ?? null;
}

/** Tag groups used by `national_fallbacks` (RESOURCE_DB §3.1 / §6.9). */
export const IMMIGRATION_GROUP: ReadonlySet<ResourceTag> = new Set<ResourceTag>([
  'immigration_legal_help',
  'removal_proceedings',
  'asylum',
  'daca_tps',
  'work_permit',
  'green_card',
  'naturalization',
  'change_of_address',
  'fee_waiver',
  'afghan_specific',
  'refugee_services',
  'court_notice',
]);

export const HEALTH_GROUP: ReadonlySet<ResourceTag> = new Set<ResourceTag>([
  'medical_bill',
  'charity_care',
  'insurance_denial',
  'medicare_appeal',
  'medicaid_renewal',
  'prescription_help',
  'primary_care_uninsured',
  'lab_results',
  'vaccine_records',
]);
