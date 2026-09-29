// Design-system components (BUILD_PLAN §4.2 props; ARCHITECTURE §3 `design/components/`).
// Import from here: `import { BigButton, Card } from '@/design/components';`

export { AppProviders, type AppProvidersProps } from './Providers';
export { Banner, BANNER_KEYS, type BannerKind, type BannerProps } from './Banner';
export { BigButton, type BigButtonProps, type BigButtonVariant } from './BigButton';
export { Bidi, type BidiDir, type BidiProps, isolate, stripIsolates } from './Bidi';
export { Card, type CardProps } from './Card';
export { Checklist, type ChecklistItem, type ChecklistProps } from './Checklist';
export { Collapsible, type CollapsibleProps } from './Collapsible';
export { ConfidenceChip, type ConfidenceChipProps } from './ConfidenceChip';
export { Crop, cropGeometry, type CropProps } from './Crop';
export { ExternalLink, type ExternalLinkProps, openExternal } from './ExternalLink';
export { FeedbackRow, type FeedbackRowProps } from './FeedbackRow';
export { Icon, type IconName, type IconProps } from './Icon';
export { Interpolated, splitTemplate } from './Interpolated';
export { ProgressSteps, type ProgressStepsProps } from './ProgressSteps';
export { EMERGENCY_HREF, openEmergency, RestartNotice, Screen, ScreenHeader, type ScreenProps } from './Screen';
export { ChoiceChips, LinkRow, SettingsSection, SwitchRow, ToggleChip } from './SettingsRows';
export { TabBar, TAB_ICONS } from './TabBar';
export { SpeakButton, type SpeakButtonProps } from './SpeakButton';
export { EmptyState, type EmptyStateProps, ErrorState, type ErrorStateProps } from './States';
export { AppText, type AppTextProps, Heading, type HeadingProps, type TextVariant, useTextStyle } from './Text';
export { badgeTier, TierBadge, tierBadgeKey } from './TierBadge';
export { Tile, type TileProps } from './Tile';
export { UrgencyBanner, type UrgencyBannerProps } from './UrgencyBanner';
