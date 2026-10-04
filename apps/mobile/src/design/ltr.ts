import { Platform, type ViewStyle } from 'react-native';

/**
 * Keeps a page image and its overlay boxes (quote crops, mask boxes, highlights) in physical
 * left-to-right coordinates inside RTL layouts — a photographed page is never mirrored.
 * Native: Yoga `direction: 'ltr'`. Web: react-native-web rejects `direction` ("Invalid style
 * property") and never mirrors physical `left`/`top`, so nothing is needed there.
 */
export const ltrBox: ViewStyle = Platform.OS === 'web' ? {} : { direction: 'ltr' };
