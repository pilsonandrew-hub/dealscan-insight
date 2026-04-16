#!/usr/bin/env node
const http = require('http');
const path = require('node:path');

const { buildBridgeRequest } = require('./paperclip-routing-governor');

const PORT = process.env.PORT ? Number(process.env.PORT) : 8787;
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const OPENROUTER_LEGACY_DEFAULTS_ENABLED = normalizeFlag(process.env.OPENROUTER_LEGACY_DEFAULTS_ENABLED);
const OPENROUTER_LEGACY_DEFAULT_LANE = normalizeString(process.env.OPENROUTER_LEGACY_DEFAULT_LANE);
const OPENROUTER_LEGACY_DEFAULT_MODEL = normalizeString(process.env.OPENROUTER_LEGACY_DEFAULT_MODEL);
const ROUTING_GOVERNOR_CONFIG_PATH = normalizeString(process.env.PAPERCLIP_ROUTING_GOVERNOR_CONFIG_PATH) || path.join(__dirname, '..', 'reports', 'paperclip-routing-governor-config-v2-2026-04-16.json');

const OPENROUTER_LANES = Object.freeze({
  openrouter_claude_review: Object.freeze({
    provider: 'openrouter',
    defaultModel: 'anthropic/claude-sonnet-4.5',
    allowedModels: Object.freeze([
      'anthropic/claude-sonnet-4.5',
      'anthropic/claude-3.7-sonnet',
    ]),
  }),
  openrouter_claude_fallback: Object.freeze({
    provider: 'openrouter',
    defaultModel: 'anthropic/claude-3.7-sonnet',
    allowedModels: Object.freeze([
      'anthropic/claude-3.7-sonnet',
    ]),
  }),
  openrouter_deepseek_reasoner: Object.freeze({
    provider: 'openrouter',
    defaultModel: 'deepseek/deepseek-v3.2',
    allowedModels: Object.freeze([
      'deepseek/deepseek-v3.2',
    ]),
  }),
  openrouter_general: Object.freeze({
    provider: 'openrouter',
    defaultModel: 'deepseek/deepseek-v3.2',
    allowedModels: Object.freeze([
      'deepseek/deepseek-v3.2',
    ]),
  }),
});

validateLaneCatalog();

if (!OPENROUTER_API_KEY) {
  throw new Error('OPENROUTER_API_KEY is required for paperclip-openrouter-bridge');
}

function normalizeString(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeFlag(value) {
  return normalizeString(value).toLowerCase() === 'true';
}

function sendJson(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data),
  });
  res.end(data);
}

function validationError(message, code = 'validation_error') {
  const error = new Error(message);
  error.statusCode = 400;
  error.code = code;
  return error;
}

function normalizeLaneName(value) {
  return normalizeString(value).toLowerCase();
}

function validateLaneCatalog() {
  for (const [lane, config] of Object.entries(OPENROUTER_LANES)) {
    if (!config || config.provider !== 'openrouter') {
      throw new Error(`Invalid lane config for ${lane}`);
    }
    if (!Array.isArray(config.allowedModels) || config.allowedModels.length === 0) {
      throw new Error(`Lane ${lane} must declare at least one allowed model`);
    }
    if (!config.defaultModel || !config.allowedModels.includes(config.defaultModel)) {
      throw new Error(`Lane ${lane} must declare a default model from its allowlist`);
    }
  }
}

