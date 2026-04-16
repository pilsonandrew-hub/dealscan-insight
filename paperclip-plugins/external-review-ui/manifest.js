export default {
  id: "local.external-review-ui-v2",
  apiVersion: 1,
  version: "0.0.4",
  displayName: "External Review UI",
  description: "Minimal plugin that exposes a UI action for external specialist review.",
  author: "Ja'various",
  categories: ["automation", "ui"],
  capabilities: ["agents.invoke", "ui.action.register"],
  entrypoints: {
    worker: "./worker.js",
    ui: "./ui.js"
  },
  launchers: [
    {
      id: "invoke-external-review",
      displayName: "External Review",
      description: "Invoke an external specialist review for the current agent context.",
      placementZone: "toolbarButton",
      entityTypes: ["agent"],
      action: {
        type: "openDrawer",
        target: "ExternalReviewLauncherPanel"
      },
      render: {
        environment: "hostOverlay",
        bounds: "wide"
      }
    }
  ]
};
