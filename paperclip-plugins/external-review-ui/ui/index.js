import React, { useEffect, useMemo, useState } from "react";
import { useHostContext, usePluginAction, usePluginData, usePluginToast } from "@paperclipai/plugin-sdk/ui";

const REVIEW_TYPES = [
  { value: "architecture_review", label: "Architecture review" },
  { value: "security_review", label: "Security review" },
  { value: "product_review", label: "Product review" },
  { value: "operational_review", label: "Operational review" }
];

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" }
];

const HISTORY_STORAGE_KEY = "paperclip.externalReview.history.v1";
const HISTORY_LIMIT = 8;

const OUTCOME_OPTIONS = [
  { value: "needs_human", label: "Needs human" },
  { value: "approved", label: "Approved" },
  { value: "blocked", label: "Blocked" },
  { value: "escalated", label: "Escalated" },
];

const OWNER_OPTIONS = [
  { value: "unassigned", label: "Unassigned" },
  { value: "Andrew", label: "Andrew" },
  { value: "Ja'various", label: "Ja'various" },
  { value: "Codex", label: "Codex" },
  { value: "Claude Code", label: "Claude Code" },
  { value: "Cursor", label: "Cursor" },
];

function cardStyle() {
  return {
    display: "grid",
    gap: 14,
    padding: 16,
    color: "#e5e7eb",
    background: "#0f172a",
    border: "1px solid rgba(148,163,184,0.25)",
    borderRadius: 14,
    boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
    minWidth: 360,
    maxWidth: 720,
  };
}

function labelStyle() {
  return {
    display: "grid",
    gap: 6,
    fontSize: 13,
    color: "#cbd5e1",
  };
}

function inputStyle(multiline = false) {
  return {
    width: "100%",
    boxSizing: "border-box",
    borderRadius: 10,
    border: "1px solid rgba(148,163,184,0.25)",
    background: "#111827",
    color: "#f8fafc",
    padding: multiline ? "12px 14px" : "10px 12px",
    outline: "none",
    minHeight: multiline ? 140 : undefined,
    resize: multiline ? "vertical" : undefined,
    font: "inherit",
  };
}

function buttonStyle(kind = "secondary") {
  const primary = kind === "primary";
  return {
    borderRadius: 10,
    border: primary ? "1px solid #2563eb" : "1px solid rgba(148,163,184,0.25)",
    background: primary ? "#2563eb" : "#111827",
    color: "#f8fafc",
    padding: "10px 14px",
    cursor: "pointer",
    fontWeight: 600,
  };
}

function sectionCardStyle() {
  return {
    display: "grid",
    gap: 10,
    padding: 12,
    borderRadius: 12,
    background: "rgba(2,6,23,0.8)",
    border: "1px solid rgba(59,130,246,0.18)",
  };
}

function badgeStyle(tone = "neutral") {
  const tones = {
    success: { background: "rgba(34,197,94,0.18)", color: "#86efac", border: "1px solid rgba(34,197,94,0.28)" },
    warn: { background: "rgba(245,158,11,0.18)", color: "#fcd34d", border: "1px solid rgba(245,158,11,0.28)" },
    danger: { background: "rgba(239,68,68,0.18)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.28)" },
    info: { background: "rgba(59,130,246,0.18)", color: "#93c5fd", border: "1px solid rgba(59,130,246,0.28)" },
    neutral: { background: "rgba(148,163,184,0.16)", color: "#cbd5e1", border: "1px solid rgba(148,163,184,0.24)" },
  };
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    padding: "4px 10px",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.02em",
    ...tones[tone],
  };
}

function mutedHeadingStyle() {
  return {
    fontSize: 12,
    fontWeight: 700,
    color: "#cbd5e1",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  };
}

function summaryFromContext(host) {
  if (host?.entityType === "agent" && host?.entityId) {
    return `External review for agent ${host.entityId}`;
  }
  if (host?.entityType && host?.entityId) {
    return `External review for ${host.entityType} ${host.entityId}`;
  }
  return "External review request";
}

function buildContextNotes(host) {
  const lines = [
    host?.companyId ? `companyId: ${host.companyId}` : null,
    host?.entityType ? `entityType: ${host.entityType}` : null,
    host?.entityId ? `entityId: ${host.entityId}` : null,
    host?.projectId ? `projectId: ${host.projectId}` : null,
    host?.parentEntityId ? `parentEntityId: ${host.parentEntityId}` : null,
    host?.userId ? `userId: ${host.userId}` : null,
  ].filter(Boolean);
  return lines.join("\n");
}

function hasValidAgentContext(host) {
  return Boolean(host?.companyId && host?.entityType === "agent" && host?.entityId);
}

