const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

process.env.OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || 'test-key';
process.env.PAPERCLIP_ENABLE_CANARY_FAILOVER_TESTS = 'true';

function httpPostJson(port, path, body) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port,
      path,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }, (res) => {
      let raw = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(raw) });
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('error', reject);
    req.write(JSON.stringify(body));
    req.end();
  });
}

const {
  isRetryableUpstreamStatus,
  isRetryableRequestError,
  buildRunAttemptCandidates,
  executeRunWithFailover,
  server,
} = require('./paperclip-openrouter-bridge.cjs');

test('retryable upstream status classification is bounded', () => {
  assert.equal(isRetryableUpstreamStatus(429), true);
  assert.equal(isRetryableUpstreamStatus(503), true);
  assert.equal(isRetryableUpstreamStatus(400), false);
  assert.equal(isRetryableUpstreamStatus(401), false);
});

test('retryable request error classification is bounded', () => {
  assert.equal(isRetryableRequestError({ code: 'ETIMEDOUT' }), true);
  assert.equal(isRetryableRequestError({ code: 'ECONNRESET' }), true);
  assert.equal(isRetryableRequestError({ code: 'SOME_OTHER_ERROR' }), false);
});

test('buildRunAttemptCandidates uses selected lane then fallback_chain and dedupes lanes', () => {
  const candidates = buildRunAttemptCandidates({
    lane: 'openrouter_gemini_review',
    model: 'google/gemini-2.5-flash',
    routing: {
      fallback_chain: [
        { lane: 'openrouter_gemini_proven', model: 'google/gemini-2.0-flash-001' },
        { lane: 'openrouter_qwen_review', model: 'qwen/qwen3.6-plus' },
        { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash' },
      ],
    },
  });

  assert.deepEqual(candidates.map((candidate) => candidate.lane), [
    'openrouter_gemini_review',
    'openrouter_gemini_proven',
    'openrouter_qwen_review',
  ]);
});

test('executeRunWithFailover falls back on retryable upstream failure', async () => {
  const calls = [];
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    if (body.model === 'google/gemini-2.5-flash') {
      return {
        ok: false,
        status: 503,
        json: async () => ({ error: 'temporarily_unavailable' }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: 'ok' } }], provider: 'Alibaba' }),
    };
  };

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_qwen_review', model: 'qwen/qwen3.6-plus', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    fetchImpl,
  });

  assert.equal(result.ok, true);
  assert.equal(result.winner.lane, 'openrouter_qwen_review');
  assert.deepEqual(calls, ['google/gemini-2.5-flash', 'qwen/qwen3.6-plus']);
});

test('executeRunWithFailover does not fall back on non-retryable upstream failure', async () => {
  const calls = [];
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    return {
      ok: false,
      status: 400,
      json: async () => ({ error: 'bad_request' }),
    };
  };

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_qwen_review', model: 'qwen/qwen3.6-plus', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    fetchImpl,
  });

  assert.equal(result.ok, false);
  assert.equal(result.terminal, true);
  assert.deepEqual(calls, ['google/gemini-2.5-flash']);
});

test('executeRunWithFailover exhausts the chain on retryable failures', async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ error: 'temporarily_unavailable' }),
  });

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_qwen_review', model: 'qwen/qwen3.6-plus', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    fetchImpl,
  });

  assert.equal(result.ok, false);
  assert.equal(result.attempts.length, 2);
  assert.equal(result.failure.status, 503);
});

test('executeRunWithFailover honors explicit canary retryable failure injection', async () => {
  const calls = [];
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    return {
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: 'ok' } }], provider: 'Alibaba' }),
    };
  };

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_qwen_review', model: 'qwen/qwen3.6-plus', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    body: { context: { canary_failover_test: true, canary_fail_lane: 'openrouter_gemini_review' } },
    fetchImpl,
  });

  assert.equal(result.ok, true);
  assert.equal(result.winner.lane, 'openrouter_qwen_review');
  assert.deepEqual(calls, ['qwen/qwen3.6-plus']);
  assert.equal(result.attempts[0].injected_canary_failure, true);
});

test('executeRunWithFailover honors explicit canary timeout injection', async () => {
  const calls = [];
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    return {
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: 'ok' } }], provider: 'Google' }),
    };
  };

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_gemini_proven', model: 'google/gemini-2.0-flash-001', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    body: { context: { canary_failover_test: true, canary_fail_lane: 'openrouter_gemini_review', canary_fail_mode: 'timeout' } },
    fetchImpl,
  });

  assert.equal(result.ok, true);
  assert.equal(result.winner.lane, 'openrouter_gemini_proven');
  assert.deepEqual(calls, ['google/gemini-2.0-flash-001']);
  assert.equal(result.attempts[0].injected_mode, 'timeout');
  assert.equal(result.attempts[0].error_code, 'ETIMEDOUT');
});

test('executeRunWithFailover retries after timeout-class request error', async () => {
  const calls = [];
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    if (body.model === 'google/gemini-2.5-flash') {
      const error = new Error('timeout');
      error.code = 'ETIMEDOUT';
      throw error;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: 'ok' } }], provider: 'Google' }),
    };
  };

  const result = await executeRunWithFailover({
    candidates: [
      { lane: 'openrouter_gemini_review', model: 'google/gemini-2.5-flash', laneConfig: { provider: 'openrouter' } },
      { lane: 'openrouter_gemini_proven', model: 'google/gemini-2.0-flash-001', laneConfig: { provider: 'openrouter' } },
    ],
    runPrompt: { systemPrompt: 's', userPrompt: 'u', maxTokens: 10 },
    fetchImpl,
  });

  assert.equal(result.ok, true);
  assert.equal(result.winner.lane, 'openrouter_gemini_proven');
  assert.deepEqual(calls, ['google/gemini-2.5-flash', 'google/gemini-2.0-flash-001']);
});

test('HTTP /run handler returns fallback success with attempted lanes', async () => {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.model);
    if (body.model === 'google/gemini-2.5-flash') {
      return {
        ok: false,
        status: 503,
        json: async () => ({ error: 'temporarily_unavailable' }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ choices: [{ message: { content: 'HTTP_FAILOVER_OK' } }], provider: 'Google' }),
    };
  };

  const ephemeralServer = server.listen(0, '127.0.0.1');
  await new Promise((resolve) => ephemeralServer.once('listening', resolve));

  try {
    const { port } = ephemeralServer.address();
    const response = await httpPostJson(port, '/run', {
        task_class: 'external_review',
        context: { prompt: 'Return only HTTP_FAILOVER_OK.' },
        max_tokens: 20,
        temperature: 0,
    });
    const data = response.body;

    assert.equal(response.status, 200);
    assert.equal(typeof data, 'object');
    assert.equal(data.error, undefined, JSON.stringify(data));
    assert.equal(data.ok, true);
    assert.equal(data.lane, 'openrouter_gemini_proven');
    assert.deepEqual(data.attempted_lanes, ['openrouter_gemini_review', 'openrouter_gemini_proven']);
    assert.equal(data.content.trim(), 'HTTP_FAILOVER_OK');
    assert.deepEqual(calls, ['google/gemini-2.5-flash', 'google/gemini-2.0-flash-001']);
  } finally {
    global.fetch = originalFetch;
    await new Promise((resolve, reject) => ephemeralServer.close((err) => err ? reject(err) : resolve()));
  }
});
