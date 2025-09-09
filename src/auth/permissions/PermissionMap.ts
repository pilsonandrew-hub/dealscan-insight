/**
 * Canonical permission keys to avoid string literal drift.
 * Convention: <domain>.<action>
 */
export const PermissionMap = {
  PRICING_READ: 'pricing.read',
  PRICING_WRITE: 'pricing.write',
  ALERTS_VIEW: 'alerts.view',
  ALERTS_MANAGE: 'alerts.manage',
  INVENTORY_READ: 'inventory.read',
  INVENTORY_WRITE: 'inventory.write',
  ADMIN_MANAGE: 'admin.manage'
} as const;

export type PermissionKey = typeof PermissionMap[keyof typeof PermissionMap];

export const ALL_PERMISSIONS = Object.freeze(
  Object.values(PermissionMap)
) as readonly PermissionKey[];