#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const DEFAULT_CONFIG_PATH = path.join(__dirname, '..', 'reports', 'paperclip-routing-governor-config-v2-2026-04-16.json');

function routingError(message, code) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function normalizeString(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeTaskClass(value) {
  return normalizeString(value);
}

function normalizeAgentHint(input) {
  const candidates = [
    input?.agent_hint,
    input?.agentHint,
    input?.reviewer_hint,
    input?.reviewerHint,
    input?.agent_role,
    input?.agentRole,
    input?.context?.agent_hint,
    input?.context?.agentHint,
    input?.context?.reviewer_hint,
    input?.context?.reviewerHint,
    input?.context?.agent_role,
    input?.context?.agentRole,
    input?.context?.agent?.name,
    input?.context?.agentName,
    input?.context?.agent?.title,
  ];
  for (const value of candidates) {
    const normalized = normalizeString(value).toLowerCase();
    if (normalized) return normalized;
  }
  return '';
}

function readJsonFile(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      throw routingError(`Routing Governor config not found: ${filePath}`, 'config_not_found');
    }
    throw routingError(`Routing Governor config is invalid: ${filePath}`, 'invalid_config');
  }
}

function validateRoutingGovernorConfig(config) {
  if (!config || typeof config !== 'object') {
    throw routingError('Routing Governor config must be an object', 'invalid_config');
  }
  if (typeof config.version !== 'number') {
    throw routingError('Routing Governor config must declare numeric version', 'invalid_config');
  }
  if (!config.policy_version || typeof config.policy_version !== 'string') {
    throw routingError('Routing Governor config must declare policy_version', 'invalid_config');
  }
  if (!config.task_policy || typeof config.task_policy !== 'object') {
    throw routingError('Routing Governor config is missing task_policy', 'invalid_config');
  }
  if (!config.lanes || typeof config.lanes !== 'object') {
    throw routingError('Routing Governor config is missing lanes', 'invalid_config');
  }
  if (config.excluded_models != null && !Array.isArray(config.excluded_models)) {
    throw routingError('Routing Governor config excluded_models must be an array when present', 'invalid_config');
  }

  for (const [taskClass, taskPolicy] of Object.entries(config.task_policy)) {
    if (!taskPolicy || typeof taskPolicy !== 'object') {
      throw routingError(`Task policy for ${taskClass} must be an object`, 'invalid_config');
    }
    if (!normalizeString(taskPolicy.primary)) {
      throw routingError(`Task policy for ${taskClass} must declare primary lane`, 'invalid_config');
    }
    if (!config.lanes[taskPolicy.primary]) {
      throw routingError(`Task policy for ${taskClass} references missing primary lane ${taskPolicy.primary}`, 'invalid_config');
    }
    const fallback = Array.isArray(taskPolicy.fallback) ? taskPolicy.fallback : [];
    for (const laneName of fallback) {
      if (!config.lanes[laneName]) {
        throw routingError(`Task policy for ${taskClass} references missing fallback lane ${laneName}`, 'invalid_config');
      }
    }
  }

  for (const [laneName, lane] of Object.entries(config.lanes)) {
    if (!lane || typeof lane !== 'object') {
      throw routingError(`Lane ${laneName} must be an object`, 'invalid_config');
    }
    const provider = normalizeString(lane.provider);
    if (!provider) {
      throw routingError(`Lane ${laneName} must declare provider`, 'invalid_config');
    }
    if (provider === 'blocked' && lane.model !== null) {
      throw routingError(`Blocked lane ${laneName} must not declare a model`, 'invalid_config');
    }
    if (provider !== 'blocked' && provider !== 'local' && !normalizeString(lane.model)) {
      throw routingError(`Lane ${laneName} must declare model unless provider is blocked/local`, 'invalid_config');
    }
  }

  return config;
}

function loadRoutingGovernorConfig(configPath = DEFAULT_CONFIG_PATH) {
  return validateRoutingGovernorConfig(readJsonFile(configPath));
}

function getTaskClassSet(config) {
  return new Set(Object.keys(config.task_policy || {}));
}

function validateLaneForTaskClass(config, taskClass, laneName, role) {
  const lane = config.lanes?.[laneName];
  if (!lane) {
    throw routingError(`No permitted route exists for task_class ${taskClass}: missing ${role} lane ${laneName}`, 'no_permitted_route');
  }
  const provider = normalizeString(lane.provider);
  if ((taskClass === 'local_only_private' || taskClass === 'admin_sensitive') && provider !== 'local') {
    throw routingError(`${taskClass} cannot route to non-local lane ${laneName}`, 'privacy_violation');
  }
  const useCases = Array.isArray(lane.use_cases) ? lane.use_cases : [];
  if (!useCases.includes(taskClass)) {
    throw routingError(`No permitted route exists for task_class ${taskClass}: lane ${laneName} does not permit it`, 'no_permitted_route');
  }
  return lane;
}