function formatDecision(decision) {
  if (!decision) return "No decision";
  return String(decision)
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function decisionTone(decision) {
  const normalized = String(decision || "").toUpperCase();
  if (normalized.includes("APPROVE") && normalized.includes("CONDITION")) return "warn";
  if (normalized.includes("APPROVE")) return "success";
  if (normalized.includes("REJECT") || normalized.includes("BLOCK")) return "danger";
  return "info";
}

function outcomeTone(outcome) {
  switch (String(outcome || "")) {
    case "approved": return "success";
    case "blocked": return "danger";
    case "escalated": return "warn";
    case "needs_human": return "info";
    default: return "neutral";
  }
}

function formatOutcome(outcome) {
  if (!outcome) return "Unlabeled";
  return String(outcome).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function percent(confidence) {
  if (typeof confidence !== "number" || Number.isNaN(confidence)) return "N/A";
  return `${Math.round(confidence * 100)}%`;
}

function normalizeResultEnvelope(response) {
  const payload = response?.data ?? response ?? {};
  const result = payload?.result ?? {};
  const routing = payload?.routing ?? {};
  const routingMeta = result?.routing_metadata ?? {};
  const usage = payload?.usage ?? {};
  const runId = payload?.runId ?? payload?.run_id ?? null;
  const queued = Boolean(runId) && !result?.decision;
  return {
    decision: result?.decision ?? null,
    confidence: result?.confidence,
    topRisks: Array.isArray(result?.top_risks) ? result.top_risks : [],
    recommendedNextStep: result?.recommended_next_step ?? null,
    escalationSuggested: Boolean(result?.escalation_suggested),
    lane: payload?.lane ?? routing?.selected_lane ?? routingMeta?.selected_lane ?? null,
    model: payload?.model ?? routingMeta?.selected_model ?? null,
    provider: payload?.provider ?? routingMeta?.provider ?? null,
    summary: payload?.summary ?? null,
    repaired: payload?.repaired ?? routingMeta?.repaired ?? null,
    correlationId: routing?.correlation_id ?? routingMeta?.correlation_id ?? runId ?? null,
    reviewType: routingMeta?.review_type ?? null,
    sourceContext: routingMeta?.source_context ?? null,
    subject: routingMeta?.subject ?? null,
    priority: routingMeta?.priority ?? null,
    promptTokens: usage?.prompt_tokens ?? null,
    completionTokens: usage?.completion_tokens ?? null,
    totalTokens: usage?.total_tokens ?? null,
    cost: usage?.cost ?? null,
    runId,
    queued,
    raw: response,
  };
}

function ResultMetric({ label, value }) {
  return React.createElement("div", { style: { display: "grid", gap: 4 } },
    React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, label),
    React.createElement("div", { style: { fontSize: 14, fontWeight: 600, color: "#f8fafc" } }, value || "N/A")
  );
}

async function fetchCompanyAgents(companyId) {
  if (!companyId) return [];
  const response = await fetch(`/api/companies/${encodeURIComponent(companyId)}/agents`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load agents (${response.status})`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

function buildSummaryText(normalized) {
  const parts = [
    `Decision: ${formatDecision(normalized.decision)}`,
    `Confidence: ${percent(normalized.confidence)}`,
    normalized.recommendedNextStep ? `Recommended next step: ${normalized.recommendedNextStep}` : null,
    normalized.topRisks.length ? `Top risks: ${normalized.topRisks.join('; ')}` : null,
    normalized.lane ? `Lane: ${normalized.lane}` : null,
    normalized.model ? `Model: ${normalized.model}` : null,
  ].filter(Boolean);
  return parts.join("\n");
}

function loadStoredHistory() {
  if (typeof window === "undefined" || !window?.localStorage) return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistHistory(entries) {
  if (typeof window === "undefined" || !window?.localStorage) return;
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries.slice(0, HISTORY_LIMIT)));
  } catch {
    // best-effort only
  }
}

async function copyToClipboard(text) {
  if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  return false;
}

function rerunPresetButton(label, onClick) {
  return React.createElement("button", { type: "button", onClick, style: buttonStyle("secondary") }, label);
}

function WhatsNewPanel() {
  const items = [
    'Structured review results with decision, confidence, risks, and next step',
    'Current-context and company-wide review history',
    'Priority queue with aging signals, team load, and rebalance guidance',
    'Owner tagging, guided reassignment, and undo window',
    'Exported Paperclip review records with archive and restore flow',
    'Worker-backed audit timeline with clickable audit chips and scoped filters',
  ];
  return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, border: "1px solid rgba(96,165,250,0.32)", background: "rgba(30,64,175,0.16)" } },
    React.createElement("div", { style: { display: "grid", gap: 4 } },
      React.createElement("div", { style: { ...mutedHeadingStyle(), color: "#bfdbfe" } }, "What's new in this drawer"),
      React.createElement("div", { style: { fontSize: 13, color: "#dbeafe", lineHeight: 1.5 } }, "This is now a full operator console, not just a one-shot review form.")
    ),
    React.createElement("div", { style: { display: "grid", gap: 6 } },
      ...items.map((item) => React.createElement("div", { key: item, style: { fontSize: 13, color: "#e2e8f0", lineHeight: 1.45 } }, `• ${item}`))
    )
  );
}

function ResultPanel({ result, currentOutcome, onSetOutcome, onReuseAsFollowUp, onEscalate, onApplyPreset, toast }) {
  const normalized = normalizeResultEnvelope(result);
  if (normalized.queued) {
    return React.createElement("div", { style: sectionCardStyle() },
      React.createElement("div", { style: { display: "grid", gap: 6 } },
        React.createElement("div", { style: mutedHeadingStyle() }, "Latest result"),
        React.createElement("div", { style: { fontSize: 18, fontWeight: 700, color: "#f8fafc" } }, "Review queued"),
        React.createElement("div", { style: { fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 } }, "Paperclip accepted the request and started an agent run, but this runtime only returned a run ID, not the finished review payload yet."),
        React.createElement("div", { style: { fontSize: 12, color: "#93c5fd" } }, `Run ID: ${normalized.runId || 'unknown'}`)
      )
    );
  }
  const summaryText = buildSummaryText(normalized);
  async function handleCopySummary() {
    try {
      const ok = await copyToClipboard(summaryText);
      if (ok) {
        toast({ tone: "success", title: "Review summary copied", body: "Structured result copied to clipboard." });
      } else {
        toast({ tone: "info", title: "Clipboard unavailable", body: "Copy is not available in this host environment." });
      }
    } catch (err) {
      toast({ tone: "error", title: "Copy failed", body: err?.message || "Could not copy review summary." });
    }
  }
  return React.createElement("div", { style: sectionCardStyle() },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" } },
      React.createElement("div", { style: { display: "grid", gap: 6 } },
        React.createElement("div", { style: mutedHeadingStyle() }, "Latest result"),
        React.createElement("div", { style: { fontSize: 18, fontWeight: 700, color: "#f8fafc" } }, formatDecision(normalized.decision))
      ),
      React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
        React.createElement("span", { style: badgeStyle(decisionTone(normalized.decision)) }, formatDecision(normalized.decision)),
        normalized.escalationSuggested ? React.createElement("span", { style: badgeStyle("warn") }, "Escalation suggested") : null,
        normalized.repaired === true ? React.createElement("span", { style: badgeStyle("info") }, "JSON repaired") : null
      )
    ),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 } },
      React.createElement(ResultMetric, { label: "Confidence", value: percent(normalized.confidence) }),
      React.createElement(ResultMetric, { label: "Lane", value: normalized.lane }),
      React.createElement(ResultMetric, { label: "Model", value: normalized.model })
    ),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 } },
      React.createElement(ResultMetric, { label: "Provider", value: normalized.provider }),
      React.createElement(ResultMetric, { label: "Priority", value: normalized.priority }),
      React.createElement(ResultMetric, { label: "Review type", value: normalized.reviewType })
    ),
    normalized.recommendedNextStep ? React.createElement("div", { style: { display: "grid", gap: 6 } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Recommended next step"),
      React.createElement("div", { style: { fontSize: 14, lineHeight: 1.5, color: "#e2e8f0" } }, normalized.recommendedNextStep)
    ) : null,
    normalized.topRisks.length > 0 ? React.createElement("div", { style: { display: "grid", gap: 8 } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Top risks"),
      React.createElement("ul", { style: { margin: 0, paddingLeft: 18, display: "grid", gap: 6, color: "#cbd5e1" } },
        ...normalized.topRisks.map((risk, index) => React.createElement("li", { key: `${index}-${risk}` }, risk))
      )
    ) : null,
    React.createElement("div", { style: { display: "grid", gap: 8 } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Operator outcome"),
      React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } },
        ...OUTCOME_OPTIONS.map((option) => React.createElement("button", {
          key: option.value,
          type: "button",
          onClick: () => onSetOutcome(option.value, normalized),
          style: {
            ...buttonStyle(currentOutcome === option.value ? "primary" : "secondary"),
            border: currentOutcome === option.value ? "1px solid #2563eb" : buttonStyle("secondary").border,
          }
        }, option.label)),
        currentOutcome ? React.createElement("span", { style: badgeStyle(outcomeTone(currentOutcome)) }, formatOutcome(currentOutcome)) : null
      )
    ),
    React.createElement("div", { style: { display: "flex", gap: 10, flexWrap: "wrap" } },
      React.createElement("button", { type: "button", onClick: handleCopySummary, style: buttonStyle("secondary") }, "Copy review summary"),
      React.createElement("button", { type: "button", onClick: () => onReuseAsFollowUp(normalized), style: buttonStyle("secondary") }, "Use as follow-up draft"),
      React.createElement("button", { type: "button", onClick: () => onEscalate(normalized), style: buttonStyle("primary") }, "Escalate")
    ),
    React.createElement("div", { style: { display: "grid", gap: 8 } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Quick rerun presets"),
      React.createElement("div", { style: { display: "flex", gap: 10, flexWrap: "wrap" } },
        rerunPresetButton("Security pass", () => onApplyPreset({ reviewType: "security_review", priority: "high", taskSummaryPrefix: "Security pass" }, normalized)),
        rerunPresetButton("Operational pass", () => onApplyPreset({ reviewType: "operational_review", priority: "high", taskSummaryPrefix: "Operational pass" }, normalized)),
        rerunPresetButton("Product pass", () => onApplyPreset({ reviewType: "product_review", priority: "normal", taskSummaryPrefix: "Product pass" }, normalized)),
        rerunPresetButton("Urgent architecture", () => onApplyPreset({ reviewType: "architecture_review", priority: "urgent", taskSummaryPrefix: "Urgent architecture follow-up" }, normalized))
      )
    ),
    React.createElement("details", { style: { display: "grid", gap: 8 } },
      React.createElement("summary", { style: { cursor: "pointer", color: "#93c5fd", fontWeight: 600 } }, "Show routing and raw details"),
      React.createElement("div", { style: { display: "grid", gap: 10 } },
        React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 } },
          React.createElement(ResultMetric, { label: "Correlation ID", value: normalized.correlationId }),
          React.createElement(ResultMetric, { label: "Subject", value: normalized.subject })
        ),
        React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 } },
          React.createElement(ResultMetric, { label: "Prompt tokens", value: normalized.promptTokens != null ? String(normalized.promptTokens) : "N/A" }),
          React.createElement(ResultMetric, { label: "Completion tokens", value: normalized.completionTokens != null ? String(normalized.completionTokens) : "N/A" }),
          React.createElement(ResultMetric, { label: "Total tokens", value: normalized.totalTokens != null ? String(normalized.totalTokens) : "N/A" }),
          React.createElement(ResultMetric, { label: "Cost", value: normalized.cost != null ? `$${Number(normalized.cost).toFixed(6)}` : "N/A" })
        ),
        React.createElement("pre", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#bfdbfe" } }, JSON.stringify(normalized.raw, null, 2))
      )
    )
  );
}

function filterHistoryEntries(entries, searchText, outcomeFilter, pinFilter, sortMode, ownerFilter = "all") {
  const query = String(searchText || "").trim().toLowerCase();
  const filtered = entries.filter((entry) => {
    const matchesOutcome = outcomeFilter === "all" ? true : String(entry.outcome || "") === outcomeFilter;
    const matchesPin = pinFilter === "all" ? true : pinFilter === "pinned" ? Boolean(entry.pinned) : !entry.pinned;
    const normalizedOwner = String(entry.owner || "unassigned");
    const matchesOwner = ownerFilter === "all" ? true : ownerFilter === "assigned" ? normalizedOwner !== "unassigned" : normalizedOwner === ownerFilter;
    if (!matchesOutcome || !matchesPin || !matchesOwner) return false;
    if (!query) return true;
    const haystack = [
      entry.taskSummary,
      entry.reviewType,
      entry.priority,
      entry.decision,
      entry.outcome,
      entry.owner,
      entry.recommendedNextStep,
      entry.scopeId,
      entry.model,
      entry.lane,
    ].filter(Boolean).join(" \n ").toLowerCase();
    return haystack.includes(query);
  });

  return [...filtered].sort((a, b) => {
    const aPinned = a.pinned ? 1 : 0;
    const bPinned = b.pinned ? 1 : 0;
    if (aPinned !== bPinned) return bPinned - aPinned;
    const aMs = Number(a.createdAtMs || 0);
    const bMs = Number(b.createdAtMs || 0);
    if (sortMode === "oldest") return aMs - bMs;
    return bMs - aMs;
  });
}

function formatAuditCopy(entry) {
  if (!entry?.lastAuditEventAt && !entry?.lastAuditEventActor && !entry?.lastReassignedAt && !entry?.lastReassignedBy) return null;
  const parts = [];
  if (entry?.lastAuditEventType) parts.push(entry.lastAuditEventType.replace(/^review\./, '').replaceAll('_', ' '));
  else if (entry?.lastReassignedBy) parts.push('reassigned');
  if (entry?.lastAuditEventActor) parts.push(`by ${entry.lastAuditEventActor}`);
  else if (entry?.lastReassignedBy) parts.push(`by ${entry.lastReassignedBy}`);
  if (entry?.lastAuditEventAt) parts.push(entry.lastAuditEventAt);
  else if (entry?.lastReassignedAt) parts.push(entry.lastReassignedAt);
  return parts.length ? parts.join(' • ') : null;
}

function AuditScopeChips({ entry, onFocusAudit }) {
  if (!entry || !onFocusAudit || (!entry.lastAuditEventType && !entry.lastAuditEventActor)) return null;
  return React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
    entry.lastAuditEventType ? React.createElement("button", {
      type: "button",
      onClick: () => onFocusAudit(entry, { eventType: entry.lastAuditEventType }),
      style: { ...badgeStyle("info"), cursor: "pointer" },
    }, entry.lastAuditEventType.replace(/^review\./, '').replaceAll('_', ' ')) : null,
    entry.lastAuditEventActor ? React.createElement("button", {
      type: "button",
      onClick: () => onFocusAudit(entry, { actor: entry.lastAuditEventActor }),
      style: { ...badgeStyle("neutral"), cursor: "pointer" },
    }, entry.lastAuditEventActor) : null
  );
}

function HistoryList({ title, subtitle, entries, onRestore, onSetOutcome, onSetPinned, onSetOwner, onExport, onFocusAudit, emptyText }) {
  return React.createElement("div", { style: { display: "grid", gap: 10 } },
    React.createElement("div", { style: { display: "grid", gap: 4 } },
      React.createElement("div", { style: mutedHeadingStyle() }, title),
      subtitle ? React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, subtitle) : null
    ),
    !entries.length
      ? React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, emptyText)
      : entries.map((entry, index) => React.createElement("div", {
          key: entry.id || `${index}-${entry.taskSummary}`,
          style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, background: "rgba(2,6,23,0.75)", border: "1px solid rgba(59,130,246,0.12)" }
        },
          React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" } },
            React.createElement("div", { style: { display: "grid", gap: 4 } },
              React.createElement("div", { style: { fontSize: 14, fontWeight: 700, color: "#f8fafc" } }, entry.taskSummary || "Untitled review"),
              React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, `${entry.reviewType || 'unknown'} • ${entry.priority || 'unknown'} • ${entry.createdAtLabel || 'now'}`),
              entry.scopeId ? React.createElement("div", { style: { fontSize: 11, color: "#64748b" } }, `scope: ${entry.scopeId}`) : null,
              React.createElement("div", { style: { fontSize: 11, color: "#64748b" } }, `owner: ${entry.owner || 'unassigned'}`),
              formatAuditCopy(entry) ? React.createElement("button", { type: "button", onClick: () => onFocusAudit && onFocusAudit(entry), style: { background: "transparent", border: "none", padding: 0, margin: 0, textAlign: "left", cursor: "pointer", fontSize: 11, color: "#64748b" } }, formatAuditCopy(entry)) : null,
              React.createElement(AuditScopeChips, { entry, onFocusAudit })
            ),
            React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } },
              entry.pinned ? React.createElement("span", { style: badgeStyle("warn") }, "Pinned") : null,
              entry.exportedEntityId ? React.createElement("span", { style: badgeStyle("success") }, "Exported") : null,
              entry.decision ? React.createElement("span", { style: badgeStyle(decisionTone(entry.decision)) }, formatDecision(entry.decision)) : null,
              entry.outcome ? React.createElement("span", { style: badgeStyle(outcomeTone(entry.outcome)) }, formatOutcome(entry.outcome)) : null,
              React.createElement("button", { type: "button", onClick: () => onSetPinned(entry.id, !entry.pinned), style: buttonStyle(entry.pinned ? "primary" : "secondary") }, entry.pinned ? "Unpin" : "Pin"),
              React.createElement("select", { value: entry.owner || "unassigned", onChange: (e) => onSetOwner(entry.id, e.target.value), style: { ...inputStyle(false), minWidth: 160, width: 160 } },
                ...OWNER_OPTIONS.map((option) => React.createElement("option", { key: option.value, value: option.value }, option.label))
              ),
              React.createElement("button", { type: "button", onClick: () => onExport(entry), style: buttonStyle(entry.exportedEntityId ? "secondary" : "primary") }, entry.exportedEntityId ? "Update record" : "Export record"),
              React.createElement("button", { type: "button", onClick: () => onRestore(entry), style: buttonStyle("secondary") }, "Restore")
            )
          ),
          React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
            ...OUTCOME_OPTIONS.map((option) => React.createElement("button", {
              key: `${entry.id}-${option.value}`,
              type: "button",
              onClick: () => onSetOutcome(entry.id, option.value),
              style: {
                ...buttonStyle(entry.outcome === option.value ? "primary" : "secondary"),
                padding: "8px 10px",
              }
            }, option.label))
          ),
          entry.recommendedNextStep ? React.createElement("div", { style: { fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 } }, entry.recommendedNextStep) : null,
          entry.exportedAt ? React.createElement("div", { style: { fontSize: 11, color: "#64748b" } }, `record synced ${entry.exportedAt}`) : null
        ))
  );
}

function AuditTimelinePanel({ events, loading, error, entryId, scopedEventType = null, scopedActor = null, onClearScope = null }) {
  const [eventTypeFilter, setEventTypeFilter] = useState('all');
  const [actorFilter, setActorFilter] = useState('all');
  useEffect(() => {
    if (scopedEventType) setEventTypeFilter(scopedEventType);
  }, [scopedEventType]);
  useEffect(() => {
    if (scopedActor) setActorFilter(scopedActor);
  }, [scopedActor]);
  const eventTypes = useMemo(() => Array.from(new Set((events || []).map((event) => event?.eventType).filter(Boolean))).sort(), [events]);
  const actors = useMemo(() => Array.from(new Set((events || []).map((event) => event?.actor).filter(Boolean))).sort(), [events]);
  const filteredEvents = useMemo(() => (events || []).filter((event) => {
    if (eventTypeFilter !== 'all' && event?.eventType !== eventTypeFilter) return false;
    if (actorFilter !== 'all' && event?.actor !== actorFilter) return false;
    return true;
  }), [events, eventTypeFilter, actorFilter]);
  if (loading) {
    return React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "Loading audit timeline...");
  }
  if (error) {
    return React.createElement("div", { style: { fontSize: 13, color: "#fca5a5" } }, `Audit timeline unavailable: ${error.message || error}`);
  }
  if (!events.length) {
    return React.createElement("div", { style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Audit timeline"),
      React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, entryId ? "No audit events for this review yet." : "Select or create a review to see its audit trail.")
    );
  }
  return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" } },
      React.createElement("div", { style: { display: "grid", gap: 4 } },
        React.createElement("div", { style: mutedHeadingStyle() }, "Audit timeline"),
        scopedEventType || scopedActor ? React.createElement("div", { style: { fontSize: 11, color: "#94a3b8" } }, `Scoped${scopedEventType ? ` • ${scopedEventType}` : ''}${scopedActor ? ` • ${scopedActor}` : ''}`) : null
      ),
      React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
        React.createElement("select", { value: eventTypeFilter, onChange: (e) => setEventTypeFilter(e.target.value), style: inputStyle(false) },
          React.createElement("option", { value: "all" }, "All event types"),
          ...eventTypes.map((value) => React.createElement("option", { key: value, value }, value))
        ),
        React.createElement("select", { value: actorFilter, onChange: (e) => setActorFilter(e.target.value), style: inputStyle(false) },
          React.createElement("option", { value: "all" }, "All actors"),
          ...actors.map((value) => React.createElement("option", { key: value, value }, value))
        ),
        scopedEventType || scopedActor ? React.createElement("button", { type: "button", onClick: () => onClearScope && onClearScope(), style: buttonStyle("secondary") }, "Clear scope") : null
      )
    ),
    !filteredEvents.length
      ? React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "No audit events match the current filters.")
      : filteredEvents.map((event) => React.createElement("div", {
          key: event.id,
          style: { display: "grid", gap: 4, padding: 10, borderRadius: 10, background: "rgba(2,6,23,0.75)", border: "1px solid rgba(59,130,246,0.12)" }
        },
          React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" } },
            React.createElement("div", { style: { fontSize: 13, fontWeight: 700, color: "#f8fafc" } }, event.eventType || "review.updated"),
            React.createElement("div", { style: { fontSize: 11, color: "#94a3b8" } }, event.at || "unknown time")
          ),
          React.createElement("div", { style: { fontSize: 12, color: "#cbd5e1" } }, `${event.actor || 'Unknown actor'}${event.to ? ` → ${event.to}` : ''}`),
          event.from || event.reason ? React.createElement("div", { style: { fontSize: 11, color: "#64748b" } }, [event.from ? `from ${event.from}` : null, event.reason ? `reason: ${event.reason}` : null].filter(Boolean).join(' • ')) : null,
          event.correlationId ? React.createElement("div", { style: { fontSize: 11, color: "#475569" } }, `correlation: ${event.correlationId}`) : null
        ))
  );
}

function ExportedRecordsPanel({ records, loading, error, archivedFilter, setArchivedFilter, onToggleArchived, onRestoreRecord, onFocusAudit }) {
  if (loading) {
    return React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "Loading exported records...");
  }
  if (error) {
    return React.createElement("div", { style: { fontSize: 13, color: "#fca5a5" } }, `Exported records unavailable: ${error.message || error}`);
  }
  if (!records.length && archivedFilter !== "all") {
    return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
      React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" } },
        React.createElement("div", { style: mutedHeadingStyle() }, "Exported Paperclip records"),
        React.createElement("select", {
          value: archivedFilter,
          onChange: (e) => setArchivedFilter(e.target.value),
          style: inputStyle(false),
        },
          React.createElement("option", { value: "active" }, "Active records"),
          React.createElement("option", { value: "archived" }, "Archived records"),
          React.createElement("option", { value: "all" }, "All records")
        )
      ),
      React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "No exported records in this view yet.")
    );
  }
  if (!records.length) return null;
  return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Exported Paperclip records"),
      React.createElement("select", {
        value: archivedFilter,
        onChange: (e) => setArchivedFilter(e.target.value),
        style: inputStyle(false),
      },
        React.createElement("option", { value: "active" }, "Active records"),
        React.createElement("option", { value: "archived" }, "Archived records"),
        React.createElement("option", { value: "all" }, "All records")
      )
    ),
    ...records.map((record) => React.createElement("div", {
      key: record.id,
      style: { display: "grid", gap: 6, padding: 12, borderRadius: 10, background: "rgba(2,6,23,0.75)", border: "1px solid rgba(34,197,94,0.18)" }
    },
      React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" } },
        React.createElement("div", { style: { fontSize: 14, fontWeight: 700, color: "#f8fafc" } }, record.title || record.data?.taskSummary || "External review record"),
        React.createElement("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
          record.data?.archived ? React.createElement("span", { style: badgeStyle("neutral") }, "Archived") : null,
          record.status ? React.createElement("span", { style: badgeStyle(record.data?.archived ? "neutral" : "success") }, record.status) : null,
          React.createElement("button", { type: "button", onClick: () => onRestoreRecord(record), style: buttonStyle("secondary") }, "Restore into form"),
          React.createElement("button", { type: "button", onClick: () => onToggleArchived(record, !record.data?.archived), style: buttonStyle(record.data?.archived ? "secondary" : "primary") }, record.data?.archived ? "Restore" : "Archive")
        )
      ),
      React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, `${record.entityType} • ${record.updatedAt || record.createdAt || 'unknown time'}`),
      formatAuditCopy(record.data) ? React.createElement("button", { type: "button", onClick: () => onFocusAudit && onFocusAudit(record.data), style: { background: "transparent", border: "none", padding: 0, margin: 0, textAlign: "left", cursor: "pointer", fontSize: 11, color: "#64748b" } }, formatAuditCopy(record.data)) : null,
      React.createElement(AuditScopeChips, { entry: record.data, onFocusAudit }),
      React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } },
        record.data?.reviewType ? React.createElement("span", { style: badgeStyle("info") }, record.data.reviewType) : null,
        record.data?.priority ? React.createElement("span", { style: badgeStyle("warn") }, record.data.priority) : null,
        record.data?.scopeId ? React.createElement("span", { style: badgeStyle("neutral") }, `scope ${record.data.scopeId}`) : null,
        record.data?.decision ? React.createElement("span", { style: badgeStyle(decisionTone(record.data.decision)) }, formatDecision(record.data.decision)) : null,
        record.data?.outcome ? React.createElement("span", { style: badgeStyle(outcomeTone(record.data.outcome)) }, formatOutcome(record.data.outcome)) : null
      ),
      record.data?.recommendedNextStep ? React.createElement("div", { style: { fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 } }, record.data.recommendedNextStep) : null,
      React.createElement("details", { style: { display: "grid", gap: 8 } },
        React.createElement("summary", { style: { cursor: "pointer", color: "#93c5fd", fontWeight: 600 } }, "Show record details"),
        React.createElement("pre", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#bfdbfe" } }, JSON.stringify(record.data || {}, null, 2))
      )
    ))
  );
}

function SummaryCard({ label, value, tone = "neutral", active = false, onClick }) {
  const toneColors = {
    neutral: { border: "rgba(148,163,184,0.18)", background: "rgba(15,23,42,0.65)", value: "#f8fafc" },
    success: { border: "rgba(34,197,94,0.22)", background: "rgba(21,128,61,0.16)", value: "#bbf7d0" },
    warn: { border: "rgba(251,191,36,0.22)", background: "rgba(161,98,7,0.18)", value: "#fde68a" },
    info: { border: "rgba(59,130,246,0.22)", background: "rgba(30,64,175,0.18)", value: "#bfdbfe" },
    danger: { border: "rgba(239,68,68,0.22)", background: "rgba(127,29,29,0.18)", value: "#fecaca" },
  };
  const palette = toneColors[tone] || toneColors.neutral;
  return React.createElement("button", {
    type: "button",
    onClick,
    style: {
      display: "grid",
      gap: 6,
      padding: 12,
      borderRadius: 10,
      border: `1px solid ${active ? '#f8fafc' : palette.border}`,
      background: active ? 'rgba(248,250,252,0.08)' : palette.background,
      minWidth: 0,
      textAlign: 'left',
      cursor: 'pointer',
    }
  },
    React.createElement("div", { style: { fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "#94a3b8", fontWeight: 700 } }, label),
    React.createElement("div", { style: { fontSize: 24, fontWeight: 800, color: palette.value, lineHeight: 1 } }, String(value))
  );
}

function buildDashboardStats({ scopedEntries, companyEntries, exportedRecords, currentOwnerLabel }) {
  const activeExported = exportedRecords.filter((record) => !record?.data?.archived);
  const archivedExported = exportedRecords.filter((record) => Boolean(record?.data?.archived));
  const pinnedHistory = companyEntries.filter((entry) => entry?.pinned);
  const needsHuman = companyEntries.filter((entry) => entry?.outcome === "needs_human");
  const blocked = companyEntries.filter((entry) => entry?.outcome === "blocked");
  const escalated = companyEntries.filter((entry) => entry?.outcome === "escalated");
  const assigned = companyEntries.filter((entry) => entry?.owner && entry.owner !== "unassigned");
  const assignedToCurrent = currentOwnerLabel ? companyEntries.filter((entry) => entry?.owner === currentOwnerLabel) : [];
  const myQueue = currentOwnerLabel ? companyEntries.filter((entry) => entry?.owner === currentOwnerLabel && ["blocked", "needs_human", "escalated"].includes(entry?.outcome)) : [];
  const myStale = myQueue.filter((entry) => getAgingState(entry).stale);
  return [
    { label: "Current context", value: scopedEntries.length, tone: "info", filterKey: "current" },
    { label: "Company history", value: companyEntries.length, tone: "neutral", filterKey: "company" },
    { label: "Pinned", value: pinnedHistory.length, tone: "warn", filterKey: "pinned" },
    { label: "Assigned", value: assigned.length, tone: assigned.length ? "info" : "neutral", filterKey: "assigned" },
    { label: "My queue", value: myQueue.length, tone: myQueue.length ? "success" : "neutral", filterKey: "my_queue" },
    { label: "My stale", value: myStale.length, tone: myStale.length ? "danger" : "neutral", filterKey: "my_stale" },
    currentOwnerLabel ? { label: currentOwnerLabel, value: assignedToCurrent.length, tone: assignedToCurrent.length ? "success" : "neutral", filterKey: "owner_current" } : null,
    { label: "Needs human", value: needsHuman.length, tone: needsHuman.length ? "warn" : "neutral", filterKey: "needs_human" },
    { label: "Blocked", value: blocked.length, tone: blocked.length ? "danger" : "neutral", filterKey: "blocked" },
    { label: "Escalated", value: escalated.length, tone: escalated.length ? "info" : "neutral", filterKey: "escalated" },
    { label: "Exported", value: activeExported.length, tone: activeExported.length ? "success" : "neutral", filterKey: "exported_active" },
    { label: "Archived records", value: archivedExported.length, tone: "neutral", filterKey: "exported_archived" },
  ].filter(Boolean);
}

function buildOwnerLoad(entries) {
  const owners = new Map();
  for (const entry of entries || []) {
    const owner = entry?.owner && entry.owner !== "unassigned" ? entry.owner : null;
    if (!owner) continue;
    const current = owners.get(owner) || { owner, total: 0, queue: 0, stale: 0, blocked: 0, needsHuman: 0, escalated: 0 };
    current.total += 1;
    if (["blocked", "needs_human", "escalated"].includes(entry?.outcome)) current.queue += 1;
    if (entry?.outcome === "blocked") current.blocked += 1;
    if (entry?.outcome === "needs_human") current.needsHuman += 1;
    if (entry?.outcome === "escalated") current.escalated += 1;
    if (["blocked", "needs_human", "escalated"].includes(entry?.outcome) && getAgingState(entry).stale) current.stale += 1;
    owners.set(owner, current);
  }
  return [...owners.values()].sort((a, b) => {
    if (b.queue !== a.queue) return b.queue - a.queue;
    if (b.stale !== a.stale) return b.stale - a.stale;
    return a.owner.localeCompare(b.owner);
  });
}

function buildRebalanceSuggestions(ownerLoad, currentOwnerLabel) {
  if (!Array.isArray(ownerLoad) || ownerLoad.length < 2) return [];
  const busiest = ownerLoad[0];
  const leastBusy = [...ownerLoad].sort((a, b) => {
    if (a.queue !== b.queue) return a.queue - b.queue;
    if (a.stale !== b.stale) return a.stale - b.stale;
    return a.owner.localeCompare(b.owner);
  })[0];
  const suggestions = [];
  if (busiest && leastBusy && busiest.owner !== leastBusy.owner && (busiest.queue - leastBusy.queue >= 2 || busiest.stale > 0)) {
    suggestions.push({
      title: `Shift one queued review from ${busiest.owner} to ${leastBusy.owner}`,
      detail: `${busiest.owner} has ${busiest.queue} queued with ${busiest.stale} stale, while ${leastBusy.owner} has ${leastBusy.queue} queued.`,
      tone: busiest.stale ? "danger" : "warn",
      filterKey: `owner:${busiest.owner}`,
      fromOwner: busiest.owner,
      toOwner: leastBusy.owner,
    });
  }
  if (currentOwnerLabel) {
    const mine = ownerLoad.find((item) => item.owner === currentOwnerLabel);
    if (mine?.stale) {
      suggestions.push({
        title: `Clear stale items in ${currentOwnerLabel}'s queue`,
        detail: `${currentOwnerLabel} has ${mine.stale} stale queued review${mine.stale === 1 ? "" : "s"} ready for triage.`,
        tone: "danger",
        filterKey: "my_stale",
      });
    } else if (mine?.queue >= 3) {
      suggestions.push({
        title: `Review ${currentOwnerLabel}'s queue depth`,
        detail: `${currentOwnerLabel} currently owns ${mine.queue} queued reviews.`,
        tone: "warn",
        filterKey: "my_queue",
      });
    }
  }
  return suggestions.slice(0, 2);
}

