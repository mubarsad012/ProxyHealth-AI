// Sequential read-aloud ("Read all aloud" / hear-it mode, PRODUCT_SPEC S7 item 18): plays a list
// of paragraphs one after another through `lib/tts.speak`, stops on demand, and reports which
// item is playing so the screen can pin the stop bar and scroll along.

import { useCallback, useEffect, useRef, useState } from 'react';

import { speak, stop } from '@/lib/tts';

export interface SpeechItem {
  id: string;
  text: string;
  lang: string;
}

export interface SequentialSpeech {
  playing: boolean;
  currentId: string | null;
  play(items: SpeechItem[]): Promise<void>;
  stop(): void;
}

export function useSequentialSpeech(): SequentialSpeech {
  const [playing, setPlaying] = useState(false);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const run = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      run.current += 1;
      void stop();
    };
  }, []);

  const halt = useCallback(() => {
    run.current += 1;
    void stop();
    setPlaying(false);
    setCurrentId(null);
  }, []);

  const play = useCallback(async (items: SpeechItem[]) => {
    run.current += 1;
    const mine = run.current;
    setPlaying(true);
    for (const item of items) {
      if (mine !== run.current || !mounted.current) return;
      if (!item.text.trim()) continue;
      setCurrentId(item.id);
      await speak(item.text, item.lang, `seq:${item.id}`);
    }
    if (mine === run.current && mounted.current) {
      setPlaying(false);
      setCurrentId(null);
    }
  }, []);

  return { playing, currentId, play, stop: halt };
}