function inferTaskClass(body) {
  const explicitTaskClass = normalizeString(body?.task_class || body?.taskClass || body?.routing?.task_class);
  if (explicitTaskClass) return explicitTaskClass;

  const ctx = body?.context || {};
  const candidateValues = [
    ctx.task_class,
    ctx.taskClass,
    ctx?.payload?.task_class,
    ctx?.payload?.taskClass,
    ctx?.payload?.classification,
    ctx?.payload?.payload?.task_class,
    ctx?.payload?.payload?.taskClass,
    ctx?.payload?.input?.task_class,
    ctx?.payload?.input?.taskClass,
    ctx?.task?.task_class,
    ctx?.task?.taskClass,
    ctx?.task?.classification,
    ctx.classification,
  ];
  for (const value of candidateValues) {
    const normalized = normalizeString(value);
    if (normalized) return normalized;
  }

  const privacyHint = [ctx.visibility, ctx.privacy, ctx.dataSensitivity, ctx.scope]
    .map(normalizeString)
    .find(Boolean);
  if (privacyHint && ['private', 'local_only', 'local-only', 'sensitive'].includes(privacyHint.toLowerCase())) {
    return 'local_only_private';
  }

  const joinedHints = [
    ctx.issueTitle,
    ctx.issueDescription,
    ctx.prompt,
    ctx?.payload?.prompt,
    ctx?.payload?.issueTitle,
    ctx?.payload?.issueDescription,
  ].map(normalizeString).join(' ').toLowerCase();

  if (joinedHints.includes('review') || joinedHints.includes('audit')) return 'external_review';
  if (joinedHints.includes('summarize') || joinedHints.includes('summary')) return 'summarization';
  if (joinedHints.includes('code') || joinedHints.includes('bug') || joinedHints.includes('debug')) return 'code_reasoning';

  return 'general_chat';
}

function resolveLaneAndModel(body) {
  const requestedLane = normalizeLaneName(body?.lane);
  const requestedModel = normalizeString(body?.model);
  const legacyEnabled = OPENROUTER_LEGACY_DEFAULTS_ENABLED;
  const taskClass = inferTaskClass(body);

  if (!requestedLane && !requestedModel) {
    const bridgeRequest = buildBridgeRequest(
      { task_class: taskClass },
      { configPath: ROUTING_GOVERNOR_CONFIG_PATH }
    );
    if (bridgeRequest.blocked) {
      throw validationError(`Task class ${taskClass} is blocked from external bridge routing`, 'blocked_task_class');
    }
    const lane = normalizeLaneName(bridgeRequest.lane);
    const model = normalizeString(bridgeRequest.model);
    const laneConfig = OPENROUTER_LANES[lane];
    if (!laneConfig) {
      throw validationError(`Unsupported lane from routing governor: ${lane}`, 'unsupported_lane');
    }
    if (!laneConfig.allowedModels.includes(model)) {
      throw validationError(`Model ${model} is not allowed for lane ${lane}`, 'lane_model_not_allowed');
    }
    return {
      lane,
      model,
      laneConfig,
      legacyDefaultsUsed: false,
      compatibilityDefaultsUsed: { lane: false, model: false },
      taskClass,
      routing: bridgeRequest.routing,
      routingSource: 'governor',
    };
  }

  let lane = requestedLane;
  let model = requestedModel;
  const compatibilityDefaultsUsed = {
    lane: false,
    model: false,
  };

  if (!lane) {
    if (!legacyEnabled) {
      throw validationError('Missing lane for OpenRouter bridge request', 'missing_lane');
    }
    lane = OPENROUTER_LEGACY_DEFAULT_LANE || 'openrouter_general';
    compatibilityDefaultsUsed.lane = true;
  }

  const laneConfig = OPENROUTER_LANES[lane];
  if (!laneConfig) {
    throw validationError(`Unsupported lane: ${lane}`, 'unsupported_lane');
  }

  if (!model) {
    if (!legacyEnabled) {
      throw validationError(`Missing model for lane ${lane}`, 'missing_model');
    }
    model = OPENROUTER_LEGACY_DEFAULT_MODEL || laneConfig.defaultModel;
    compatibilityDefaultsUsed.model = true;
  }

  if (!laneConfig.allowedModels.includes(model)) {
    throw validationError(`Model ${model} is not allowed for lane ${lane}`, 'lane_model_not_allowed');
  }

  return {
    lane,
    model,
    laneConfig,
    legacyDefaultsUsed: compatibilityDefaultsUsed.lane || compatibilityDefaultsUsed.model,
    compatibilityDefaultsUsed,
    taskClass,
    routing: body?.routing || null,
    routingSource: 'direct',
  };
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw validationError('Invalid JSON body', 'invalid_json');
  }
}

