# Vercel Deploy Gate Post-Switch Proof

This documentation-only change validates the post-switch behavior after native
Vercel Git deployments were disabled.

Expected behavior:

- Vercel Deploy Gate reports `deploy=false`.
- The gated `vercel-deploy` job is skipped.
- Native Vercel Git deployment does not create a separate Vercel status.