function explainRebalanceCandidate(entry, suggestion) {
  if (!entry) return null;
  const reasons = [];
  if (["blocked", "needs_human", "escalated"].includes(entry?.outcome)) {
    reasons.push(`${outcomeLabel(entry.outcome)} item`);
  }
  const aging = getAgingState(entry);
  if (aging?.label && aging.label !== "Fresh" && aging.label !== "Unknown age") {
    reasons.push(aging.label.toLowerCase());
  }
  if (entry?.pinned) reasons.push("currently pinned");
  if (suggestion?.fromOwner && suggestion?.toOwner) {
    reasons.push(`moves load from ${suggestion.fromOwner} to ${suggestion.toOwner}`);
  }
  if (!reasons.length) reasons.push("highest-priority queued item in the overloaded lane");
  return `Why this item: ${reasons.join(", ")}.`;
}

function TeamLoadPanel({ entries, currentOwnerLabel, onSelectFilter, activeDashboardFilter, onReassignSuggestion }) {
  const ownerLoad = useMemo(() => buildOwnerLoad(entries), [entries]);
  const suggestions = useMemo(() => buildRebalanceSuggestions(ownerLoad, currentOwnerLabel), [ownerLoad, currentOwnerLabel]);
  const rebalanceCandidates = useMemo(() => {
    return suggestions.map((suggestion) => {
      if (!suggestion.fromOwner || !suggestion.toOwner) return null;
      const candidate = (entries || [])
        .filter((entry) => entry?.owner === suggestion.fromOwner)
        .filter((entry) => ["blocked", "needs_human", "escalated"].includes(entry?.outcome))
        .sort((a, b) => {
          const staleDelta = Number(getAgingState(b).stale) - Number(getAgingState(a).stale);
          if (staleDelta !== 0) return staleDelta;
          return (b?.createdAtMs || 0) - (a?.createdAtMs || 0);
        })[0];
      return candidate ? { suggestion, entry: candidate } : null;
    }).filter(Boolean);
  }, [entries, suggestions]);
  if (!ownerLoad.length) return null;
  return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Team load"),
      React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, "Queue pressure by assigned owner")
    ),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 } },
      ...ownerLoad.map((item) => {
        const filterKey = `owner:${item.owner}`;
        const isActive = activeDashboardFilter === filterKey;
        return React.createElement("button", {
          key: item.owner,
          type: "button",
          onClick: () => onSelectFilter(isActive ? null : filterKey),
          style: {
            display: "grid",
            gap: 8,
            textAlign: "left",
            padding: 12,
            borderRadius: 10,
            border: isActive ? "1px solid rgba(96,165,250,0.65)" : "1px solid rgba(148,163,184,0.18)",
            background: isActive ? "rgba(30,41,59,0.95)" : "rgba(2,6,23,0.72)",
            color: "#e2e8f0",
            cursor: "pointer",
          }
        },
          React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" } },
            React.createElement("div", { style: { display: "grid", gap: 2 } },
              React.createElement("div", { style: { fontSize: 14, fontWeight: 700, color: "#f8fafc" } }, item.owner),
              currentOwnerLabel === item.owner ? React.createElement("div", { style: { fontSize: 11, color: "#60a5fa" } }, "You") : null
            ),
            React.createElement("span", { style: badgeStyle(item.stale ? "danger" : item.queue ? "warn" : "neutral") }, `${item.queue} queued`)
          ),
          React.createElement("div", { style: { display: "flex", gap: 6, flexWrap: "wrap" } },
            React.createElement("span", { style: badgeStyle("neutral") }, `${item.total} assigned`),
            item.blocked ? React.createElement("span", { style: badgeStyle("danger") }, `${item.blocked} blocked`) : null,
            item.needsHuman ? React.createElement("span", { style: badgeStyle("warn") }, `${item.needsHuman} needs human`) : null,
            item.escalated ? React.createElement("span", { style: badgeStyle("info") }, `${item.escalated} escalated`) : null,
            item.stale ? React.createElement("span", { style: badgeStyle("danger") }, `${item.stale} stale`) : null
          )
        );
      })
    ),
    suggestions.length ? React.createElement("div", { style: { display: "grid", gap: 8 } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Rebalance suggestions"),
      ...suggestions.map((suggestion) => {
        const candidate = rebalanceCandidates.find((item) => item.suggestion.title === suggestion.title);
        return React.createElement("div", {
          key: suggestion.title,
          style: {
            display: "grid",
            gap: 8,
            padding: 10,
            borderRadius: 10,
            border: "1px solid rgba(148,163,184,0.18)",
            background: "rgba(2,6,23,0.72)",
          }
        },
          React.createElement("button", {
            type: "button",
            onClick: () => onSelectFilter(suggestion.filterKey),
            style: {
              display: "grid",
              gap: 4,
              textAlign: "left",
              padding: 0,
              border: "none",
              background: "transparent",
              color: "#e2e8f0",
              cursor: "pointer",
            }
          },
            React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" } },
              React.createElement("div", { style: { fontSize: 13, fontWeight: 700, color: "#f8fafc" } }, suggestion.title),
              React.createElement("span", { style: badgeStyle(suggestion.tone) }, suggestion.tone === "danger" ? "High leverage" : "Suggested")
            ),
            React.createElement("div", { style: { fontSize: 12, color: "#cbd5e1", lineHeight: 1.5 } }, suggestion.detail)
          ),
          candidate ? React.createElement("div", { style: { display: "grid", gap: 6 } },
            React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" } },
              React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, `Suggested item: ${candidate.entry.taskSummary || 'Untitled review'}`),
              React.createElement("button", { type: "button", onClick: () => onReassignSuggestion(candidate.entry, suggestion.toOwner), style: buttonStyle("secondary") }, `Reassign to ${suggestion.toOwner}`)
            ),
            React.createElement("div", { style: { fontSize: 11, color: "#94a3b8", lineHeight: 1.5 } }, explainRebalanceCandidate(candidate.entry, suggestion))
          ) : null
        );
      })
    ) : null
  );
}