function buildFallbackChain(config, taskClass, fallbackLaneNames) {
  return fallbackLaneNames.map((laneName) => {
    const lane = validateLaneForTaskClass(config, taskClass, laneName, 'fallback');
    return {
      lane: laneName,
      provider: lane.provider,
      model: lane.model,
    };
  });
}

function makeCorrelationId(input) {
  const explicit = normalizeString(input?.correlation_id || input?.request_id || input?.run_id);
  if (explicit) return explicit;
  return crypto.randomUUID();
}

function routeRoutingRequest(input, options = {}) {
  const config = options.config || loadRoutingGovernorConfig(options.configPath);
  const taskClass = normalizeTaskClass(input?.task_class);
  const supportedTaskClasses = getTaskClassSet(config);

  if (!supportedTaskClasses.has(taskClass)) {
    throw routingError(`Unsupported task_class for Routing Governor v${config.version}: ${taskClass || '(missing)'}`, 'unsupported_task_class');
  }

  const taskPolicy = config.task_policy?.[taskClass];
  if (!taskPolicy || !taskPolicy.primary) {
    throw routingError(`No permitted route exists for task_class ${taskClass}`, 'no_permitted_route');
  }

  const agentHint = normalizeAgentHint(input);
  const hintLaneMap = config.agent_hint_policy && typeof config.agent_hint_policy === 'object'
    ? config.agent_hint_policy
    : {};
  const hintedLaneName = agentHint && hintLaneMap[agentHint] ? hintLaneMap[agentHint] : null;
  const selectedLaneName = hintedLaneName || taskPolicy.primary;
  const selectedLane = validateLaneForTaskClass(config, taskClass, selectedLaneName, 'primary');
  const fallbackChain = buildFallbackChain(config, taskClass, Array.isArray(taskPolicy.fallback) ? taskPolicy.fallback : []);
  const maxEstimatedCost = Number(selectedLane.max_estimated_cost_usd);
  const budgetLimit = Number(config.budget_policy?.default_max_estimated_cost_usd);
  const provider = normalizeString(selectedLane.provider);
  const blocked = provider === 'blocked';
  const requiresManualApproval = taskPolicy.requires_manual_approval === true;
  const premium = selectedLane.premium === true;
  const premiumAllowed = taskPolicy.premium_allowed === true;
  const certificationRequired = selectedLane.certification_required === true;
  const correlationId = makeCorrelationId(input);
  const excludedModels = Array.isArray(config.excluded_models) ? config.excluded_models : [];
  const exclusion = excludedModels.find((entry) => normalizeString(entry?.model) === normalizeString(selectedLane.model));

  if (exclusion) {
    throw routingError(`Model ${selectedLane.model} is excluded: ${normalizeString(exclusion.reason) || 'no reason provided'}`, 'excluded_model');
  }

  if (premium && !premiumAllowed && config.budget_policy?.premium_without_explicit_approval === false) {
    throw routingError(`Premium lane ${selectedLaneName} is not permitted for task_class ${taskClass}`, 'budget_blocked');
  }

  const budgetApproved = blocked
    ? true
    : (Number.isFinite(maxEstimatedCost) && Number.isFinite(budgetLimit)
      ? maxEstimatedCost <= budgetLimit || premiumAllowed
      : premiumAllowed !== false);

  if (!budgetApproved && config.budget_policy?.block_on_budget_exceeded === true) {
    throw routingError(`Budget blocked lane ${selectedLaneName} for task_class ${taskClass}`, 'budget_blocked');
  }

  const decision = {
    task_class: taskClass,
    selected_lane: selectedLaneName,
    selected_provider: selectedLane.provider,
    selected_model: selectedLane.model,
    provider: selectedLane.provider,
    model: selectedLane.model,
    policy_version: config.policy_version || null,
    reason: blocked
      ? `Routing Governor v${config.version} blocked ${taskClass} via ${selectedLaneName}.`
      : hintedLaneName
        ? `Routing Governor v${config.version} selected ${selectedLaneName} for ${taskClass} using agent hint ${agentHint}.`
        : `Routing Governor v${config.version} selected ${selectedLaneName} for ${taskClass}.`,
    agent_hint: agentHint || null,
    fallbacks_tried: [],
    fallback_chain: fallbackChain,
    requires_approval: requiresManualApproval,
    requires_manual_approval: requiresManualApproval,
    priority: taskPolicy.priority || null,
    budget_approved: budgetApproved,
    max_estimated_cost_usd: Number.isFinite(maxEstimatedCost) ? maxEstimatedCost : null,
    blocked,
    certification_required: certificationRequired,
    excluded_model_reason: null,
    correlation_id: correlationId,
  };

  return decision;
}

