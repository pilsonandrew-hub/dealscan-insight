import React, { useMemo, useState } from "react";
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
  const [error, setError] = useState(null);

  const contextPreview = useMemo(() => ({
    companyId: host?.companyId ?? null,
    entityType: host?.entityType ?? null,
    entityId: host?.entityId ?? null,
    projectId: host?.projectId ?? null,
    parentEntityId: host?.parentEntityId ?? null,
    userId: host?.userId ?? null,
  }), [host]);

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
      React.createElement("div", { style: { fontSize: 12, fontWeight: 700, color: "#cbd5e1", textTransform: "uppercase", letterSpacing: "0.04em" } }, "Detected context"),
      React.createElement("pre", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#93c5fd" } }, JSON.stringify(contextPreview, null, 2))
    ),
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
    result ? React.createElement("div", { style: { display: "grid", gap: 8, padding: 12, borderRadius: 10, background: "rgba(2,6,23,0.8)", border: "1px solid rgba(59,130,246,0.25)" } },
      React.createElement("div", { style: { fontSize: 12, fontWeight: 700, color: "#cbd5e1", textTransform: "uppercase", letterSpacing: "0.04em" } }, "Latest result"),
      React.createElement("pre", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#bfdbfe" } }, JSON.stringify(result, null, 2))
    ) : null
  );
}