function buildPrompt(body) {
  const ctx = body?.context || {};
  const parts = [];
  if (ctx.issueTitle) parts.push(`Issue: ${ctx.issueTitle}`);
  if (ctx.issueDescription) parts.push(`Description:\n${ctx.issueDescription}`);
  if (ctx.prompt) parts.push(`Prompt:\n${ctx.prompt}`);
  if (ctx.task && typeof ctx.task === 'object') parts.push(`Task JSON:\n${JSON.stringify(ctx.task, null, 2)}`);
  if (parts.length === 0) parts.push(`Paperclip context:\n${JSON.stringify(ctx, null, 2)}`);
  return parts.join('\n\n');
}

function buildTaskPrompt(body) {
  const inputs = body?.inputs && typeof body.inputs === 'object' ? body.inputs : {};
  const contextNotes = Array.isArray(inputs.context_notes) ? inputs.context_notes : [];
  const requiredOutput = Array.isArray(body?.required_output) ? body.required_output : [];
  const content = normalizeString(inputs.content || body?.content);
  const reviewType = normalizeString(inputs.review_type || body?.review_type);
  const taskSummary = normalizeString(body?.task_summary);
  const lines = [
    `Task class: ${normalizeString(body?.task_class) || 'unknown'}`,
    `Review type: ${reviewType || 'unspecified'}`,
    `Task summary: ${taskSummary || 'none provided'}`,
    `Content:\n${content || 'none provided'}`,
  ];
  if (contextNotes.length) {
    lines.push(`Context notes:\n- ${contextNotes.join('\n- ')}`);
  }
  if (requiredOutput.length) {
    lines.push(`Required output fields:\n- ${requiredOutput.join('\n- ')}`);
  }
  return lines.join('\n\n');
}

function getExternalReviewResultSchema() {
  return {
    type: 'object',
    additionalProperties: false,
    required: [
      'decision',
      'confidence',
      'top_risks',
      'recommended_next_step',
      'escalation_suggested',
      'routing_metadata',
    ],
    properties: {
      decision: { type: 'string' },
      confidence: { type: 'number' },
      top_risks: {
        type: 'array',
        maxItems: 3,
        items: {
          anyOf: [
            { type: 'string' },
            {
              type: 'object',
              additionalProperties: true,
              required: ['description'],
              properties: {
                risk_id: { type: 'string' },
                category: { type: 'string' },
                severity: { type: 'string' },
                description: { type: 'string' },
              },
            },
          ],
        },
      },
      recommended_next_step: { type: 'string' },
      escalation_suggested: { type: 'boolean' },
      routing_metadata: {
        type: 'object',
        additionalProperties: true,
      },
    },
  };
}

