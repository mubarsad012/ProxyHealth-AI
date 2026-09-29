// Vector glyphs (PRODUCT_SPEC §5.1 "icons are vector glyphs with accessibilityLabel"). Drawn with
// react-native-svg (works on iOS, Android and web); no icon font, no emoji, no SF Symbols (D-27).
// Icons of real objects are never mirrored in RTL; pass `mirror` for chevrons/arrows only.

import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { useDirection } from '@/i18n/direction';

export type IconName =
  | 'home'
  | 'papers'
  | 'help'
  | 'settings'
  | 'camera'
  | 'image'
  | 'speaker'
  | 'stop'
  | 'alert'
  | 'calendar'
  | 'calendar-alert'
  | 'calendar-clock'
  | 'info'
  | 'lock'
  | 'cloud'
  | 'server'
  | 'phone'
  | 'check'
  | 'chevron-right'
  | 'chevron-down'
  | 'arrow-back'
  | 'globe'
  | 'text-size'
  | 'close'
  | 'thumb-up'
  | 'thumb-down'
  | 'flag'
  | 'search'
  | 'refresh'
  | 'people'
  | 'sample'
  | 'offline';

export interface IconProps {
  name: IconName;
  size?: number;
  color: string;
  /** Flip horizontally in RTL (chevrons, back arrows, progress). Real objects: never. */
  mirror?: boolean;
  /** When set the icon is announced; otherwise it is hidden from assistive tech. */
  accessibilityLabel?: string;
}

const MIRRORABLE: ReadonlySet<IconName> = new Set(['chevron-right', 'arrow-back']);

function glyph(name: IconName, c: string) {
  const s = { stroke: c, strokeWidth: 2, fill: 'none', strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
  switch (name) {
    case 'home':
      return <Path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" {...s} />;
    case 'papers':
      return (
        <>
          <Path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" {...s} />
          <Path d="M14 3v5h5M9 13h7M9 17h7" {...s} />
        </>
      );
    case 'help':
      return (
        <>
          <Circle cx={12} cy={12} r={9} {...s} />
          <Path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.01" {...s} />
        </>
      );
    case 'settings':
      return (
        <>
          <Circle cx={12} cy={12} r={3} {...s} />
          <Path
            d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"
            {...s}
          />
        </>
      );
    case 'camera':
      return (
        <>
          <Path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" {...s} />
          <Circle cx={12} cy={13.5} r={3.5} {...s} />
        </>
      );
    case 'image':
      return (
        <>
          <Rect x={3} y={4} width={18} height={16} rx={2} {...s} />
          <Circle cx={8.5} cy={9.5} r={1.5} {...s} />
          <Path d="M21 16l-5-5-9 9" {...s} />
        </>
      );
    case 'speaker':
      return <Path d="M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" {...s} />;
    case 'stop':
      return <Rect x={6} y={6} width={12} height={12} rx={1.5} {...s} fill={c} />;
    case 'alert':
      return <Path d="M12 3l9.5 17h-19zM12 10v4M12 17.5v.01" {...s} />;
    case 'calendar':
      return (
        <>
          <Rect x={3} y={5} width={18} height={16} rx={2} {...s} />
          <Path d="M3 10h18M8 3v4M16 3v4" {...s} />
        </>
      );
    case 'calendar-alert':
      return (
        <>
          <Rect x={3} y={5} width={18} height={16} rx={2} {...s} />
          <Path d="M3 10h18M8 3v4M16 3v4M12 13v3M12 18.5v.01" {...s} />
        </>
      );
    case 'calendar-clock':
      return (
        <>
          <Path d="M11 21H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4M3 10h18M8 3v4M16 3v4" {...s} />
          <Circle cx={17} cy={17} r={4} {...s} />
          <Path d="M17 15.5V17l1 1" {...s} />
        </>
      );
    case 'info':
      return (
        <>
          <Circle cx={12} cy={12} r={9} {...s} />
          <Path d="M12 11v6M12 7.5v.01" {...s} />
        </>
      );
    case 'lock':
      return (
        <>
          <Rect x={5} y={11} width={14} height={10} rx={2} {...s} />
          <Path d="M8 11V7a4 4 0 0 1 8 0v4" {...s} />
        </>
      );
    case 'cloud':
      return <Path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z" {...s} />;
    case 'server':
      return (
        <>
          <Rect x={4} y={4} width={16} height={7} rx={1.5} {...s} />
          <Rect x={4} y={13} width={16} height={7} rx={1.5} {...s} />
          <Path d="M8 7.5v.01M8 16.5v.01M3 21L21 3" {...s} />
        </>
      );
    case 'phone':
      return (
        <>
          <Rect x={7} y={2.5} width={10} height={19} rx={2} {...s} />
          <Path d="M11 18.5h2" {...s} />
        </>
      );
    case 'check':
      return <Path d="M5 12.5l4.5 4.5L19 7.5" {...s} />;
    case 'chevron-right':
      return <Path d="M9 5l7 7-7 7" {...s} />;
    case 'chevron-down':
      return <Path d="M5 9l7 7 7-7" {...s} />;
    case 'arrow-back':
      return <Path d="M20 12H5M11 5l-7 7 7 7" {...s} />;
    case 'globe':
      return (
        <>
          <Circle cx={12} cy={12} r={9} {...s} />
          <Path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" {...s} />
        </>
      );
    case 'text-size':
      return <Path d="M3 19l5-13 5 13M4.5 15h7M14 19l3.5-9 3.5 9M15 16.5h5" {...s} />;
    case 'close':
      return <Path d="M6 6l12 12M18 6L6 18" {...s} />;
    case 'thumb-up':
      return <Path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7" {...s} />;
    case 'thumb-down':
      return <Path d="M7 13V4H4v9zM7 13l4 8a2 2 0 0 0 2-2v-4h5.5a2 2 0 0 0 2-2.3l-1.2-7A2 2 0 0 0 17.3 4H7" {...s} />;
    case 'flag':
      return <Path d="M5 21V4M5 4h11l-2 4 2 4H5" {...s} />;
    case 'search':
      return (
        <>
          <Circle cx={11} cy={11} r={6.5} {...s} />
          <Path d="M16 16l5 5" {...s} />
        </>
      );
    case 'refresh':
      return <Path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" {...s} />;
    case 'people':
      return (
        <>
          <Circle cx={9} cy={8} r={3.5} {...s} />
          <Path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6.5 6.5 0 0 1 3.5 6" {...s} />
        </>
      );
    case 'sample':
      return (
        <>
          <Path d="M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" {...s} />
          <Path d="M9 8h6M9 12h6M9 16h3" {...s} />
        </>
      );
    case 'offline':
      return <Path d="M2 8.5a15 15 0 0 1 20 0M5.5 12a10 10 0 0 1 13 0M9 15.5a5 5 0 0 1 6 0M12 19v.01M3 3l18 18" {...s} />;
  }
}

export function Icon({ name, size = 24, color, mirror, accessibilityLabel }: IconProps) {
  const { isRTL } = useDirection();
  const flip = isRTL && (mirror ?? MIRRORABLE.has(name));
  const a11y = accessibilityLabel
    ? { accessible: true, accessibilityLabel, role: 'img' as const }
    : { accessible: false, 'aria-hidden': true as const, importantForAccessibility: 'no-hide-descendants' as const };
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      style={flip ? { transform: [{ scaleX: -1 }] } : undefined}
      {...a11y}>
      {glyph(name, color)}
    </Svg>
  );
}
