const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { routeRoutingRequest, buildBridgeRequest, buildClaudeCompactContract } = require('./paperclip-routing-governor.cjs');

const CONFIG_PATH = path.join(__dirname, '..', 'reports', 'paperclip-routing-governor-config-v2-2026-04-16.json');

test('routes external_review to Gemini 2.5 Flash with Gemini 2.0 fallback', () => {
  const decision = routeRoutingRequest(
    { task_class: 'external_review' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(decision.task_class, 'external_review');
  assert.equal(decision.priority, 'high');
  assert.equal(decision.selected_provider, 'openrouter');
  assert.equal(decision.selected_model, 'google/gemini-2.5-flash');
  assert.equal(decision.selected_lane, 'openrouter_gemini_review');
  assert.deepEqual(decision.fallback_chain, [
    { provider: 'openrouter', model: 'google/gemini-2.0-flash-001', lane: 'openrouter_gemini_proven' },
  ]);
  assert.equal(decision.budget_approved, true);
  assert.equal(decision.policy_version, '2026-04-17.v5');
});

test('routes local_only_private to the local lane without external providers', () => {
  const decision = routeRoutingRequest(
    { task_class: 'local_only_private' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(decision.selected_provider, 'local');
  assert.equal(decision.selected_model, null);
  assert.equal(decision.selected_lane, 'local_private_lane');
  assert.deepEqual(decision.fallback_chain, []);
  assert.equal(decision.budget_approved, true);
});

test('hard-blocks crosshair_filter from any LLM route', () => {
  const decision = routeRoutingRequest(
    { task_class: 'crosshair_filter' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(decision.blocked, true);
  assert.equal(decision.selected_lane, 'blocked_no_llm');
  assert.equal(decision.selected_provider, 'blocked');
  assert.equal(decision.selected_model, null);
});

test('routes psr_extraction to Kimi specialist only', () => {
  const decision = routeRoutingRequest(
    { task_class: 'psr_extraction' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(decision.selected_lane, 'openrouter_kimi_specialist');
  assert.equal(decision.selected_model, 'moonshotai/kimi-k2');
  assert.deepEqual(decision.fallback_chain, [
    { provider: 'openrouter', model: 'google/gemini-2.0-flash-001', lane: 'openrouter_gemini_proven' },
  ]);
});

test('routes financial-sensitive review tasks to Gemini, not DeepSeek', () => {
  const decision = routeRoutingRequest(
    { task_class: 'deal_adjudication' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(decision.selected_lane, 'openrouter_gemini_review');
  assert.equal(decision.selected_model, 'google/gemini-2.5-flash');
  assert.ok(decision.fallback_chain.every((lane) => lane.model !== 'deepseek/deepseek-v3.2'));
});

test('throws when no permitted route exists', () => {
  assert.throws(
    () =>
      routeRoutingRequest(
        { task_class: 'general_default' },
        {
          config: {
            version: 1,
            policy_version: '2026-04-15.v1',
            lanes: {
              local_private_lane: {
                provider: 'local',
                model: null,
                max_estimated_cost_usd: 0,
                premium: false,
                use_cases: ['local_only_private'],
              },
            },
            task_policy: {
              general_default: {
                primary: 'missing_lane',
                fallback: [],
                premium_allowed: false,
                requires_manual_approval: false,
              },
            },
            budget_policy: {
              default_max_estimated_cost_usd: 0.05,
              premium_without_explicit_approval: false,
              block_on_budget_exceeded: true,
            },
          },
        }
      ),
    /no permitted route/i
  );
});

test('throws when selected model is explicitly excluded', () => {
  assert.throws(
    () => routeRoutingRequest(
      { task_class: 'external_review', agent_hint: 'qwen' },
      {
        config: {
          version: 2,
          policy_version: '2026-04-17.v5',
          lanes: {
            openrouter_gemini_review: {
              provider: 'openrouter',
              model: 'google/gemini-2.5-flash',
              max_estimated_cost_usd: 0.03,
              premium: false,
              use_cases: ['external_review'],
            },
            openrouter_qwen_review: {
              provider: 'openrouter',
              model: 'qwen/qwen3-235b-a22b',
              max_estimated_cost_usd: 0.03,
              premium: true,
              use_cases: ['external_review'],
            },
          },
          agent_hint_policy: {
            qwen: 'openrouter_qwen_review',
          },
          task_policy: {
            external_review: {
              primary: 'openrouter_gemini_review',
              fallback: [],
              premium_allowed: false,
              requires_manual_approval: false,
            },
          },
          budget_policy: {
            default_max_estimated_cost_usd: 0.05,
            premium_without_explicit_approval: false,
            block_on_budget_exceeded: true,
          },
          excluded_models: [
            {
              model: 'qwen/qwen3-235b-a22b',
              reason: 'reasoning-heavy behavior makes it unsuitable for current governor-routed structured workloads',
            },
          ],
        },
      }
    ),
    /excluded/i
  );
});

test('buildBridgeRequest converts a RoutingDecision into bridge input', () => {
  const bridgeRequest = buildBridgeRequest(
    { task_class: 'external_review' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(bridgeRequest.lane, 'openrouter_gemini_review');
  assert.equal(bridgeRequest.model, 'google/gemini-2.5-flash');
  assert.equal(bridgeRequest.routing.task_class, 'external_review');
  assert.equal(bridgeRequest.routing.policy_version, '2026-04-17.v5');
  assert.equal(bridgeRequest.contract, undefined);
});

test('buildBridgeRequest attaches compact Claude contract for premium recon routing', () => {
  const bridgeRequest = buildBridgeRequest(
    { task_class: 'recon_scoring', agent_hint: 'claude' },
    { configPath: CONFIG_PATH }
  );

  assert.equal(bridgeRequest.lane, 'openrouter_claude_premium');
  assert.equal(bridgeRequest.model, 'anthropic/claude-opus-4.7');
  assert.equal(bridgeRequest.contract.response_format, 'json_compact');
  assert.deepEqual(bridgeRequest.contract.output_contract.ordered_keys, [
    'verdict',
    'confidence',
    'score',
    'max_bid',
    'top_risks',
    'rationale',
  ]);
});

test('buildClaudeCompactContract returns null for non-premium classes without a custom contract', () => {
  assert.equal(buildClaudeCompactContract('external_review'), null);
});
