import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

const REVIEW_HISTORY_KEY = "external-review-history-v1";
const COMPANY_HISTORY_KEY = "external-review-history-company-v1";
const REVIEW_HISTORY_LIMIT = 20;

function firstNonEmpty(...values) {
  for (const value of values) {
    const normalized = typeof value === "string" ? value.trim() : "";
    if (normalized) return normalized;
  }
  return "";
}

function deriveContent(params) {
  const direct = firstNonEmpty(params?.content, params?.text, params?.prompt, params?.description, params?.notes);
  if (direct) return direct;

  const context = params?.context && typeof params.context === "object" ? params.context : null;
  const contextBits = [
    firstNonEmpty(params?.entityType),
    firstNonEmpty(params?.entityId),
    firstNonEmpty(context?.source),
    firstNonEmpty(context?.title),
    firstNonEmpty(context?.parentEntityId),
    firstNonEmpty(context?.projectId),
  ].filter(Boolean);

  if (contextBits.length > 0) {
    return `Review request from plugin launcher context: ${contextBits.join(" | ")}`;
  }

  return "Please review the current agent context and provide a decision, risks, and recommended next step.";
}

function normalizeHistoryEntry(input = {}) {
  return {
    id: firstNonEmpty(input.id, `${Date.now()}`),
    createdAtLabel: firstNonEmpty(input.createdAtLabel, new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })),
    createdAtMs: Number.isFinite(Number(input.createdAtMs)) ? Number(input.createdAtMs) : Date.now(),
    taskSummary: firstNonEmpty(input.taskSummary, "External review request"),
    reviewType: firstNonEmpty(input.reviewType, "architecture_review"),
    priority: firstNonEmpty(input.priority, "normal"),
    content: typeof input.content === "string" ? input.content : "",
    contextNotes: typeof input.contextNotes === "string" ? input.contextNotes : "",
    decision: firstNonEmpty(input.decision),
    recommendedNextStep: firstNonEmpty(input.recommendedNextStep),
    lane: firstNonEmpty(input.lane),
    model: firstNonEmpty(input.model),
    outcome: firstNonEmpty(input.outcome),
  };
}

function buildScopeKey(scopeId) {
  return scopeId ? `${REVIEW_HISTORY_KEY}:${scopeId}` : REVIEW_HISTORY_KEY;
}

async function readHistory(ctx, companyId, scopeId) {
  const stored = await ctx.state.get({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: buildScopeKey(scopeId),
  });
  return Array.isArray(stored) ? stored.map((item) => normalizeHistoryEntry(item)) : [];
}

async function writeHistory(ctx, companyId, scopeId, entries) {
  await ctx.state.set({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: buildScopeKey(scopeId),
  }, entries.slice(0, REVIEW_HISTORY_LIMIT));
}

async function readCompanyHistory(ctx, companyId) {
  const stored = await ctx.state.get({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: COMPANY_HISTORY_KEY,
  });
  return Array.isArray(stored) ? stored.map((item) => normalizeHistoryEntry(item)) : [];
}

async function writeCompanyHistory(ctx, companyId, entries) {
  await ctx.state.set({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: COMPANY_HISTORY_KEY,
  }, entries.slice(0, REVIEW_HISTORY_LIMIT));
}

async function syncHistoryWrite(ctx, companyId, scopeId, entry) {
  const scopedHistory = await readHistory(ctx, companyId, scopeId);
  const nextScoped = [entry, ...scopedHistory.filter((item) => item.id !== entry.id)].slice(0, REVIEW_HISTORY_LIMIT);
  await writeHistory(ctx, companyId, scopeId, nextScoped);

  const companyHistory = await readCompanyHistory(ctx, companyId);
  const nextCompany = [
    { ...entry, scopeId: firstNonEmpty(scopeId) || null },
    ...companyHistory.filter((item) => item.id !== entry.id)
  ].slice(0, REVIEW_HISTORY_LIMIT);
  await writeCompanyHistory(ctx, companyId, nextCompany);

  return { scoped: nextScoped, company: nextCompany };
}

