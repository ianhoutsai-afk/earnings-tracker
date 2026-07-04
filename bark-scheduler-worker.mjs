const GITHUB_API_URL =
  'https://api.github.com/repos/ianhoutsai-afk/earnings-tracker/actions/workflows/bark.yml/dispatches';

export async function dispatchBarkWorkflow(env, fetchImpl = fetch) {
  const token = String(env.GITHUB_ACTIONS_TOKEN || '').trim();
  if (!token) {
    throw new Error('GITHUB_ACTIONS_TOKEN is not configured');
  }

  const response = await fetchImpl(GITHUB_API_URL, {
    method: 'POST',
    headers: {
      'Accept': 'application/vnd.github+json',
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': 'earnings-tracker-bark-scheduler',
      'X-GitHub-Api-Version': '2026-03-10',
    },
    body: JSON.stringify({
      ref: 'main',
      inputs: {
        test_notification: 'false',
      },
    }),
  });

  if (response.status !== 200 && response.status !== 204) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error(
      `GitHub workflow dispatch failed with HTTP ${response.status}: ${detail}`
    );
  }
}

export function createScheduler(fetchImpl = fetch) {
  return {
    async scheduled(_controller, env, ctx) {
      ctx.waitUntil(dispatchBarkWorkflow(env, fetchImpl));
    },
  };
}

export default createScheduler();
