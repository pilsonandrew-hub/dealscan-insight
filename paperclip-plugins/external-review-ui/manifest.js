export default {
  id: "local.external-review-ui-v2",
  apiVersion: 1,
  version: "0.1.7",
  displayName: "External Review UI",
  description: "Minimal plugin that exposes a UI action for external specialist review.",
  author: "Ja'various",
  categories: ["automation", "ui"],
  capabilities: ["agents.invoke", "ui.action.register", "plugin.state.read", "plugin.state.write", "ui.page.register"],
  entrypoints: {
    worker: "./worker.js",
    ui: "./ui"
  },
  ui: {
    slots: [
      {
        type: "page",
        id: "external-review-page",
        displayName: "External Review",
        exportName: "ExternalReviewLauncherPanel",
        routePath: "external-review"
      }
    ],
    launchers: [
      {
        id: "invoke-external-review",
        displayName: "External Review",
        description: "Invoke an external specialist review for the current agent context.",
        placementZone: "toolbarButton",
        exportName: "ExternalReviewLauncherPanel",
        entityTypes: ["agent"],
        action: {
          type: "openDrawer",
          target: "ExternalReviewLauncherPanel"
        },
        render: {
          environment: "hostOverlay",
          bounds: "wide"
        }
      },
      {
        id: "invoke-external-review-global",
        displayName: "External Review",
        description: "Open the external review workspace from the Paperclip global toolbar.",
        placementZone: "globalToolbarButton",
        exportName: "ExternalReviewLauncherPanel",
        action: {
          type: "openDrawer",
          target: "ExternalReviewLauncherPanel"
        },
        render: {
          environment: "hostOverlay",
          bounds: "wide"
        }
      },
    ]
  }
};
