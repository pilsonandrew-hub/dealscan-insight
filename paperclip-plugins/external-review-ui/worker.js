import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

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

const plugin = definePlugin({
  id: "local.external-review-ui-v2",
  displayName: "External Review UI",
  version: "0.0.3",
  capabilities: ["agents.invoke"],
  async setup(ctx) {
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
