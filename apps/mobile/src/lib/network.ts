// Reachability (ARCHITECTURE §3.1 "Offline behaviors"). expo-network works on web
// (navigator.onLine → type UNKNOWN when connected, NONE when offline).

import * as Network from 'expo-network';
import { useEffect, useState } from 'react';

export interface OnlineState {
  /** True when the device reports a connection and does not say internet is unreachable. */
  online: boolean;
  /** Undefined until the first reading. */
  known: boolean;
}

function toOnline(state: Network.NetworkState | null | undefined): boolean {
  if (!state) return true;
  if (state.isConnected === false) return false;
  if (state.isInternetReachable === false) return false;
  return true;
}

export async function isOnline(): Promise<boolean> {
  try {
    return toOnline(await Network.getNetworkStateAsync());
  } catch {
    return true;
  }
}

/** Live reachability. Optimistic (online) until the first reading arrives. */
export function useOnline(): OnlineState {
  const [state, setState] = useState<OnlineState>({ online: true, known: false });
  useEffect(() => {
    let cancelled = false;
    isOnline().then((online) => {
      if (!cancelled) setState({ online, known: true });
    });
    let sub: { remove?: () => void } | null = null;
    try {
      sub = Network.addNetworkStateListener((e) => {
        setState({ online: toOnline(e), known: true });
      });
    } catch {
      sub = null;
    }
    return () => {
      cancelled = true;
      // CL-034: the jest-expo expo-network mock returns a listener without `remove`.
      if (typeof sub?.remove === 'function') sub.remove();
    };
  }, []);
  return state;
}