function OperatorDashboard({ scopedEntries, companyEntries, exportedRecords, activeDashboardFilter, onSelectFilter, currentOwnerLabel, onReassignSuggestion }) {
  const stats = buildDashboardStats({ scopedEntries, companyEntries, exportedRecords, currentOwnerLabel });
  return React.createElement("div", { style: { display: "grid", gap: 10 } },
    React.createElement("div", { style: mutedHeadingStyle() }, "Operator dashboard"),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 } },
      ...stats.map((item) => React.createElement(SummaryCard, { key: item.label, label: item.label, value: item.value, tone: item.tone, active: activeDashboardFilter === item.filterKey, onClick: () => onSelectFilter(activeDashboardFilter === item.filterKey ? null : item.filterKey) }))
    ),
    React.createElement(TeamLoadPanel, { entries: companyEntries, currentOwnerLabel, onSelectFilter, activeDashboardFilter, onReassignSuggestion })
  );
}

function applyDashboardHistoryFilter(entries, activeDashboardFilter, scope, currentOwnerLabel = null) {
  if (typeof activeDashboardFilter === "string" && activeDashboardFilter.startsWith("owner:")) {
    const owner = activeDashboardFilter.slice("owner:".length);
    return owner ? entries.filter((entry) => entry?.owner === owner) : entries;
  }
  switch (activeDashboardFilter) {
    case "current":
      return scope === "scoped" ? entries : [];
    case "company":
      return scope === "company" ? entries : [];
    case "pinned":
      return entries.filter((entry) => entry?.pinned);
    case "assigned":
      return entries.filter((entry) => entry?.owner && entry.owner !== "unassigned");
    case "my_queue":
      return currentOwnerLabel ? entries.filter((entry) => entry?.owner === currentOwnerLabel && ["blocked", "needs_human", "escalated"].includes(entry?.outcome)) : [];
    case "my_stale":
      return currentOwnerLabel ? entries.filter((entry) => entry?.owner === currentOwnerLabel && ["blocked", "needs_human", "escalated"].includes(entry?.outcome) && getAgingState(entry).stale) : [];
    case "owner_current":
      return currentOwnerLabel ? entries.filter((entry) => entry?.owner === currentOwnerLabel) : [];
    case "needs_human":
      return entries.filter((entry) => entry?.outcome === "needs_human");
    case "blocked":
      return entries.filter((entry) => entry?.outcome === "blocked");
    case "escalated":
      return entries.filter((entry) => entry?.outcome === "escalated");
    case "exported_active":
      return entries.filter((entry) => entry?.exportedEntityId && !entry?.archived);
    case "exported_archived":
      return entries.filter((entry) => entry?.exportedEntityId && entry?.archived);
    default:
      return entries;
  }
}

