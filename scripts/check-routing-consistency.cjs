#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..');
const CONFIG_PATH = path.join(ROOT, 'reports', 'paperclip-routing-governor-config-v2-2026-04-16.json');
const ROLE_MAP_PATH = path.join(ROOT, 'reports', 'dealerscope-model-role-map-2026-04-17.md');
const GOV_SPEC_PATH = path.join(ROOT, 'reports', 'dealerscope-model-governor-spec-2026-04-17.md');
const HELPER_PATH = path.join(ROOT, 'scripts', 'javarious-task-handoff-helper.cjs');
const GOVERNOR_PATH = path.join(ROOT, 'scripts', 'paperclip-routing-governor.cjs');
const TEST_PATH = path.join(ROOT, 'scripts', 'paperclip-routing-governor.test.cjs');
const BRIDGE_PATH = path.join(ROOT, 'scripts', 'paperclip-openrouter-bridge.cjs');

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function fail(message) {
  console.error(`CONSISTENCY_FAIL ${message}`);
  process.exit(1);
}

function pass(message) {
  console.log(`CONSISTENCY_OK ${message}`);
}

const config = JSON.parse(read(CONFIG_PATH));
const roleMap = read(ROLE_MAP_PATH);
const govSpec = read(GOV_SPEC_PATH);
const helper = read(HELPER_PATH);
const governor = read(GOVERNOR_PATH);
const testFile = read(TEST_PATH);
const bridge = read(BRIDGE_PATH);

try {
  assert.equal(config.policy_version, '2026-04-17.v5');
  pass('policy version is 2026-04-17.v5 in active config');

  const requiredBridgeLanes = [
    'openrouter_claude_premium',
    'openrouter_gemini_review',
    'openrouter_gemini_proven',
    'openrouter_deepseek_workhorse',
    'openrouter_gemini_triage',
    'openrouter_kimi_specialist',
  ];
  const requiredConfigOnlyLanes = ['local_private_lane', 'blocked_no_llm'];

  for (const lane of requiredBridgeLanes) {
    assert.ok(config.lanes[lane], `missing lane in config: ${lane}`);
    assert.ok(bridge.includes(lane), `bridge missing lane string: ${lane}`);
  }
  for (const lane of requiredConfigOnlyLanes) {
    assert.ok(config.lanes[lane], `missing config-only lane in config: ${lane}`);
  }
  pass('active bridge lanes exist in config and bridge, and config-only blocked/local lanes remain declared');

  assert.equal(config.task_policy.external_review.primary, 'openrouter_gemini_review');
  assert.equal(config.task_policy.psr_extraction.primary, 'openrouter_kimi_specialist');
  assert.equal(config.task_policy.crosshair_filter.primary, 'blocked_no_llm');
  assert.equal(config.task_policy.recon_scoring.primary, 'openrouter_gemini_review');
  assert.equal(config.task_policy.deal_adjudication.primary, 'openrouter_gemini_review');
  pass('critical task-class primary routes match expected policy');

  assert.equal(config.task_policy.crosshair_filter.primary, 'blocked_no_llm');
  assert.equal(config.task_policy.recon_scoring.premium_allowed, true);
  assert.equal(config.task_policy.recon_scoring.requires_manual_approval, true);
  assert.equal(config.task_policy.deal_adjudication.premium_allowed, false);
  assert.equal(config.task_policy.deal_adjudication.requires_manual_approval, true);
  assert.equal(config.task_policy.market_intel_financial.premium_allowed, false);
  assert.equal(config.task_policy.market_intel_financial.requires_manual_approval, true);
  pass('sensitive-task premium and blocked-lane rules match expected policy');

  const deepseekUseCases = config.lanes.openrouter_deepseek_workhorse.use_cases || [];
  for (const forbidden of ['recon_scoring', 'deal_adjudication', 'market_intel_financial', 'premium_judgment']) {
    assert.ok(!deepseekUseCases.includes(forbidden), `deepseek lane must not allow ${forbidden}`);
  }
  pass('deepseek workhorse is not allowed on financial-sensitive classes');

  const kimiUseCases = config.lanes.openrouter_kimi_specialist.use_cases || [];
  assert.deepEqual(kimiUseCases, ['psr_extraction']);
  pass('kimi remains specialist-only for psr_extraction');

  assert.ok(governor.includes('openrouter_claude_premium'), 'governor missing premium lane logic');
  assert.ok(governor.includes('json_compact'), 'governor missing compact contract logic');
  assert.ok(bridge.includes('contract_applied'), 'bridge missing contract application metadata');
  pass('governor and bridge still express compact premium contract path');

  assert.ok(helper.includes('Gemini 2.5 Flash as the default review lane'), 'helper stale on default review lane');
  assert.ok(helper.includes('Premium Claude use is restricted to certified compact-contract escalation paths'), 'helper stale on premium Claude restriction');
  pass('helper notes match current routing posture');

  assert.ok(testFile.includes('policy_version'), 'tests missing policy assertions');
  assert.ok(testFile.includes('openrouter_kimi_specialist'), 'tests missing kimi specialist coverage');
  assert.ok(testFile.includes('openrouter_claude_premium'), 'tests missing premium Claude coverage');
  pass('routing tests still reference key active policy lanes');

  assert.ok(roleMap.includes('certified compact premium contract path'), 'role map missing certified compact premium language');
  assert.ok(govSpec.includes('Crosshair'), 'governor spec missing Crosshair block documentation');
  pass('active docs still reflect current runtime policy');

  console.log('ROUTING_CONSISTENCY_PASS');
} catch (error) {
  fail(error.message || String(error));
}
