// Settings → About "Report a problem" (PRODUCT_SPEC S17 item 9): the fixed kinds only, sent with the
// app-level surface `app` (CL-057) — it is not feedback on an AI summary, so it must not count as one.

import { fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { resetServerConfigSession } from '@/api/config';
import { ApiError } from '@/api/errors';
import type { FeedbackRequest } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { kv } from '@/storage/kv';
import { useSession } from '@/store/session';

import { AboutSection } from './SettingsSections';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function recordingClient(sent: FeedbackRequest[]): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({} as ApiClient, {
    get: (_t, prop) => {
      if (prop === 'feedback') {
        return (req: FeedbackRequest) => {
          sent.push(req);
          return Promise.resolve({ accepted: true });
        };
      }
      if (prop === 'baseUrl') return 'http://127.0.0.1:8026';
      return fail;
    },
  });
}

describe('Settings → About "Report a problem"', () => {
  beforeEach(async () => {
    await kv.clearAll();
    resetServerConfigSession();
    useSession.getState().reset();
  });

  it('posts the fixed kind with surface "app" (not "summary") and no free text', async () => {
    const sent: FeedbackRequest[] = [];
    const { getByText, findByText } = await render(
      <AppProviders client={recordingClient(sent)} staticMetrics>
        <AboutSection config={null} />
      </AppProviders>,
    );
    fireEvent.press(getByText('Report a problem'));
    fireEvent.press(await findByText('Hard to understand'));
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ surface: 'app', kind: 'unclear', card_id: null, document_type: null });
    expect(sent[0].surface).not.toBe('summary');
    expect(await findByText('Thank you. We count your answer only. We never send your paper.')).toBeTruthy();
  });
});