function syncArchivedFilter(activeDashboardFilter, currentArchivedFilter) {
  if (activeDashboardFilter === "exported_archived") return "archived";
  if (activeDashboardFilter === "exported_active") return "active";
  return currentArchivedFilter;
}

function getAgingState(entry) {
  const createdAtMs = entry?.createdAtMs || 0;
  if (!createdAtMs) return { label: "Unknown age", tone: "neutral", stale: false };
  const ageHours = (Date.now() - createdAtMs) / (1000 * 60 * 60);
  if (ageHours >= 24) return { label: `${Math.round(ageHours)}h old`, tone: "danger", stale: true };
  if (ageHours >= 8) return { label: `${Math.round(ageHours)}h old`, tone: "warn", stale: true };
  if (ageHours >= 2) return { label: `${Math.round(ageHours)}h old`, tone: "info", stale: false };
  return { label: "Fresh", tone: "success", stale: false };
}

function buildPriorityQueue(companyEntries, ownerFilter = null) {
  const priorityOrder = { blocked: 0, needs_human: 1, escalated: 2 };
  return companyEntries
    .filter((entry) => ["blocked", "needs_human", "escalated"].includes(entry?.outcome))
    .filter((entry) => {
      if (!ownerFilter) return true;
      if (ownerFilter === "assigned") return entry?.owner && entry.owner !== "unassigned";
      return String(entry?.owner || "unassigned") === ownerFilter;
    })
    .sort((a, b) => {
      const left = priorityOrder[a?.outcome] ?? 99;
      const right = priorityOrder[b?.outcome] ?? 99;
      if (left !== right) return left - right;
      const staleDelta = Number(getAgingState(b).stale) - Number(getAgingState(a).stale);
      if (staleDelta !== 0) return staleDelta;
      return (b?.createdAtMs || 0) - (a?.createdAtMs || 0);
    })
    .slice(0, 6);
}

function PriorityQueuePanel({ entries, onRestore, onSetOutcome, onSetPinned, onSetOwner, onFocusAudit }) {
  if (!entries.length) return null;
  return React.createElement("div", { style: { display: "grid", gap: 12, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.78)", border: "1px solid rgba(248,113,113,0.22)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Priority queue"),
      React.createElement("div", { style: { fontSize: 12, color: "#fca5a5" } }, "Blocked, needs human, and escalated reviews float to the top here.")
    ),
    ...entries.map((entry) => React.createElement("div", {
      key: `priority-${entry.id}`,
      style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, border: "1px solid rgba(248,113,113,0.18)", background: "rgba(2,6,23,0.72)" }
    },
      React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" } },
        React.createElement("div", { style: { fontSize: 14, fontWeight: 700, color: "#f8fafc" } }, entry.taskSummary || "Untitled review"),
        React.createElement("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
          entry.outcome ? React.createElement("span", { style: badgeStyle(entry.outcome === "blocked" ? "danger" : entry.outcome === "needs_human" ? "warn" : "info") }, outcomeLabel(entry.outcome)) : null,
          React.createElement("span", { style: badgeStyle(getAgingState(entry).tone) }, getAgingState(entry).label),
          React.createElement("span", { style: badgeStyle("neutral") }, `Owner: ${entry.owner || 'Unassigned'}`),
          entry.pinned ? React.createElement("span", { style: badgeStyle("warn") }, "Pinned") : null,
          entry.decision ? React.createElement("span", { style: badgeStyle("neutral") }, entry.decision) : null
        )
      ),
      React.createElement("div", { style: { fontSize: 12, color: "#cbd5e1", lineHeight: 1.5 } }, entry.recommendedNextStep || entry.contextNotes || entry.content || "No summary available."),
      formatAuditCopy(entry) ? React.createElement("button", { type: "button", onClick: () => onFocusAudit && onFocusAudit(entry), style: { background: "transparent", border: "none", padding: 0, margin: 0, textAlign: "left", cursor: "pointer", fontSize: 11, color: "#64748b" } }, formatAuditCopy(entry)) : null,
      React.createElement(AuditScopeChips, { entry, onFocusAudit }),
      React.createElement("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
        React.createElement("button", { type: "button", onClick: () => onRestore(entry), style: buttonStyle("secondary") }, "Restore"),
        React.createElement("button", { type: "button", onClick: () => onSetPinned(entry.id, !entry.pinned), style: buttonStyle(entry.pinned ? "warn" : "secondary") }, entry.pinned ? "Unpin" : "Pin"),
        React.createElement("select", { value: entry.owner || "unassigned", onChange: (e) => onSetOwner(entry.id, e.target.value), style: { ...inputStyle(false), minWidth: 160, width: 160 } },
          ...OWNER_OPTIONS.map((option) => React.createElement("option", { key: option.value, value: option.value }, option.label))
        ),
        ...OUTCOME_OPTIONS.filter((option) => option.value !== entry.outcome).map((option) => React.createElement("button", { key: option.value, type: "button", onClick: () => onSetOutcome(entry.id, option.value), style: buttonStyle(option.value === "blocked" ? "danger" : option.value === "needs_human" ? "warn" : "secondary") }, option.label))
      )
    ))
  );
}

