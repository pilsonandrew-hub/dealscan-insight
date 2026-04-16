import React, { useEffect, useMemo, useState } from "react";
import { useHostContext, usePluginAction, usePluginToast } from "@paperclipai/plugin-sdk/ui";

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
    correlationId: routing?.correlation_id ?? routingMeta?.correlation_id ?? null,
    reviewType: routingMeta?.review_type ?? null,
    sourceContext: routingMeta?.source_context ?? null,
    subject: routingMeta?.subject ?? null,
    priority: routingMeta?.priority ?? null,
    promptTokens: usage?.prompt_tokens ?? null,
    completionTokens: usage?.completion_tokens ?? null,
    totalTokens: usage?.total_tokens ?? null,
    cost: usage?.cost ?? null,
    raw: response,
  };
}

function ResultMetric({ label, value }) {
  return React.createElement("div", { style: { display: "grid", gap: 4 } },
    React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, label),
    React.createElement("div", { style: { fontSize: 14, fontWeight: 600, color: "#f8fafc" } }, value || "N/A")
  );
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

function ResultPanel({ result, onReuseAsFollowUp, onEscalate, onApplyPreset, toast }) {
  const normalized = normalizeResultEnvelope(result);
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

function HistoryPanel({ entries, onRestore, onClear }) {
  if (!entries.length) return null;
  return React.createElement("div", { style: { display: "grid", gap: 10, padding: 12, borderRadius: 10, background: "rgba(15,23,42,0.65)", border: "1px solid rgba(148,163,184,0.18)" } },
    React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" } },
      React.createElement("div", { style: mutedHeadingStyle() }, "Recent review attempts"),
      React.createElement("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
        React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, `${entries.length} stored locally across reloads`),
        React.createElement("button", { type: "button", onClick: onClear, style: buttonStyle("secondary") }, "Clear history")
      )
    ),
    ...entries.map((entry, index) => React.createElement("div", {
      key: entry.id || `${index}-${entry.taskSummary}`,
      style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, background: "rgba(2,6,23,0.75)", border: "1px solid rgba(59,130,246,0.12)" }
    },
      React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" } },
        React.createElement("div", { style: { display: "grid", gap: 4 } },
          React.createElement("div", { style: { fontSize: 14, fontWeight: 700, color: "#f8fafc" } }, entry.taskSummary || "Untitled review"),
          React.createElement("div", { style: { fontSize: 12, color: "#94a3b8" } }, `${entry.reviewType || 'unknown'} • ${entry.priority || 'unknown'} • ${entry.createdAtLabel || 'now'}`)
        ),
        React.createElement("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
          entry.decision ? React.createElement("span", { style: badgeStyle(decisionTone(entry.decision)) }, formatDecision(entry.decision)) : null,
          React.createElement("button", { type: "button", onClick: () => onRestore(entry), style: buttonStyle("secondary") }, "Restore")
        )
      ),
      entry.recommendedNextStep ? React.createElement("div", { style: { fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 } }, entry.recommendedNextStep) : null
    ))
  );
}

export default function ExternalReviewLauncherPanel() {
  const host = useHostContext();
  const invoke = usePluginAction("invoke_external_review");
  const toast = usePluginToast();
  const [reviewType, setReviewType] = useState("architecture_review");
  const [priority, setPriority] = useState("normal");
  const [taskSummary, setTaskSummary] = useState(() => summaryFromContext(host));
  const [content, setContent] = useState("Please review the current agent context and provide a decision, risks, and recommended next step.");
  const [contextNotes, setContextNotes] = useState(() => buildContextNotes(host));
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState(() => loadStoredHistory());
  const [error, setError] = useState(null);

  const contextPreview = useMemo(() => ({
    companyId: host?.companyId ?? null,
    entityType: host?.entityType ?? null,
    entityId: host?.entityId ?? null,
    projectId: host?.projectId ?? null,
    parentEntityId: host?.parentEntityId ?? null,
    userId: host?.userId ?? null,
  }), [host]);

  useEffect(() => {
    persistHistory(history);
  }, [history]);

  useEffect(() => {
    if (!result) return;
    const normalized = normalizeResultEnvelope(result);
    const entry = {
      id: normalized.correlationId || `${Date.now()}`,
      createdAtLabel: new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }),
      createdAtMs: Date.now(),
      taskSummary,
      reviewType,
      priority,
      content,
      contextNotes,
      decision: normalized.decision,
      recommendedNextStep: normalized.recommendedNextStep,
      lane: normalized.lane,
      model: normalized.model,
    };
    setHistory((prev) => [entry, ...prev.filter((item) => item.id !== entry.id)].slice(0, HISTORY_LIMIT));
  }, [result]);

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

  function handleClearHistory() {
    setHistory([]);
    toast({ tone: "success", title: "History cleared", body: "Saved review history was cleared from this browser context." });
  }

  function handleRestoreHistory(entry) {
    setReviewType(entry.reviewType || "architecture_review");
    setPriority(entry.priority || "normal");
    setTaskSummary(entry.taskSummary || summaryFromContext(host));
    setContent(entry.content || "");
    setContextNotes(entry.contextNotes || buildContextNotes(host));
    setError(null);
    toast({ tone: "success", title: "Review restored", body: "A recent review attempt has been restored into the form." });
  }

  async function handleSubmit(event) {
    event?.preventDefault?.();
    setSubmitting(true);
    setError(null);
    try {
      const response = await invoke({
        companyId: host?.companyId ?? undefined,
        entityType: host?.entityType ?? undefined,
        entityId: host?.entityId ?? undefined,
        context: {
          companyId: host?.companyId ?? undefined,
          companyPrefix: host?.companyPrefix ?? undefined,
          projectId: host?.projectId ?? undefined,
          entityType: host?.entityType ?? undefined,
          entityId: host?.entityId ?? undefined,
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
      setResult(response);
      toast({ tone: "success", title: "External review submitted", body: "Specialist invocation completed successfully." });
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
    React.createElement(HistoryPanel, { entries: history, onRestore: handleRestoreHistory, onClear: handleClearHistory }),
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
    result ? React.createElement(ResultPanel, { result, onReuseAsFollowUp: handleReuseAsFollowUp, onEscalate: handleEscalate, onApplyPreset: handleApplyPreset, toast }) : null
  );
}
