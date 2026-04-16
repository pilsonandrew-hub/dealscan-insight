#!/usr/bin/env node
const http = require('http');

const TASK_ENDPOINT = process.env.JAVARIOUS_TASK_TRANSPORT_URL || 'http://127.0.0.1:8787/task';

function normalizeString(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function shouldUseExternalReviewTask(userRequest) {
  const text = normalizeString(userRequest).toLowerCase();
  if (!text) return false;
  const directTriggers = [
    'review this',
    'critique this',
    'audit this',
    'what are the risks',
    'challenge this architecture',
    'second opinion',
    'review the architecture',
    'please review',
    'review the typed',
    'identify the top risks',
    'external review',
  ];
  if (directTriggers.some((phrase) => text.includes(phrase))) return true;

  const hasReviewIntent = /(review|audit|critique|challenge|assess|evaluate|inspect)/.test(text);
  const hasTarget = /(architecture|design|contract|transport|integration|approach|plan|implementation|system)/.test(text);
  return hasReviewIntent && hasTarget;
}

function buildExternalReviewTaskPacket(userRequest, supportingContext = {}) {
  const contextNotes = Array.isArray(supportingContext.context_notes)
    ? supportingContext.context_notes.map(normalizeString).filter(Boolean)
    : [];
  return {
    agent: 'external_review',
    task_class: 'external_review',
    packet_version: '2026-04-16.v1',
    task_summary: normalizeString(supportingContext.task_summary) || normalizeString(userRequest),
    inputs: {
      review_type: normalizeString(supportingContext.review_type) || 'architecture',
      content: normalizeString(supportingContext.content) || normalizeString(userRequest),
      context_notes: contextNotes,
      priority: normalizeString(supportingContext.priority) || 'high',
    },
    required_output: [
      'decision',
      'confidence',
      'top_risks',
      'recommended_next_step',
      'escalation_suggested',
      'routing_metadata',
    ],
  };
}

function postJson(url, payload) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const body = JSON.stringify(payload);
    const req = http.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        path: target.pathname,
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'content-length': Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          let data;
          try {
            data = raw ? JSON.parse(raw) : {};
          } catch {
            return reject(new Error(`Invalid JSON response from /task: ${raw}`));
          }
          if (res.statusCode < 200 || res.statusCode >= 300) {
            return reject(new Error(data?.message || data?.error || `Task transport failed with status ${res.statusCode}`));
          }
          resolve(data);
        });
      }
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function callTypedTaskTransport(packet) {
  const response = await postJson(TASK_ENDPOINT, packet);
  if (!response || response.ok !== true) {
    throw new Error(response?.error || 'Typed task transport returned non-ok response');
  }
  if (normalizeString(response?.task_class) !== 'external_review') {
    throw new Error(`Unexpected task_class from transport: ${response?.task_class || '(missing)'}`);
  }
  return response;
}

function normalizeExternalReviewObject(result, response) {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  return {
    decision: normalizeString(result.decision),
    confidence: typeof result.confidence === 'number' ? result.confidence : Number(result.confidence),
    top_risks: Array.isArray(result.top_risks) ? result.top_risks : [],
    recommended_next_step: normalizeString(result.recommended_next_step),
    escalation_suggested: Boolean(result.escalation_suggested),
    routing_metadata: result.routing_metadata || response?.routing || null,
  };
}

function renderExternalReviewResult(response) {
  const normalized = normalizeExternalReviewObject(response?.result, response);
  if (!normalized) {
    throw new Error('Typed task transport returned non-object result for external_review');
  }
  return {
    raw: normalizeString(response?.raw_result),
    parsed: normalized,
    summary: normalized,
    transport: {
      lane: response?.lane,
      model: response?.model,
      provider: response?.provider,
      routing: response?.routing,
      repaired: Boolean(response?.repaired),
    },
  };
}

async function main() {
  const request = process.argv.slice(2).join(' ').trim();
  if (!request) {
    console.error('Usage: node scripts/javarious-task-handoff-helper.js "review this architecture..."');
    process.exit(1);
  }
  if (!shouldUseExternalReviewTask(request)) {
    console.log(JSON.stringify({ use_task: false, reason: 'request_did_not_match_external_review_phase1' }, null, 2));
    return;
  }
  const packet = buildExternalReviewTaskPacket(request, {
    context_notes: [
      'Typed /task transport is live',
      'External Review Agent routes to claude-sonnet-4.5',
    ],
  });
  const response = await callTypedTaskTransport(packet);
  const rendered = renderExternalReviewResult(response);
  console.log(JSON.stringify({ use_task: true, packet, response, rendered }, null, 2));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message || String(error));
    process.exit(1);
  });
}

module.exports = {
  shouldUseExternalReviewTask,
  buildExternalReviewTaskPacket,
  callTypedTaskTransport,
  renderExternalReviewResult,
};
