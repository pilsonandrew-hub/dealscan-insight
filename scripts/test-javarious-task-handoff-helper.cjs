const assert = require('assert');
const helper = require('./javarious-task-handoff-helper.cjs');

const rendered = helper.renderExternalReviewResult({
  lane: 'openrouter_claude_review',
  model: 'anthropic/claude-sonnet-4.5',
  provider: 'Amazon Bedrock',
  routing: { task_class: 'external_review', policy_version: '2026-04-16.v2' },
  repaired: true,
  raw_result: '```json {"bad":true} ```',
  result: {
    decision: 'APPROVED_WITH_CONDITIONS',
    confidence: 0.82,
    top_risks: ['a', 'b', 'c'],
    recommended_next_step: 'Ship behind a flag',
    escalation_suggested: false,
    routing_metadata: { task_class: 'external_review', policy_version: '2026-04-16.v2' },
  },
});

assert.equal(rendered.summary.decision, 'APPROVED_WITH_CONDITIONS');
assert.equal(rendered.summary.top_risks.length, 3);
assert.equal(rendered.transport.repaired, true);
assert.equal(rendered.summary.routing_metadata.policy_version, '2026-04-16.v2');

assert.throws(() => helper.renderExternalReviewResult({ result: 'bad' }), /non-object result/);

console.log('helper tests passed');
