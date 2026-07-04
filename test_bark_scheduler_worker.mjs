import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createScheduler,
  dispatchBarkWorkflow,
} from './bark-scheduler-worker.mjs';

test('dispatches the production Bark workflow on main', async () => {
  const captured = {};
  const fakeFetch = async (url, options) => {
    captured.url = url;
    captured.options = options;
    return {
      status: 204,
      async text() {
        return '';
      },
    };
  };

  await dispatchBarkWorkflow(
    { GITHUB_ACTIONS_TOKEN: 'test-token' },
    fakeFetch,
  );

  assert.equal(
    captured.url,
    'https://api.github.com/repos/ianhoutsai-afk/earnings-tracker/actions/workflows/bark.yml/dispatches',
  );
  assert.equal(captured.options.method, 'POST');
  assert.equal(
    captured.options.headers.Authorization,
    'Bearer test-token',
  );
  assert.equal(
    captured.options.headers['X-GitHub-Api-Version'],
    '2026-03-10',
  );
  assert.deepEqual(JSON.parse(captured.options.body), {
    ref: 'main',
    inputs: {
      test_notification: 'false',
    },
  });
});

test('rejects a missing GitHub Actions token without making a request', async () => {
  let called = false;
  const fakeFetch = async () => {
    called = true;
  };

  await assert.rejects(
    dispatchBarkWorkflow({}, fakeFetch),
    /GITHUB_ACTIONS_TOKEN is not configured/,
  );
  assert.equal(called, false);
});

test('rejects a non-success GitHub response', async () => {
  const fakeFetch = async () => ({
    status: 401,
    async text() {
      return '{"message":"Bad credentials"}';
    },
  });

  await assert.rejects(
    dispatchBarkWorkflow(
      { GITHUB_ACTIONS_TOKEN: 'invalid-token' },
      fakeFetch,
    ),
    /HTTP 401.*Bad credentials/,
  );
});

test('accepts the workflow run response returned by newer API versions', async () => {
  const fakeFetch = async () => ({
    status: 200,
    async text() {
      return '{"workflow_run_id":123}';
    },
  });

  await dispatchBarkWorkflow(
    { GITHUB_ACTIONS_TOKEN: 'test-token' },
    fakeFetch,
  );
});

test('scheduled events keep the workflow dispatch alive', async () => {
  const fakeFetch = async () => ({
    status: 204,
    async text() {
      return '';
    },
  });
  const scheduler = createScheduler(fakeFetch);
  let scheduledPromise;

  await scheduler.scheduled(
    {},
    { GITHUB_ACTIONS_TOKEN: 'test-token' },
    {
      waitUntil(promise) {
        scheduledPromise = promise;
      },
    },
  );

  assert.ok(scheduledPromise instanceof Promise);
  await scheduledPromise;
});
