import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

const REVIEW_HISTORY_KEY = "external-review-history-v1";
const COMPANY_HISTORY_KEY = "external-review-history-company-v1";
const REVIEW_AUDIT_KEY = "external-review-audit-v1";
const REVIEW_ENTITY_TYPE = "external-review-record";
const REVIEW_HISTORY_LIMIT = 20;
const REVIEW_AUDIT_LIMIT = 100;

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
    owner: firstNonEmpty(input.owner),
    content: typeof input.content === "string" ? input.content : "",
    contextNotes: typeof input.contextNotes === "string" ? input.contextNotes : "",
    decision: firstNonEmpty(input.decision),
    recommendedNextStep: firstNonEmpty(input.recommendedNextStep),
    lane: firstNonEmpty(input.lane),
    model: firstNonEmpty(input.model),
    outcome: firstNonEmpty(input.outcome),
    pinned: Boolean(input.pinned),
    scopeId: firstNonEmpty(input.scopeId),
    exportedEntityId: firstNonEmpty(input.exportedEntityId),
    exportedAt: firstNonEmpty(input.exportedAt),
    lastReassignedAt: firstNonEmpty(input.lastReassignedAt),
    lastReassignedBy: firstNonEmpty(input.lastReassignedBy),
    previousOwner: firstNonEmpty(input.previousOwner),
    auditEvents: Array.isArray(input.auditEvents) ? input.auditEvents : [],
  };
}

function normalizeAuditEvent(input = {}) {
  return {
    id: firstNonEmpty(input.id, `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`),
    eventType: firstNonEmpty(input.eventType, "review.updated"),
    entryId: firstNonEmpty(input.entryId),
    actor: firstNonEmpty(input.actor, "unknown"),
    at: firstNonEmpty(input.at, new Date().toISOString()),
    from: firstNonEmpty(input.from),
    to: firstNonEmpty(input.to),
    reason: firstNonEmpty(input.reason),
    sourceSurface: firstNonEmpty(input.sourceSurface, "external_review_ui"),
    correlationId: firstNonEmpty(input.correlationId),
  };
}

function buildExportTitle(entry) {
  const summary = firstNonEmpty(entry.taskSummary, "External review");
  const decision = firstNonEmpty(entry.decision);
  return decision ? `${summary} · ${decision}` : summary;
}

function buildExportPayload(entry, companyId, scopeId) {
  const normalized = normalizeHistoryEntry({ ...entry, scopeId: firstNonEmpty(entry.scopeId, scopeId) });
  return {
    companyId,
    scopeId: firstNonEmpty(normalized.scopeId),
    taskSummary: normalized.taskSummary,
    reviewType: normalized.reviewType,
    priority: normalized.priority,
    owner: normalized.owner,
    decision: normalized.decision,
    recommendedNextStep: normalized.recommendedNextStep,
    lane: normalized.lane,
    model: normalized.model,
    outcome: normalized.outcome,
    pinned: normalized.pinned,
    content: normalized.content,
    contextNotes: normalized.contextNotes,
    createdAtLabel: normalized.createdAtLabel,
    createdAtMs: normalized.createdAtMs,
    exportedAt: new Date().toISOString(),
    archived: Boolean(normalized.archived),
    lastReassignedAt: normalized.lastReassignedAt,
    lastReassignedBy: normalized.lastReassignedBy,
    previousOwner: normalized.previousOwner,
    auditEvents: normalized.auditEvents,
  };
}