function buildClaudeCompactContract(taskClass) {
  if (taskClass === 'recon_scoring') {
    return {
      response_format: 'json_compact',
      system_prompt: 'You are performing DealerScope wholesale arbitrage evaluation. Return strict minified JSON only with exactly these keys in this order: verdict, confidence, score, max_bid, top_risks, rationale. Constraints: verdict is one word BUY or PASS. confidence and score are decimals 0 to 1. max_bid is integer dollars. top_risks is an array of exactly 3 short strings, each under 80 characters. rationale is one short sentence under 220 characters. No markdown. No extra keys. No safety or policy commentary.',
      output_contract: {
        type: 'json_compact',
        ordered_keys: ['verdict', 'confidence', 'score', 'max_bid', 'top_risks', 'rationale'],
        top_risks_count: 3,
        rationale_max_chars: 220,
      },
    };
  }

  if (taskClass === 'deal_adjudication') {
    return {
      response_format: 'json_compact',
      system_prompt: 'Return strict minified JSON only with exactly these keys in this order: approve, confidence, max_bid, all_in_cost, ratio_to_mmr, gross_profit, rationale. Constraints: approve is boolean. confidence and ratio_to_mmr are decimals. max_bid, all_in_cost, and gross_profit are integer dollars. rationale is one short sentence under 240 characters. No markdown. No extra keys.',
      output_contract: {
        type: 'json_compact',
        ordered_keys: ['approve', 'confidence', 'max_bid', 'all_in_cost', 'ratio_to_mmr', 'gross_profit', 'rationale'],
        rationale_max_chars: 240,
      },
    };
  }

  if (taskClass === 'premium_judgment' || taskClass === 'market_intel_financial') {
    return {
      response_format: 'json_compact',
      system_prompt: 'Return strict minified JSON only with exactly these keys in this order: verdict, confidence, key_points, recommendation. Constraints: key_points is an array of at most 4 short strings, recommendation is one short sentence under 240 characters. No markdown. No extra keys.',
      output_contract: {
        type: 'json_compact',
        ordered_keys: ['verdict', 'confidence', 'key_points', 'recommendation'],
        key_points_max_count: 4,
        recommendation_max_chars: 240,
      },
    };
  }

  return null;
}

function buildBridgeRequest(input, options = {}) {
  const decision = routeRoutingRequest(input, options);
  const bridgeRequest = {
    lane: decision.selected_lane,
    model: decision.model,
    blocked: decision.blocked,
    routing: {
      task_class: decision.task_class,
      policy_version: decision.policy_version,
      reason: decision.reason,
      requires_manual_approval: decision.requires_manual_approval,
      correlation_id: decision.correlation_id,
    },
  };

  if (decision.selected_lane === 'openrouter_claude_premium') {
    const claudeContract = buildClaudeCompactContract(decision.task_class);
    if (claudeContract) {
      bridgeRequest.contract = claudeContract;
    }
  }

  return bridgeRequest;
}

function parseCliArgs(argv) {
  const args = { raw: null, dryRun: false, taskClass: null, configPath: null };
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--dry-run') {
      args.dryRun = true;
      continue;
    }
    if (token === '--task-class') {
      args.taskClass = argv[i + 1] || null;
      i += 1;
      continue;
    }
    if (token === '--config') {
      args.configPath = argv[i + 1] || null;
      i += 1;
      continue;
    }
    if (!args.raw) {
      args.raw = token;
    }
  }
  return args;
}

function demoCli() {
  const args = parseCliArgs(process.argv);
  const configPath = args.configPath || DEFAULT_CONFIG_PATH;
  const input = args.taskClass
    ? { task_class: args.taskClass }
    : args.raw
      ? JSON.parse(args.raw)
      : { task_class: 'general_chat' };

  const decision = routeRoutingRequest(input, { configPath });
  process.stdout.write(`${JSON.stringify(decision, null, 2)}\n`);
}

if (require.main === module) {
  try {
    demoCli();
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  DEFAULT_CONFIG_PATH,
  validateRoutingGovernorConfig,
  loadRoutingGovernorConfig,
  routeRoutingRequest,
  buildBridgeRequest,
  buildClaudeCompactContract,
};