function HistoryPanel({ scopedEntries, companyEntries, loading, error, onRestore, onClear, onSetOutcome, onSetPinned, onSetOwner, onExport, onFocusAudit, initialOwnerFilter = "all" }) {
  const [searchText, setSearchText] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("all");
  const [pinFilter, setPinFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState(initialOwnerFilter);
  const [sortMode, setSortMode] = useState("newest");
  useEffect(() => {
    setOwnerFilter(initialOwnerFilter);
  }, [initialOwnerFilter]);
  const filteredScopedEntries = useMemo(
    () => filterHistoryEntries(scopedEntries, "", "all", "all", sortMode, ownerFilter),
    [scopedEntries, sortMode, ownerFilter]
  );
  const filteredCompanyEntries = useMemo(
    () => filterHistoryEntries(companyEntries, searchText, outcomeFilter, pinFilter, sortMode, ownerFilter),
    [companyEntries, searchText, outcomeFilter, pinFilter, sortMode, ownerFilter]
  );
  if (loading) {
    return React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "Loading review history...");
  }
  if (error) {
    return React.createElement("div", { style: { fontSize: 13, color: "#fca5a5" } }, `History unavailable: ${error.message || error}`);
  }
  if (!scopedEntries.length && !companyEntries.length) return null;
  return React.createElement("div", { style: { display: "grid", gap: 12, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Review history"),
      React.createElement("button", { type: "button", onClick: onClear, style: buttonStyle("secondary") }, "Clear current scope")
    ),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) 180px 160px 180px 160px", gap: 10 } },
      React.createElement("input", {
        value: searchText,
        onChange: (e) => setSearchText(e.target.value),
        placeholder: "Search shared history by summary, decision, lane, model, or scope",
        style: inputStyle(false),
      }),
      React.createElement("select", {
        value: outcomeFilter,
        onChange: (e) => setOutcomeFilter(e.target.value),
        style: inputStyle(false),
      },
        React.createElement("option", { value: "all" }, "All outcomes"),
        ...OUTCOME_OPTIONS.map((option) => React.createElement("option", { key: option.value, value: option.value }, option.label))
      ),
      React.createElement("select", {
        value: pinFilter,
        onChange: (e) => setPinFilter(e.target.value),
        style: inputStyle(false),
      },
        React.createElement("option", { value: "all" }, "All pins"),
        React.createElement("option", { value: "pinned" }, "Pinned only"),
        React.createElement("option", { value: "unpinned" }, "Unpinned only")
      ),
      React.createElement("select", {
        value: ownerFilter,
        onChange: (e) => setOwnerFilter(e.target.value),
        style: inputStyle(false),
      },
        React.createElement("option", { value: "all" }, "All owners"),
        React.createElement("option", { value: "assigned" }, "Assigned only"),
        ...OWNER_OPTIONS.map((option) => React.createElement("option", { key: option.value, value: option.value }, option.label))
      ),
      React.createElement("select", {
        value: sortMode,
        onChange: (e) => setSortMode(e.target.value),
        style: inputStyle(false),
      },
        React.createElement("option", { value: "newest" }, "Newest first"),
        React.createElement("option", { value: "oldest" }, "Oldest first")
      )
    ),
    React.createElement(HistoryList, {
      title: "Current context",
      subtitle: `${filteredScopedEntries.length} reviews tied to this entity`,
      entries: filteredScopedEntries,
      onRestore,
      onSetOutcome,
      onSetPinned,
      onSetOwner,
      onExport,
      onFocusAudit,
      emptyText: "No reviews saved for this entity yet."
    }),
    React.createElement(HistoryList, {
      title: "Company-wide recent reviews",
      subtitle: `${filteredCompanyEntries.length} of ${companyEntries.length} shared reviews across this Paperclip company`,
      entries: filteredCompanyEntries,
      onRestore,
      onSetOutcome,
      onSetPinned,
      onSetOwner,
      onExport,
      onFocusAudit,
      emptyText: "No shared company reviews yet."
    })
  );
}