function stripMarkdownFences(value) {
  const raw = normalizeString(value);
  return raw
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/```$/i, '')
    .trim();
}

function extractJsonObject(value) {
  const stripped = stripMarkdownFences(value);
  const firstBrace = stripped.indexOf('{');
  const lastBrace = stripped.lastIndexOf('}');
  if (firstBrace === -1 || lastBrace === -1 || lastBrace < firstBrace) {
    return stripped;
  }
  return stripped.slice(firstBrace, lastBrace + 1);
}

function parseJsonCandidate(value) {
  const candidate = extractJsonObject(value);
  return candidate ? JSON.parse(candidate) : null;
}

function validateAgainstSchema(schema, value, pathName = 'result') {
  if (!schema || typeof schema !== 'object') return [];
  const errors = [];
  const actualType = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value;

  if (schema.anyOf && Array.isArray(schema.anyOf)) {
    const variantErrors = schema.anyOf.map((variant) => validateAgainstSchema(variant, value, pathName));
    if (variantErrors.some((errs) => errs.length === 0)) return [];
    return variantErrors[0] || [`${pathName} does not match any allowed schema variant`];
  }

  if (schema.type === 'object') {
    if (actualType !== 'object' || Array.isArray(value) || value === null) {
      return [`${pathName} must be an object`];
    }
    const required = Array.isArray(schema.required) ? schema.required : [];
    for (const key of required) {
      if (!(key in value)) errors.push(`${pathName}.${key} is required`);
    }
    if (schema.properties && typeof schema.properties === 'object') {
      for (const [key, propertySchema] of Object.entries(schema.properties)) {
        if (key in value) {
          errors.push(...validateAgainstSchema(propertySchema, value[key], `${pathName}.${key}`));
        }
      }
    }
    if (schema.additionalProperties === false && schema.properties) {
      for (const key of Object.keys(value)) {
        if (!(key in schema.properties)) errors.push(`${pathName}.${key} is not allowed`);
      }
    }
    return errors;
  }

  if (schema.type === 'array') {
    if (!Array.isArray(value)) return [`${pathName} must be an array`];
    if (typeof schema.maxItems === 'number' && value.length > schema.maxItems) {
      errors.push(`${pathName} must contain at most ${schema.maxItems} items`);
    }
    if (schema.items) {
      value.forEach((item, index) => {
        errors.push(...validateAgainstSchema(schema.items, item, `${pathName}[${index}]`));
      });
    }
    return errors;
  }

  if (schema.type === 'string' && actualType !== 'string') {
    return [`${pathName} must be a string`];
  }
  if (schema.type === 'number' && actualType !== 'number') {
    return [`${pathName} must be a number`];
  }
  if (schema.type === 'boolean' && actualType !== 'boolean') {
    return [`${pathName} must be a boolean`];
  }

  return errors;
}

function coerceParsedExternalReviewResult(parsed, routingMetadata) {
  const topRisks = Array.isArray(parsed?.top_risks) ? parsed.top_risks.slice(0, 3) : [];
  const confidenceValue = typeof parsed?.confidence === 'number' ? parsed.confidence : Number(parsed?.confidence);
  return {
    decision: normalizeString(parsed?.decision),
    confidence: Number.isFinite(confidenceValue) ? confidenceValue : 0,
    top_risks: topRisks.map((item) => {
      if (typeof item === 'string') return item.trim();
      if (item && typeof item === 'object') {
        return {
          ...item,
          description: normalizeString(item.description),
        };
      }
      return String(item);
    }).filter(Boolean),
    recommended_next_step: normalizeString(parsed?.recommended_next_step),
    escalation_suggested: Boolean(parsed?.escalation_suggested),
    routing_metadata: {
      ...(parsed?.routing_metadata && typeof parsed.routing_metadata === 'object' ? parsed.routing_metadata : {}),
      ...(routingMetadata && typeof routingMetadata === 'object' ? routingMetadata : {}),
    },
  };
}

function buildExternalReviewRepairPrompt(rawOutput, validationErrors) {
  return [
    'Your previous response was invalid.',
    'Return ONLY valid minified JSON with exactly these keys: decision, confidence, top_risks, recommended_next_step, escalation_suggested, routing_metadata.',
    `Validation errors: ${validationErrors.join('; ')}`,
    `Previous invalid output:\n${normalizeString(rawOutput) || '(empty)'}`,
  ].join('\n\n');
}

async function requestOpenRouterChat({ model, systemPrompt, userPrompt, maxTokens, responseFormat }) {
  const payload = {
    model,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt },
    ],
    max_tokens: maxTokens,
  };
  if (responseFormat) payload.response_format = responseFormat;

  const upstream = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'http://127.0.0.1:3100',
      'X-Title': 'Paperclip Typed Task Transport',
    },
    body: JSON.stringify(payload),
  });

  const data = await upstream.json();
  return { upstream, data };
}

function enforceExternalReviewOutput(rawContent, routingMetadata) {
  const schema = getExternalReviewResultSchema();
  const parsed = parseJsonCandidate(rawContent);
  const normalized = coerceParsedExternalReviewResult(parsed, routingMetadata);
  const validationErrors = validateAgainstSchema(schema, normalized);
  return {
    parsed,
    normalized,
    validationErrors,
  };
}

function validateTypedTaskPacket(body) {
  const agent = normalizeString(body?.agent);
  const taskClass = normalizeString(body?.task_class);
  if (agent !== 'external_review') {
    throw validationError('Unsupported specialist agent for /task transport', 'unsupported_specialist_agent');
  }
  if (taskClass !== 'external_review') {
    throw validationError('External Review Agent only accepts task_class=external_review', 'unsupported_task_class');
  }
  const inputs = body?.inputs && typeof body.inputs === 'object' ? body.inputs : null;
  if (!normalizeString(body?.task_summary)) {
    throw validationError('Missing required field: task_summary', 'invalid_packet');
  }
  if (!inputs) {
    throw validationError('Missing required field: inputs', 'invalid_packet');
  }
  if (!normalizeString(inputs.review_type || body?.review_type)) {
    throw validationError('Missing required field: review_type', 'invalid_packet');
  }
  if (!normalizeString(inputs.content || body?.content)) {
    throw validationError('Missing required field: content', 'invalid_packet');
  }
  const requiredOutput = Array.isArray(body?.required_output) ? body.required_output : [];
  if (requiredOutput.length === 0) {
    throw validationError('Missing required field: required_output', 'invalid_packet');
  }
  return {
    agent,
    taskClass,
    reviewType: normalizeString(inputs.review_type || body?.review_type),
    content: normalizeString(inputs.content || body?.content),
    taskSummary: normalizeString(body?.task_summary),
    contextNotes: Array.isArray(inputs.context_notes) ? inputs.context_notes.map(normalizeString).filter(Boolean) : [],
    requiredOutput: requiredOutput.map(normalizeString).filter(Boolean),
  };
}

function buildHealthResponse() {
  return {
    ok: true,
    provider: 'openrouter',
    legacy_defaults_enabled: OPENROUTER_LEGACY_DEFAULTS_ENABLED,
    routing_governor_config_path: ROUTING_GOVERNOR_CONFIG_PATH,
    lanes: Object.entries(OPENROUTER_LANES).map(([lane, config]) => ({
      lane,
      default_model: config.defaultModel,
      allowed_models: [...config.allowedModels],
    })),
  };
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'HEAD' && (req.url === '/health' || req.url === '/run')) {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.method === 'GET' && req.url === '/health') {
    return sendJson(res, 200, buildHealthResponse());
  }

  if (req.method === 'POST' && req.url === '/task') {
    try {
      const body = await readBody(req);
      const packet = validateTypedTaskPacket(body);
      const bridgeRequest = buildBridgeRequest(
        { task_class: packet.taskClass },
        { configPath: ROUTING_GOVERNOR_CONFIG_PATH }
      );
      if (bridgeRequest.blocked) {
        throw validationError(`Task class ${packet.taskClass} is blocked from typed task transport`, 'blocked_task_class');
      }
      const lane = normalizeLaneName(bridgeRequest.lane);
      const model = normalizeString(bridgeRequest.model);
      const laneConfig = OPENROUTER_LANES[lane];
      if (!laneConfig) {
        throw validationError(`Unsupported lane from routing governor: ${lane}`, 'unsupported_lane');
      }

      const schema = getExternalReviewResultSchema();
      const systemPrompt = 'You are the External Review Agent. Return ONLY valid minified JSON with exactly these top-level keys: decision, confidence, top_risks, recommended_next_step, escalation_suggested, routing_metadata. No markdown fences. No prose.';
      const userPrompt = buildTaskPrompt(body);
      const maxTokens = Number.isInteger(body?.max_tokens) && body.max_tokens > 0 ? body.max_tokens : 260;
      const routingMetadata = {
        ...(bridgeRequest.routing || {}),
        selected_lane: lane,
        selected_model: model,
        provider: laneConfig.provider,
      };

      let firstAttempt = await requestOpenRouterChat({
        model,
        systemPrompt,
        userPrompt,
        maxTokens,
        responseFormat: { type: 'json_object' },
      });

      if (!firstAttempt.upstream.ok) {
        return sendJson(res, 502, {
          ok: false,
          error: 'openrouter_request_failed',
          lane,
          model,
          details: firstAttempt.data,
        });
      }

      const rawContent = firstAttempt.data?.choices?.[0]?.message?.content || '';
      let validationErrors = [];

      try {
        const enforced = enforceExternalReviewOutput(rawContent, routingMetadata);
        validationErrors = enforced.validationErrors;
        if (validationErrors.length === 0) {
          return sendJson(res, 200, {
            ok: true,
            agent: packet.agent,
            task_class: packet.taskClass,
            lane,
            model,
            summary: `OpenRouter ${model}`,
            result: enforced.normalized,
            usage: firstAttempt.data?.usage || null,
            provider: firstAttempt.data?.provider || laneConfig.provider,
            routing: bridgeRequest.routing,
            raw_result: rawContent,
          });
        }
      } catch (error) {
        validationErrors = [error instanceof Error ? error.message : 'invalid_json_output'];
      }

      const repairAttempt = await requestOpenRouterChat({
        model,
        systemPrompt,
        userPrompt: buildExternalReviewRepairPrompt(rawContent, validationErrors),
        maxTokens: 220,
      });

      if (!repairAttempt.upstream.ok) {
        return sendJson(res, 502, {
          ok: false,
          error: 'openrouter_repair_failed',
          lane,
          model,
          details: repairAttempt.data,
        });
      }

      const repairedRaw = repairAttempt.data?.choices?.[0]?.message?.content || '';
      try {
        const repaired = enforceExternalReviewOutput(repairedRaw, routingMetadata);
        if (repaired.validationErrors.length === 0) {
          return sendJson(res, 200, {
            ok: true,
            agent: packet.agent,
            task_class: packet.taskClass,
            lane,
            model,
            summary: `OpenRouter ${model}`,
            result: repaired.normalized,
            usage: repairAttempt.data?.usage || firstAttempt.data?.usage || null,
            provider: repairAttempt.data?.provider || laneConfig.provider,
            routing: bridgeRequest.routing,
            raw_result: repairedRaw,
            repaired: true,
          });
        }
        return sendJson(res, 422, {
          ok: false,
          error: 'invalid_model_output',
          lane,
          model,
          validation_errors: repaired.validationErrors,
          raw_result: repairedRaw,
          routing: bridgeRequest.routing,
        });
      } catch (error) {
        return sendJson(res, 422, {
          ok: false,
          error: 'invalid_model_output',
          lane,
          model,
          validation_errors: [error instanceof Error ? error.message : 'invalid_json_output'],
          raw_result: repairedRaw,
          routing: bridgeRequest.routing,
        });
      }
    } catch (err) {
      const statusCode = err && typeof err.statusCode === 'number' ? err.statusCode : 500;
      const code = err && typeof err.code === 'string' ? err.code : 'internal_error';
      return sendJson(res, statusCode, {
        ok: false,
        error: code,
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  if (req.method !== 'POST' || req.url !== '/run') {
    return sendJson(res, 404, { error: 'Not found' });
  }

  try {
    const body = await readBody(req);
    if (process.env.PAPERCLIP_BRIDGE_TRACE_REQUESTS === 'true') {
      try {
        console.error('[paperclip-openrouter-bridge] request body:', JSON.stringify(body));
      } catch {}
    }
    const { lane, model, laneConfig, legacyDefaultsUsed, compatibilityDefaultsUsed, taskClass, routing, routingSource } = resolveLaneAndModel(body);
    const prompt = buildPrompt(body);
    const systemPrompt =
      typeof body?.system_prompt === 'string' && body.system_prompt.trim()
        ? body.system_prompt.trim()
        : 'You are a Paperclip agent backend. Respond concisely and use plain text.';
    const maxTokens = Number.isInteger(body?.max_tokens) && body.max_tokens > 0 ? body.max_tokens : 700;

    const upstream = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'http://127.0.0.1:3100',
        'X-Title': 'Paperclip OpenRouter Bridge',
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        max_tokens: maxTokens,
      }),
    });

    const data = await upstream.json();
    if (!upstream.ok) {
      return sendJson(res, 502, {
        ok: false,
        error: 'openrouter_request_failed',
        lane,
        model,
        details: data,
      });
    }

    const content = data?.choices?.[0]?.message?.content || 'No response content.';
    return sendJson(res, 200, {
      ok: true,
      lane,
      model,
      summary: `OpenRouter ${model}`,
      content,
      usage: data?.usage || null,
      provider: data?.provider || laneConfig.provider,
      legacy_defaults_used: legacyDefaultsUsed,
      compatibility_defaults_used: compatibilityDefaultsUsed,
      task_class: taskClass,
      routing_source: routingSource,
      routing,
    });
  } catch (err) {
    const statusCode = err && typeof err.statusCode === 'number' ? err.statusCode : 500;
    const code = err && typeof err.code === 'string' ? err.code : 'internal_error';
    return sendJson(res, statusCode, {
      ok: false,
      error: code,
      message: err instanceof Error ? err.message : String(err),
    });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`paperclip-openrouter-bridge listening on http://127.0.0.1:${PORT}`);
});
