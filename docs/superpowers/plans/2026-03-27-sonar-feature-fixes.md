# Sonar Feature Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Sonar search experience so state handling, loading, sharing, and result cards are resilient to real-world data and user interaction.

**Architecture:** Keep Sonar-specific behavior in the Sonar tab and card components, but move shared formatting into a utility module and move Sonar animation CSS into the global stylesheet. Tighten the data model only where runtime data can actually differ from the current assumptions, and keep UI fallbacks local to the component that renders them.

**Tech Stack:** React, TypeScript, Tailwind CSS, existing shadcn-style UI primitives, existing toast hook, existing Sonar API adapter.

---

### Task 1: Extract shared formatting and align the Sonar data model

**Files:**
- Create: `src/utils/formatters.ts`
- Modify: `src/components/SonarCard.tsx`
- Modify: `src/components/SonarTab.tsx`
- Modify: `src/services/sonarAPI.ts`

**Exact fixes:**
- Move the duplicated `fmt$` helper into `src/utils/formatters.ts` as a reusable currency formatter export.
- Update both Sonar components to import the shared formatter instead of keeping a local copy.
- Widen the `SonarResult.mileage` type so the UI can safely handle scraped values that are not numeric, including `null` and string markers such as `TMU` or `Exempt`.

**Dependency note:** This should happen before the card hardening work so the display logic can use the shared formatter and the mileage guard can be typed correctly.

---

### Task 2: Harden `SonarCard` against real data and make critical details visible

**Files:**
- Modify: `src/components/SonarCard.tsx`

**Exact fixes:**
- Replace `TITLE_STATUS_COLORS[result.titleStatus]` with a fallback-safe lookup so unknown title strings render with a neutral badge class instead of crashing.
- Add an `onError` image fallback that swaps broken photos to a local placeholder or a safe default asset, and prevent repeated error loops by disabling the handler after the first failure.
- Guard the mileage line so it renders a readable fallback for `null`, string, or non-numeric values instead of calling `toLocaleString()` directly.
- Remove the `line-clamp-2` restriction from the condition text and replace it with an explicit expand/collapse toggle so damage notes remain visible by default but can still be condensed when the card is tall.
- Replace the small gray as-is sentence with a prominent warning banner that uses stronger color contrast, clearer wording, and a layout that reads as a caution, not a footnote.

**Dependency note:** This is independent of the tab state refactor, but it should follow Task 1 so the mileage and formatter changes are already available.

---

### Task 3: Refactor `SonarTab` state and interaction handling

**Files:**
- Modify: `src/components/SonarTab.tsx`

**Exact fixes:**
- Replace the `Map<SonarSource, SourceStatus>` React state with a plain `Record<SonarSource, SourceStatus>` so state updates are serializable, predictable, and easier to reason about.
- Rework the budget inputs so the user edits string draft values, then parse and normalize them on blur instead of coercing on every keystroke and fighting the cursor.
- Remove the arbitrary hard ceiling from the budget UI by using a named Sonar budget limit constant or a dynamically justified UI maximum, and keep that UI bound separate from the search form’s parsed values.
- Add search feedback for the Share button:
  - Show a toast on successful copy.
  - Show an error toast when clipboard access fails.
  - Swap the Share label/icon to a copied checkmark state briefly after success.
- Add skeleton loaders for the result grid while search batches are still streaming so the page does not show a blank grid during loading.
- Keep the progressive source-status row intact, but make it read from the new `Record` state and preserve the current scanning/done indicators.

**Dependency note:** This task depends on Task 1 only for the shared formatter import. It can be implemented after Task 2, but the state refactor should be finished before the loading and share-UX polish so the component remains easy to test.

---

### Task 4: Move Sonar animation CSS out of the component

**Files:**
- Modify: `src/components/SonarTab.tsx`
- Modify: `src/index.css`

**Exact fixes:**
- Delete the raw `<style>` tag from `SonarTab`.
- Move the Sonar-specific animation and slider helper classes into `src/index.css` under the existing `@layer components` or `@layer utilities` sections.
- Keep the class names stable so the JSX only changes where the styles live, not how the component references them.

**Dependency note:** This should be done after Task 3 because it is a pure extraction of styles already in use and should not alter the tab behavior.

---

### Task 5: Verify the Sonar flow end to end

**Files:**
- Verify: `src/components/SonarTab.tsx`
- Verify: `src/components/SonarCard.tsx`
- Verify: `src/services/sonarAPI.ts`
- Verify: `src/utils/formatters.ts`
- Verify: `src/index.css`

**Exact checks:**
- Confirm the Sonar tab still streams batches, updates source statuses, and renders cards progressively.
- Confirm the Share button copies formatted text and shows success/failure feedback.
- Confirm the budget controls accept typing without cursor jump and submit the parsed values.
- Confirm broken images, unknown titles, non-numeric mileage, and long condition text no longer crash or hide critical details.
- Confirm the Sonar animation classes still apply after moving CSS into the global stylesheet.

**Suggested validation commands:**
- `pnpm test -- --runInBand` or the repo’s equivalent targeted test command if the project uses a different runner.
- `pnpm lint` or the repo’s equivalent lint command.
- A focused manual browser check of the Sonar tab after the build passes.