async function syncOutcomeWrite(ctx, companyId, scopeId, entryId, outcome) {
  const scopedHistory = await readHistory(ctx, companyId, scopeId);
  const nextScoped = scopedHistory.map((item) => item.id === entryId ? { ...item, outcome } : item);
  await writeHistory(ctx, companyId, scopeId, nextScoped);

  const companyHistory = await readCompanyHistory(ctx, companyId);
  const nextCompany = companyHistory.map((item) => item.id === entryId ? { ...item, outcome } : item);
  await writeCompanyHistory(ctx, companyId, nextCompany);

  return { scoped: nextScoped, company: nextCompany };
}

async function clearScopedHistory(ctx, companyId, scopeId) {
  const scopedHistory = await readHistory(ctx, companyId, scopeId);
  const scopedIds = new Set(scopedHistory.map((item) => item.id));
  await writeHistory(ctx, companyId, scopeId, []);

  if (scopedIds.size > 0) {
    const companyHistory = await readCompanyHistory(ctx, companyId);
    const nextCompany = companyHistory.filter((item) => !scopedIds.has(item.id));
    await writeCompanyHistory(ctx, companyId, nextCompany);
    return { scoped: [], company: nextCompany };
  }

  return { scoped: [], company: await readCompanyHistory(ctx, companyId) };
}

const plugin = definePlugin({
  id: "local.external-review-ui-v2",
  displayName: "External Review UI",
  version: "0.0.4",
  capabilities: ["agents.invoke", "plugin.state.read", "plugin.state.write"],
  async setup(ctx) {
    ctx.data.register("review_history", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      if (!companyId) {
        throw new Error("companyId is required to load review history");
      }
      const scoped = await readHistory(ctx, companyId, scopeId);
      const company = await readCompanyHistory(ctx, companyId);
      return { scoped, company };
    });

    ctx.actions.register("save_review_history", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      if (!companyId) {
        throw new Error("companyId is required to save review history");
      }
      const entry = normalizeHistoryEntry(params?.entry || {});
      return await syncHistoryWrite(ctx, companyId, scopeId, entry);
    });

    ctx.actions.register("set_review_outcome", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      const entryId = firstNonEmpty(params?.entryId);
      const outcome = firstNonEmpty(params?.outcome);
      if (!companyId || !entryId) {
        throw new Error("companyId and entryId are required to update review outcome");
      }
      return await syncOutcomeWrite(ctx, companyId, scopeId, entryId, outcome);
    });

    ctx.actions.register("clear_review_history", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      if (!companyId) {
        throw new Error("companyId is required to clear review history");
      }
      return await clearScopedHistory(ctx, companyId, scopeId);
    });

    ctx.actions.register("invoke_external_review", async (params) => {
      const agentId = firstNonEmpty(
        params?.agentId,
        params?.entityType === "agent" ? params?.entityId : "",
        params?.agent?.id
      );
      const companyId = firstNonEmpty(params?.companyId, params?.company?.id, params?.context?.companyId);
      const taskSummary = firstNonEmpty(
        params?.taskSummary,
        params?.title,
        params?.context?.title,
        params?.entityType === "agent" && params?.entityId ? `External review for agent ${params.entityId}` : "",
        "External review request"
      );
      const content = deriveContent(params);
      const reviewType = firstNonEmpty(params?.reviewType, "architecture_review");
      const priority = firstNonEmpty(params?.priority, "normal");
      const contextNotes = Array.isArray(params?.contextNotes)
        ? params.contextNotes.map((v) => String(v))
        : typeof params?.contextNotes === "string" && params.contextNotes.trim().length > 0
          ? [params.contextNotes]
          : [];

      if (!agentId || !companyId) {
        throw new Error("Plugin launcher context must provide a valid agent entity and companyId");
      }

      return await ctx.agents.invokeSpecialist(agentId, companyId, {
        specialist: "external_review",
        taskClass: "external_review",
        taskSummary,
        inputs: {
          review_type: reviewType,
          content,
          context_notes: contextNotes,
          priority,
        },
        requiredOutput: [
          "decision",
          "confidence",
          "top_risks",
          "recommended_next_step",
          "escalation_suggested",
          "routing_metadata"
        ],
        reason: "plugin_action_invoke_external_review"
      });
    });
  },
});

export default plugin;
runWorker(plugin, import.meta.url);