export function ExternalReviewLauncherPanel() {
  const host = useHostContext();
  const canInvokeAgentReview = hasValidAgentContext(host);
  const invoke = usePluginAction("invoke_external_review");
  const saveReviewHistory = usePluginAction("save_review_history");
  const setReviewOutcome = usePluginAction("set_review_outcome");
  const setReviewPinned = usePluginAction("set_review_pinned");
  const setReviewOwner = usePluginAction("set_review_owner");
  const clearReviewHistory = usePluginAction("clear_review_history");
  const exportReviewRecord = usePluginAction("export_review_record");
  const setExportedReviewArchived = usePluginAction("set_exported_review_archived");
  const toast = usePluginToast();
  const [reviewType, setReviewType] = useState("architecture_review");
  const [priority, setPriority] = useState("normal");
  const [taskSummary, setTaskSummary] = useState(() => summaryFromContext(host));
  const [content, setContent] = useState("Please review the current agent context and provide a decision, risks, and recommended next step.");
  const [contextNotes, setContextNotes] = useState(() => buildContextNotes(host));
  const [availableAgents, setAvailableAgents] = useState([]);
  const [selectedAgentId, setSelectedAgentId] = useState(() => host?.entityType === "agent" ? host?.entityId ?? "" : "");
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [agentsError, setAgentsError] = useState(null);
  const historyQuery = usePluginData("review_history", {
    companyId: host?.companyId ?? undefined,
    entityId: host?.entityId ?? undefined,
    context: {
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
    },
  });
  const [archivedFilter, setArchivedFilter] = useState("active");
  const [activeDashboardFilter, setActiveDashboardFilter] = useState(null);
  const [selectedAuditEntryId, setSelectedAuditEntryId] = useState(null);
  const [scopedAuditEventType, setScopedAuditEventType] = useState(null);
  const [scopedAuditActor, setScopedAuditActor] = useState(null);
  const exportedRecordsQuery = usePluginData("exported_review_records", {
    companyId: host?.companyId ?? undefined,
    archivedFilter,
    context: host,
  });
  const auditEventsQuery = usePluginData("review_audit_events", {
    companyId: host?.companyId ?? undefined,
    entryId: selectedAuditEntryId ?? undefined,
    context: host,
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState({ scoped: [], company: [] });
  const [currentOutcome, setCurrentOutcome] = useState(null);
  const [error, setError] = useState(null);
  const [pendingUndo, setPendingUndo] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!host?.companyId || host?.entityType === "agent") return undefined;
    setAgentsLoading(true);
    setAgentsError(null);
    fetchCompanyAgents(host.companyId)
      .then((agents) => {
        if (cancelled) return;
        setAvailableAgents(agents);
        if (!selectedAgentId && agents.length > 0) {
          const preferred = agents.find((agent) => agent?.status === "idle") || agents[0];
          setSelectedAgentId(preferred?.id || "");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setAgentsError(err?.message || "Failed to load agents");
      })
      .finally(() => {
        if (!cancelled) setAgentsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [host?.companyId, host?.entityType]);

  const effectiveEntityType = host?.entityType === "agent" ? "agent" : (selectedAgentId ? "agent" : host?.entityType ?? null);
  const effectiveEntityId = host?.entityType === "agent" ? (host?.entityId ?? null) : (selectedAgentId || null);
  const canSubmitFromPage = Boolean(host?.companyId && effectiveEntityType === "agent" && effectiveEntityId);

  const contextPreview = useMemo(() => ({
    companyId: host?.companyId ?? null,
    entityType: effectiveEntityType,
    entityId: effectiveEntityId,
    projectId: host?.projectId ?? null,
    parentEntityId: host?.parentEntityId ?? null,
    userId: host?.userId ?? null,
  }), [host, effectiveEntityType, effectiveEntityId]);

  const currentOwnerLabel = useMemo(() => {
    const preferred = [host?.userName, host?.userDisplayName, host?.userLabel, host?.renderEnvironment?.userName, host?.renderEnvironment?.userDisplayName, host?.renderEnvironment?.userLabel]
      .find((value) => typeof value === "string" && value.trim());
    if (preferred) return preferred.trim();
    if (host?.userId === "7529788084") return "Andrew";
    return null;
  }, [host]);

  function buildAuditIntent(reason, entryId, extras = {}) {
    return {
      actor: currentOwnerLabel || 'Operator',
      reason,
      correlationId: extras.correlationId || `${entryId || 'review'}-${reason}-${Date.now()}`,
      sourceSurface: 'external_review_ui',
      ...extras,
    };
  }

  useEffect(() => {
    if (historyQuery.data && typeof historyQuery.data === "object") {
      const scoped = Array.isArray(historyQuery.data.scoped) ? historyQuery.data.scoped : [];
      const company = Array.isArray(historyQuery.data.company) ? historyQuery.data.company : [];
      setHistory({ scoped, company });
      persistHistory(scoped);
    } else if (!historyQuery.loading && !historyQuery.data) {
      setHistory({ scoped: loadStoredHistory(), company: [] });
    }
  }, [historyQuery.data, historyQuery.loading]);

  useEffect(() => {
    if (!result) return;
    const normalized = normalizeResultEnvelope(result);
    if (normalized.queued || !normalized.decision) {
      return;
    }
    const entry = {
      id: normalized.correlationId || `${Date.now()}`,
      createdAtLabel: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      createdAtMs: Date.now(),
      taskSummary,
      reviewType,
      priority,
      owner: "unassigned",
      content,
      contextNotes,
      decision: normalized.decision,
      recommendedNextStep: normalized.recommendedNextStep,
      lane: normalized.lane,
      model: normalized.model,
    };
    setCurrentOutcome(entry.outcome || null);
    setSelectedAuditEntryId(entry.id);
    setHistory((prev) => ({
      scoped: [entry, ...prev.scoped.filter((item) => item.id !== entry.id)].slice(0, HISTORY_LIMIT),
      company: [{ ...entry, scopeId: host?.entityId ?? null }, ...prev.company.filter((item) => item.id !== entry.id)].slice(0, HISTORY_LIMIT),
    }));
    saveReviewHistory({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
      },
      entry,
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
    }).catch(() => {
      persistHistory([entry, ...history.scoped.filter((item) => item.id !== entry.id)].slice(0, HISTORY_LIMIT));
    });
  }, [result]);

  useEffect(() => {
    return () => {
      if (pendingUndo?.timeoutId) window.clearTimeout(pendingUndo.timeoutId);
    };
  }, [pendingUndo]);

  function handleReuseAsFollowUp(normalized) {
    const followUpLines = [
      normalized.recommendedNextStep ? `Execute this next step: ${normalized.recommendedNextStep}` : "Follow up on the external review outcome.",
      normalized.topRisks.length ? `Address these risks: ${normalized.topRisks.join('; ')}` : null,
      normalized.decision ? `Current decision context: ${formatDecision(normalized.decision)}` : null,
    ].filter(Boolean);
    setTaskSummary(`Follow-up for ${taskSummary}`);
    setContent(followUpLines.join("\n\n"));
    setError(null);
    toast({ tone: "success", title: "Follow-up draft ready", body: "The review output has been converted into a follow-up draft." });
  }

  function handleEscalate(normalized) {
    const escalationLines = [
      "Escalation requested. Re-review this item with higher urgency and sharper decision pressure.",
      normalized.decision ? `Prior review decision: ${formatDecision(normalized.decision)}` : null,
      normalized.recommendedNextStep ? `Previous recommended next step: ${normalized.recommendedNextStep}` : null,
      normalized.topRisks.length ? `Unresolved risks: ${normalized.topRisks.join('; ')}` : null,
      normalized.summary ? `Previous review summary: ${normalized.summary}` : null,
      "Return a firmer decision, the highest-risk blocker, and the exact next operator move.",
    ].filter(Boolean);
    setReviewType("operational_review");
    setPriority("urgent");
    setTaskSummary(`Escalation: ${taskSummary}`);
    setContent(escalationLines.join("\n\n"));
    setContextNotes((prev) => {
      const prefix = prev?.trim() ? `${prev.trim()}\n\n` : "";
      return `${prefix}escalation_requested: true\nescalation_source: external_review_ui\nprevious_lane: ${normalized.lane || 'unknown'}\nprevious_model: ${normalized.model || 'unknown'}`;
    });
    setError(null);
    toast({ tone: "success", title: "Escalation draft ready", body: "The drawer has been prefilled for a higher-priority follow-up review." });
  }

  function handleApplyPreset(preset, normalized) {
    const prefix = preset?.taskSummaryPrefix ? `${preset.taskSummaryPrefix}: ` : "";
    setReviewType(preset?.reviewType || reviewType);
    setPriority(preset?.priority || priority);
    setTaskSummary(`${prefix}${taskSummary}`);
    setContent([
      normalized?.recommendedNextStep ? `Focus first on: ${normalized.recommendedNextStep}` : null,
      normalized?.topRisks?.length ? `Reassess these risks: ${normalized.topRisks.join('; ')}` : null,
      content,
    ].filter(Boolean).join("\n\n"));
    setError(null);
    toast({ tone: "success", title: "Preset applied", body: "The form has been prefilled for a targeted rerun." });
  }

  function handleSetCurrentOutcome(outcome, normalized) {
    setCurrentOutcome(outcome);
    const targetId = normalized?.correlationId || null;
    if (!targetId) return;
    setHistory((prev) => ({
      scoped: prev.scoped.map((entry) => entry.id === targetId ? { ...entry, outcome } : entry),
      company: prev.company.map((entry) => entry.id === targetId ? { ...entry, outcome } : entry),
    }));
    setReviewOutcome({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
      },
      entryId: targetId,
      outcome,
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
    }).catch(() => {
      persistHistory(history.scoped.map((entry) => entry.id === targetId ? { ...entry, outcome } : entry));
    });
    toast({ tone: "success", title: "Outcome updated", body: `Marked review as ${formatOutcome(outcome)}.` });
  }

  function handleHistoryOutcome(entryId, outcome) {
    setHistory((prev) => ({
      scoped: prev.scoped.map((entry) => entry.id === entryId ? { ...entry, outcome } : entry),
      company: prev.company.map((entry) => entry.id === entryId ? { ...entry, outcome } : entry),
    }));
    if (history.scoped.find((entry) => entry.id === entryId)?.id === (normalizeResultEnvelope(result || {}).correlationId || null)) {
      setCurrentOutcome(outcome);
    }
    setReviewOutcome({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
        userName: currentOwnerLabel || undefined,
        userDisplayName: currentOwnerLabel || undefined,
      },
      entryId,
      outcome,
      ...buildAuditIntent('manual_outcome_update', entryId),
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
    }).catch(() => {
      persistHistory(history.scoped.map((entry) => entry.id === entryId ? { ...entry, outcome } : entry));
    });
    toast({ tone: "success", title: "Outcome updated", body: `Marked review as ${formatOutcome(outcome)}.` });
  }

  function handleSetPinned(entryId, pinned) {
    setHistory((prev) => ({
      scoped: prev.scoped.map((entry) => entry.id === entryId ? { ...entry, pinned } : entry),
      company: prev.company.map((entry) => entry.id === entryId ? { ...entry, pinned } : entry),
    }));
    setReviewPinned({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
        userName: currentOwnerLabel || undefined,
        userDisplayName: currentOwnerLabel || undefined,
      },
      entryId,
      pinned,
      ...buildAuditIntent(pinned ? 'manual_pin' : 'manual_unpin', entryId),
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
    }).catch(() => {
      persistHistory(history.scoped.map((entry) => entry.id === entryId ? { ...entry, pinned } : entry));
    });
    toast({ tone: "success", title: pinned ? "Review pinned" : "Review unpinned", body: pinned ? "Pinned review will stay surfaced in history." : "Review returned to normal history ordering." });
  }

  function handleExportRecord(entry) {
    const normalizedEntry = {
      ...entry,
      scopeId: entry.scopeId || host?.entityId || null,
    };
    exportReviewRecord({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        ...host,
        userName: currentOwnerLabel || undefined,
        userDisplayName: currentOwnerLabel || undefined,
      },
      entry: normalizedEntry,
      ...buildAuditIntent('manual_export', normalizedEntry.id),
    }).then((result) => {
      if (result?.history && typeof result.history === "object") {
        setHistory({
          scoped: Array.isArray(result.history.scoped) ? result.history.scoped : [],
          company: Array.isArray(result.history.company) ? result.history.company : [],
        });
      }
      toast({ tone: "success", title: "Review exported", body: "Review is now stored as a Paperclip record." });
    }).catch((error) => {
      toast({ tone: "error", title: "Export failed", body: error?.message || "Could not export review record." });
    });
  }

  function handleToggleArchived(record, archived) {
    const entryId = record.externalId || record.data?.externalId || record.data?.id;
    setHistory((prev) => ({
      scoped: prev.scoped.map((entry) => entry.exportedEntityId === record.id ? { ...entry, archived } : entry),
      company: prev.company.map((entry) => entry.exportedEntityId === record.id ? { ...entry, archived } : entry),
    }));
    setExportedReviewArchived({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        ...host,
        userName: currentOwnerLabel || undefined,
        userDisplayName: currentOwnerLabel || undefined,
      },
      recordId: record.id,
      entryId,
      externalId: entryId,
      archived,
      ...buildAuditIntent(archived ? 'manual_archive_export' : 'manual_restore_export', entryId),
    }).then((result) => {
      if (result?.history && typeof result.history === "object") {
        setHistory({
          scoped: Array.isArray(result.history.scoped) ? result.history.scoped : [],
          company: Array.isArray(result.history.company) ? result.history.company : [],
        });
      }
      toast({ tone: "success", title: archived ? "Record archived" : "Record restored", body: archived ? "Exported review record has been archived from the active list." : "Exported review record is active again." });
    }).catch((error) => {
      toast({ tone: "error", title: archived ? "Archive failed" : "Restore failed", body: error?.message || "Could not update exported record state." });
    });
  }

  function handleRestoreExportedRecord(record) {
    const data = record?.data || {};
    setReviewType(data.reviewType || "architecture_review");
    setPriority(data.priority || "normal");
    setTaskSummary(data.taskSummary || record?.title || summaryFromContext(host));
    setContent(data.content || "");
    setContextNotes(data.contextNotes || buildContextNotes(host));
    setCurrentOutcome(data.outcome || null);
    setError(null);
    toast({ tone: "success", title: "Exported review restored", body: "The exported review has been loaded back into the form." });
  }

  function handleSelectDashboardFilter(filterKey) {
    setActiveDashboardFilter(filterKey);
    setArchivedFilter((current) => syncArchivedFilter(filterKey, current));
  }

  function handleFocusAudit(item, overrides = {}) {
    setSelectedAuditEntryId(item?.id || item?.externalId || null);
    setScopedAuditEventType(overrides.eventType ?? item?.lastAuditEventType ?? null);
    setScopedAuditActor(overrides.actor ?? item?.lastAuditEventActor ?? item?.lastReassignedBy ?? null);
  }

  function handleClearAuditScope() {
    setScopedAuditEventType(null);
    setScopedAuditActor(null);
  }

  function applyOwnerUpdate(entryId, owner, successBody = `Assigned to ${owner}.`, options = {}) {
    setHistory((prev) => ({
      scoped: prev.scoped.map((entry) => entry.id === entryId ? { ...entry, owner } : entry),
      company: prev.company.map((entry) => entry.id === entryId ? { ...entry, owner } : entry),
    }));
    return setReviewOwner({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
        userName: currentOwnerLabel || undefined,
        userDisplayName: currentOwnerLabel || undefined,
      },
      entryId,
      owner,
      actor: options.actor || currentOwnerLabel || 'Operator',
      reason: options.reason || 'owner_update',
      previousOwner: options.previousOwner,
      correlationId: options.correlationId,
      sourceSurface: 'external_review_ui',
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
      toast({ tone: "success", title: "Owner updated", body: successBody });
      return next;
    });
  }

  function clearPendingUndo() {
    setPendingUndo((current) => {
      if (current?.timeoutId) window.clearTimeout(current.timeoutId);
      return null;
    });
  }

  function scheduleUndo(entry, previousOwner, nextOwner) {
    setPendingUndo((current) => {
      if (current?.timeoutId) window.clearTimeout(current.timeoutId);
      const timeoutId = window.setTimeout(() => {
        setPendingUndo(null);
      }, 12000);
      return {
        entryId: entry.id,
        taskSummary: entry.taskSummary || 'Untitled review',
        previousOwner,
        nextOwner,
        timeoutId,
      };
    });
  }

  function handleSetOwner(entryId, owner) {
    applyOwnerUpdate(entryId, owner, `Assigned to ${owner}.`, { reason: 'manual_assignment' }).catch((err) => {
      toast({ tone: "error", title: "Owner update failed", body: err?.message || "Could not assign review owner." });
    });
  }

  function handleReassignSuggestion(entry, owner) {
    if (!entry?.id || !owner) return;
    const previousOwner = entry?.owner || 'unassigned';
    const correlationId = `${entry.id}-reassign-${Date.now()}`;
    applyOwnerUpdate(entry.id, owner, `Reassigned \"${entry.taskSummary || 'Untitled review'}\" to ${owner}. Undo available for 12s.`, {
      reason: 'guided_reassignment',
      previousOwner,
      correlationId,
    })
      .then(() => {
        scheduleUndo(entry, previousOwner, owner);
      })
      .catch((err) => {
        toast({ tone: "error", title: "Reassignment failed", body: err?.message || "Could not reassign suggested review." });
      });
  }

  function handleUndoReassignment() {
    if (!pendingUndo?.entryId || !pendingUndo?.previousOwner) return;
    const undo = pendingUndo;
    clearPendingUndo();
    applyOwnerUpdate(undo.entryId, undo.previousOwner, `Restored \"${undo.taskSummary}\" back to ${undo.previousOwner}.`, {
      reason: 'undo_reassignment',
      previousOwner: undo.nextOwner,
      correlationId: `${undo.entryId}-undo-${Date.now()}`,
    }).catch((err) => {
      toast({ tone: "error", title: "Undo failed", body: err?.message || "Could not restore previous owner." });
    });
  }

  function handleClearHistory() {
    setHistory({ scoped: [], company: history.company });
    clearReviewHistory({
      companyId: host?.companyId ?? undefined,
      entityId: host?.entityId ?? undefined,
      context: {
        companyId: host?.companyId ?? undefined,
        entityId: host?.entityId ?? undefined,
      },
    }).then((next) => {
      if (next && typeof next === "object") {
        setHistory({
          scoped: Array.isArray(next.scoped) ? next.scoped : [],
          company: Array.isArray(next.company) ? next.company : [],
        });
      }
    }).catch(() => {
      persistHistory([]);
    });
    toast({ tone: "success", title: "History cleared", body: "Saved review history was cleared." });
  }

  function handleRestoreHistory(entry) {
    setReviewType(entry.reviewType || "architecture_review");
    setPriority(entry.priority || "normal");
    setTaskSummary(entry.taskSummary || summaryFromContext(host));
    setContent(entry.content || "");
    setContextNotes(entry.contextNotes || buildContextNotes(host));
    setCurrentOutcome(entry.outcome || null);
    setSelectedAuditEntryId(entry.id || null);
    setScopedAuditEventType(null);
    setScopedAuditActor(null);
    setError(null);
    toast({ tone: "success", title: "Review restored", body: "A recent review attempt has been restored into the form." });
  }

  async function handleSubmit(event) {
    event?.preventDefault?.();
    if (!canSubmitFromPage) {
      const message = "Select an agent before submitting an external review from the page view.";
      setError(message);
      toast({ tone: "warn", title: "Agent context required", body: message });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await invoke({
        companyId: host?.companyId ?? undefined,
        entityType: effectiveEntityType ?? undefined,
        entityId: effectiveEntityId ?? undefined,
        context: {
          companyId: host?.companyId ?? undefined,
          companyPrefix: host?.companyPrefix ?? undefined,
          projectId: host?.projectId ?? undefined,
          entityType: effectiveEntityType ?? undefined,
          entityId: effectiveEntityId ?? undefined,
          parentEntityId: host?.parentEntityId ?? undefined,
          userId: host?.userId ?? undefined,
          renderEnvironment: host?.renderEnvironment ?? undefined,
          source: "external_review_ui_drawer",
          title: taskSummary,
        },
        reviewType,
        priority,
        taskSummary,
        content,
        contextNotes,
      });
      const normalized = normalizeResultEnvelope(response);
      setResult(response);
      toast({ tone: "success", title: normalized.queued ? "External review queued" : "External review submitted", body: normalized.queued ? `Agent run started${normalized.runId ? ` (${normalized.runId})` : ''}.` : "Specialist invocation completed successfully." });
    } catch (err) {
      const message = err?.message || "External review failed";
      setError(message);
      toast({ tone: "error", title: "External review failed", body: message });
    } finally {
      setSubmitting(false);
    }
  }

  return React.createElement(
    "form",
    { onSubmit: handleSubmit, style: cardStyle() },
    React.createElement("div", { style: { display: "grid", gap: 4 } },
      React.createElement("div", { style: { fontSize: 18, fontWeight: 700, color: "#f8fafc" } }, "External Review"),
      React.createElement("div", { style: { fontSize: 13, color: "#94a3b8" } }, "Submit a structured review request with explicit scope before invoking the specialist lane.")
    ),
    React.createElement("div", { style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Detected context"),
      React.createElement("pre", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#93c5fd" } }, JSON.stringify(contextPreview, null, 2))
    ),
    host?.entityType !== "agent" ? React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(59,130,246,0.12)", border: "1px solid rgba(59,130,246,0.28)", color: "#dbeafe" } },
      React.createElement("div", { style: { fontWeight: 700, fontSize: 13 } }, "Page mode: choose an agent for submission"),
      React.createElement("div", { style: { fontSize: 13, color: "#bfdbfe", lineHeight: 1.5 } }, "This page opened at company scope, so I loaded the available agents for you. Pick one below, then submit the external review normally."),
      React.createElement("label", { style: labelStyle() },
        React.createElement("span", null, "Target agent"),
        React.createElement("select", {
          value: selectedAgentId,
          onChange: (event) => setSelectedAgentId(event.target.value),
          style: inputStyle(false),
          disabled: agentsLoading || availableAgents.length === 0,
        },
          React.createElement("option", { value: "" }, agentsLoading ? "Loading agents..." : "Select an agent"),
          availableAgents.map((agent) => React.createElement("option", { key: agent.id, value: agent.id }, `${agent.name || agent.title || agent.id}${agent.status ? ` (${agent.status})` : ""}`))
        )
      ),
      agentsError ? React.createElement("div", { style: { fontSize: 12, color: "#fca5a5" } }, agentsError) : null,
      !canSubmitFromPage ? React.createElement("div", { style: { fontSize: 12, color: "#fde68a" } }, "Choose an agent to enable submission.") : null
    ) : null,
    React.createElement(WhatsNewPanel),
    pendingUndo ? React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: 12, borderRadius: 10, border: "1px solid rgba(251,191,36,0.28)", background: "rgba(120,53,15,0.18)" } },
      React.createElement("div", { style: { display: "grid", gap: 2 } },
        React.createElement("div", { style: { fontSize: 13, fontWeight: 700, color: "#fde68a" } }, "Recent reassignment"),
        React.createElement("div", { style: { fontSize: 12, color: "#fcd34d" } }, `${pendingUndo.taskSummary} moved from ${pendingUndo.previousOwner} to ${pendingUndo.nextOwner}.`)
      ),
      React.createElement("button", { type: "button", onClick: handleUndoReassignment, style: buttonStyle("warn") }, "Undo reassignment")
    ) : null,
    React.createElement(OperatorDashboard, {
      scopedEntries: history.scoped,
      companyEntries: history.company,
      exportedRecords: Array.isArray(exportedRecordsQuery.data) ? exportedRecordsQuery.data : [],
      activeDashboardFilter,
      currentOwnerLabel,
      onSelectFilter: handleSelectDashboardFilter,
      onReassignSuggestion: handleReassignSuggestion,
    }),
    React.createElement(PriorityQueuePanel, { entries: buildPriorityQueue(history.company, activeDashboardFilter === "assigned" ? "assigned" : activeDashboardFilter === "owner_current" || activeDashboardFilter === "my_queue" || activeDashboardFilter === "my_stale" ? currentOwnerLabel : null).filter((entry) => activeDashboardFilter === "my_stale" ? getAgingState(entry).stale : true), onRestore: handleRestoreHistory, onSetOutcome: handleHistoryOutcome, onSetPinned: handleSetPinned, onSetOwner: handleSetOwner, onFocusAudit: handleFocusAudit }),
    React.createElement(HistoryPanel, { scopedEntries: applyDashboardHistoryFilter(history.scoped, activeDashboardFilter, "scoped", currentOwnerLabel), companyEntries: applyDashboardHistoryFilter(history.company, activeDashboardFilter, "company", currentOwnerLabel), loading: historyQuery.loading, error: historyQuery.error, onRestore: handleRestoreHistory, onClear: handleClearHistory, onSetOutcome: handleHistoryOutcome, onSetPinned: handleSetPinned, onSetOwner: handleSetOwner, onExport: handleExportRecord, onFocusAudit: handleFocusAudit, initialOwnerFilter: activeDashboardFilter === "assigned" ? "assigned" : activeDashboardFilter === "owner_current" || activeDashboardFilter === "my_queue" || activeDashboardFilter === "my_stale" ? (currentOwnerLabel || "all") : "all" }),
    React.createElement(ExportedRecordsPanel, { records: Array.isArray(exportedRecordsQuery.data) ? exportedRecordsQuery.data : [], loading: exportedRecordsQuery.loading, error: exportedRecordsQuery.error, archivedFilter, setArchivedFilter, onToggleArchived: handleToggleArchived, onRestoreRecord: handleRestoreExportedRecord, onFocusAudit: handleFocusAudit }),
    React.createElement(AuditTimelinePanel, { events: Array.isArray(auditEventsQuery.data) ? auditEventsQuery.data : [], loading: auditEventsQuery.loading, error: auditEventsQuery.error, entryId: selectedAuditEntryId, scopedEventType: scopedAuditEventType, scopedActor: scopedAuditActor, onClearScope: handleClearAuditScope }),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 } },
      React.createElement("label", { style: labelStyle() },
        React.createElement("span", null, "Review type"),
        React.createElement("select", { value: reviewType, onChange: (e) => setReviewType(e.target.value), style: inputStyle(false) },
          ...REVIEW_TYPES.map((item) => React.createElement("option", { key: item.value, value: item.value }, item.label))
        )
      ),
      React.createElement("label", { style: labelStyle() },
        React.createElement("span", null, "Priority"),
        React.createElement("select", { value: priority, onChange: (e) => setPriority(e.target.value), style: inputStyle(false) },
          ...PRIORITIES.map((item) => React.createElement("option", { key: item.value, value: item.value }, item.label))
        )
      )
    ),
    React.createElement("label", { style: labelStyle() },
      React.createElement("span", null, "Task summary"),
      React.createElement("input", { value: taskSummary, onChange: (e) => setTaskSummary(e.target.value), style: inputStyle(false), placeholder: "What should the specialist review?" })
    ),
    React.createElement("label", { style: labelStyle() },
      React.createElement("span", null, "Review content"),
      React.createElement("textarea", { value: content, onChange: (e) => setContent(e.target.value), style: inputStyle(true), placeholder: "Describe the context, target decision, constraints, and what kind of review you want back." })
    ),
    React.createElement("label", { style: labelStyle() },
      React.createElement("span", null, "Context notes"),
      React.createElement("textarea", { value: contextNotes, onChange: (e) => setContextNotes(e.target.value), style: inputStyle(true), placeholder: "Optional: add supporting notes, risks, or relevant surrounding context." })
    ),
    error ? React.createElement("div", { style: { color: "#fca5a5", fontSize: 13 } }, error) : null,
    React.createElement("div", { style: { display: "flex", justifyContent: "flex-end", gap: 10 } },
      React.createElement("button", { type: "submit", disabled: submitting, style: buttonStyle("primary") }, submitting ? "Submitting..." : "Submit external review")
    ),
    result ? React.createElement(ResultPanel, { result, currentOutcome, onSetOutcome: handleSetCurrentOutcome, onReuseAsFollowUp: handleReuseAsFollowUp, onEscalate: handleEscalate, onApplyPreset: handleApplyPreset, toast }) : null
  );
}

export default ExternalReviewLauncherPanel;