async function updateHistoryEntry(ctx, companyId, scopeId, entryId, updater) {
  const scopedHistory = await readHistory(ctx, companyId, scopeId);
  const nextScoped = scopedHistory.map((item) => item.id === entryId ? normalizeHistoryEntry(updater(item)) : item);
  await writeHistory(ctx, companyId, scopeId, nextScoped);

  const companyHistory = await readCompanyHistory(ctx, companyId);
  const nextCompany = companyHistory.map((item) => item.id === entryId ? normalizeHistoryEntry(updater(item)) : item);
  await writeCompanyHistory(ctx, companyId, nextCompany);

  return { scoped: nextScoped, company: nextCompany };
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

async function readAuditTrail(ctx, companyId) {
  const stored = await ctx.state.get({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: REVIEW_AUDIT_KEY,
  });
  return Array.isArray(stored) ? stored.map((item) => normalizeAuditEvent(item)) : [];
}

async function writeAuditTrail(ctx, companyId, events) {
  await ctx.state.set({
    scopeKind: "company",
    scopeId: companyId,
    namespace: "external-review-ui",
    stateKey: REVIEW_AUDIT_KEY,
  }, events.slice(0, REVIEW_AUDIT_LIMIT));
}

async function appendAuditEvent(ctx, companyId, event) {
  const normalized = normalizeAuditEvent(event);
  const current = await readAuditTrail(ctx, companyId);
  const next = [normalized, ...current].slice(0, REVIEW_AUDIT_LIMIT);
  await writeAuditTrail(ctx, companyId, next);
  return normalized;
}

function auditActorFromParams(params) {
  return firstNonEmpty(params?.actor, params?.context?.userName, params?.context?.userDisplayName, params?.context?.userLabel, "unknown");
}

function auditSurfaceFromParams(params) {
  return firstNonEmpty(params?.sourceSurface, "external_review_ui");
}

function auditCorrelationFromParams(params, fallback = "") {
  return firstNonEmpty(params?.correlationId, fallback);
}

function attachAuditEvent(entry, event) {
  const normalizedEvent = normalizeAuditEvent(event);
  const nextEvents = [normalizedEvent, ...(Array.isArray(entry?.auditEvents) ? entry.auditEvents : [])].slice(0, 20);
  return normalizeHistoryEntry({
    ...entry,
    auditEvents: nextEvents,
    lastReassignedAt: normalizedEvent.eventType === "review.reassigned" || normalizedEvent.eventType === "review.reassignment_undone" ? normalizedEvent.at : entry?.lastReassignedAt,
    lastReassignedBy: normalizedEvent.eventType === "review.reassigned" || normalizedEvent.eventType === "review.reassignment_undone" ? normalizedEvent.actor : entry?.lastReassignedBy,
    previousOwner: normalizedEvent.eventType === "review.reassigned" ? normalizedEvent.from : entry?.previousOwner,
  });
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

async function syncExportedEntityWrite(ctx, companyId, scopeId, entryId, exportedEntityId, exportedAt) {
  const scopedHistory = await readHistory(ctx, companyId, scopeId);
  const nextScoped = scopedHistory.map((item) => item.id === entryId ? { ...item, exportedEntityId, exportedAt } : item);
  await writeHistory(ctx, companyId, scopeId, nextScoped);

  const companyHistory = await readCompanyHistory(ctx, companyId);
  const nextCompany = companyHistory.map((item) => item.id === entryId ? { ...item, exportedEntityId, exportedAt } : item);
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
      const scopedHistory = await readHistory(ctx, companyId, scopeId);
      const companyHistory = await readCompanyHistory(ctx, companyId);
      const current = scopedHistory.find((item) => item.id === entryId) || companyHistory.find((item) => item.id === entryId);
      const auditEvent = await appendAuditEvent(ctx, companyId, {
        eventType: "review.outcome_updated",
        entryId,
        actor: auditActorFromParams(params),
        from: firstNonEmpty(current?.outcome),
        to: outcome,
        reason: firstNonEmpty(params?.reason, "outcome_update"),
        sourceSurface: auditSurfaceFromParams(params),
        correlationId: auditCorrelationFromParams(params, `${entryId}-outcome-${Date.now()}`),
      });
      const nextScoped = scopedHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, outcome }, auditEvent) : item);
      await writeHistory(ctx, companyId, scopeId, nextScoped);
      const nextCompany = companyHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, outcome }, auditEvent) : item);
      await writeCompanyHistory(ctx, companyId, nextCompany);
      return { scoped: nextScoped, company: nextCompany, auditEvent };
    });

    ctx.actions.register("set_review_pinned", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      const entryId = firstNonEmpty(params?.entryId);
      const pinned = Boolean(params?.pinned);
      if (!companyId || !entryId) {
        throw new Error("companyId and entryId are required to update review pin state");
      }

      const scopedHistory = await readHistory(ctx, companyId, scopeId);
      const companyHistory = await readCompanyHistory(ctx, companyId);
      const current = scopedHistory.find((item) => item.id === entryId) || companyHistory.find((item) => item.id === entryId);
      const auditEvent = await appendAuditEvent(ctx, companyId, {
        eventType: pinned ? "review.pinned" : "review.unpinned",
        entryId,
        actor: auditActorFromParams(params),
        from: String(Boolean(current?.pinned)),
        to: String(pinned),
        reason: firstNonEmpty(params?.reason, pinned ? "pin_review" : "unpin_review"),
        sourceSurface: auditSurfaceFromParams(params),
        correlationId: auditCorrelationFromParams(params, `${entryId}-pin-${Date.now()}`),
      });

      const nextScoped = scopedHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, pinned }, auditEvent) : item);
      await writeHistory(ctx, companyId, scopeId, nextScoped);

      const nextCompany = companyHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, pinned }, auditEvent) : item);
      await writeCompanyHistory(ctx, companyId, nextCompany);

      return { scoped: nextScoped, company: nextCompany, auditEvent };
    });

    ctx.actions.register("set_review_owner", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      const entryId = firstNonEmpty(params?.entryId);
      const owner = firstNonEmpty(params?.owner, "unassigned");
      const actor = firstNonEmpty(params?.actor, params?.context?.userName, params?.context?.userDisplayName, params?.context?.userLabel, "unknown");
      const reason = firstNonEmpty(params?.reason, "owner_update");
      const previousOwner = firstNonEmpty(params?.previousOwner);
      const correlationId = firstNonEmpty(params?.correlationId);
      if (!companyId || !entryId) {
        throw new Error("companyId and entryId are required to update review owner");
      }

      const scopedHistory = await readHistory(ctx, companyId, scopeId);
      const companyHistory = await readCompanyHistory(ctx, companyId);
      const current = scopedHistory.find((item) => item.id === entryId) || companyHistory.find((item) => item.id === entryId);
      const fromOwner = firstNonEmpty(previousOwner, current?.owner, "unassigned");
      const eventType = reason === "undo_reassignment" ? "review.reassignment_undone" : "review.reassigned";
      const auditEvent = await appendAuditEvent(ctx, companyId, {
        eventType,
        entryId,
        actor,
        from: fromOwner,
        to: owner,
        reason,
        sourceSurface: firstNonEmpty(params?.sourceSurface, "external_review_ui"),
        correlationId,
      });

      const nextScoped = scopedHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, owner }, auditEvent) : item);
      await writeHistory(ctx, companyId, scopeId, nextScoped);

      const nextCompany = companyHistory.map((item) => item.id === entryId ? attachAuditEvent({ ...item, owner }, auditEvent) : item);
      await writeCompanyHistory(ctx, companyId, nextCompany);

      return { scoped: nextScoped, company: nextCompany, auditEvent };
    });

    ctx.actions.register("export_review_record", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      if (!companyId) {
        throw new Error("companyId is required to export a review record");
      }
      const entry = normalizeHistoryEntry(params?.entry || {});
      const exported = await ctx.entities.upsert({
        entityType: REVIEW_ENTITY_TYPE,
        scopeKind: "company",
        scopeId: companyId,
        externalId: entry.id,
        title: buildExportTitle(entry),
        status: firstNonEmpty(entry.outcome, entry.decision, "recorded"),
        data: buildExportPayload(entry, companyId, scopeId),
      });
      const auditEvent = await appendAuditEvent(ctx, companyId, {
        eventType: "review.exported",
        entryId: entry.id,
        actor: auditActorFromParams(params),
        to: exported.id,
        reason: firstNonEmpty(params?.reason, "export_review_record"),
        sourceSurface: auditSurfaceFromParams(params),
        correlationId: auditCorrelationFromParams(params, `${entry.id}-export-${Date.now()}`),
      });
      const next = await syncExportedEntityWrite(ctx, companyId, scopeId, entry.id, exported.id, new Date().toISOString());
      const scoped = Array.isArray(next?.scoped) ? next.scoped.map((item) => item.id === entry.id ? attachAuditEvent(item, auditEvent) : item) : [];
      const company = Array.isArray(next?.company) ? next.company.map((item) => item.id === entry.id ? attachAuditEvent(item, auditEvent) : item) : [];
      await writeHistory(ctx, companyId, scopeId, scoped);
      await writeCompanyHistory(ctx, companyId, company);
      return { entity: exported, history: { scoped, company }, auditEvent };
    });

    ctx.data.register("exported_review_records", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      if (!companyId) {
        throw new Error("companyId is required to load exported review records");
      }
      const archivedFilter = firstNonEmpty(params?.archivedFilter, "active");
      const records = await ctx.entities.list({
        entityType: REVIEW_ENTITY_TYPE,
        scopeKind: "company",
        scopeId: companyId,
        limit: 50,
        offset: 0,
      });
      if (archivedFilter === "all") return records;
      return records.filter((record) => archivedFilter === "archived" ? Boolean(record?.data?.archived) : !record?.data?.archived);
    });

    ctx.data.register("review_audit_events", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      if (!companyId) {
        throw new Error("companyId is required to load review audit events");
      }
      const entryId = firstNonEmpty(params?.entryId);
      const events = await readAuditTrail(ctx, companyId);
      return entryId ? events.filter((event) => event.entryId === entryId) : events;
    });

    ctx.actions.register("set_exported_review_archived", async (params) => {
      const companyId = firstNonEmpty(params?.companyId, params?.context?.companyId);
      const scopeId = firstNonEmpty(params?.entityId, params?.context?.entityId);
      const recordId = firstNonEmpty(params?.recordId);
      const entryId = firstNonEmpty(params?.entryId, params?.externalId);
      const archived = Boolean(params?.archived);
      if (!companyId || !recordId || !entryId) {
        throw new Error("companyId, recordId, and entryId are required to update exported review archive state");
      }
      const records = await ctx.entities.list({
        entityType: REVIEW_ENTITY_TYPE,
        scopeKind: "company",
        scopeId: companyId,
        limit: 100,
        offset: 0,
      });
      const existing = records.find((record) => record.id === recordId);
      if (!existing) {
        throw new Error("Exported review record not found");
      }
      const nextRecord = await ctx.entities.upsert({
        entityType: REVIEW_ENTITY_TYPE,
        scopeKind: "company",
        scopeId: companyId,
        externalId: existing.externalId || entryId,
        title: existing.title || buildExportTitle(existing.data || {}),
        status: archived ? "archived" : firstNonEmpty(existing.status, "recorded"),
        data: {
          ...(existing.data || {}),
          archived,
          archivedAt: archived ? new Date().toISOString() : null,
        },
      });
      const auditEvent = await appendAuditEvent(ctx, companyId, {
        eventType: archived ? "review.export_archived" : "review.export_restored",
        entryId,
        actor: auditActorFromParams(params),
        from: existing?.data?.archived ? "archived" : "active",
        to: archived ? "archived" : "active",
        reason: firstNonEmpty(params?.reason, archived ? "archive_exported_review" : "restore_exported_review"),
        sourceSurface: auditSurfaceFromParams(params),
        correlationId: auditCorrelationFromParams(params, `${entryId}-archive-${Date.now()}`),
      });
      const history = await updateHistoryEntry(ctx, companyId, scopeId, entryId, (item) => attachAuditEvent({
        ...item,
        exportedEntityId: nextRecord.id,
        archived,
      }, auditEvent));
      return { entity: nextRecord, history, auditEvent };
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

      const promptPayload = {
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
      };

      return await ctx.agents.invoke(agentId, companyId, {
        prompt: JSON.stringify(promptPayload),
        reason: "plugin_action_invoke_external_review"
      });
    });
  },
});

export default plugin;
runWorker(plugin, import.meta.url);
