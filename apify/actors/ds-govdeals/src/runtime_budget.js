export function createRuntimeBudget({ totalMs, now = () => Date.now(), logger = null } = {}) {
    const parsedTotal = Number(totalMs);
    const safeTotalMs = Number.isFinite(parsedTotal) && parsedTotal > 0 ? parsedTotal : 330000;
    const startedAtMs = now();

    function elapsedMs() {
        return Math.max(0, now() - startedAtMs);
    }

    function remainingMs() {
        return Math.max(0, safeTotalMs - elapsedMs());
    }

    function hasTimeFor(requiredMs) {
        const parsedRequired = Number(requiredMs);
        const safeRequiredMs = Number.isFinite(parsedRequired) && parsedRequired > 0 ? parsedRequired : 0;
        return remainingMs() >= safeRequiredMs;
    }

    function shouldContinue(requiredMs, label = 'work') {
        if (hasTimeFor(requiredMs)) return true;
        const message = `[RUNTIME BUDGET] Stopping ${label}: remaining=${remainingMs()}ms required=${requiredMs}ms elapsed=${elapsedMs()}ms budget=${safeTotalMs}ms`;
        if (logger?.warning) logger.warning(message);
        else if (logger?.warn) logger.warn(message);
        else if (logger?.info) logger.info(message);
        return false;
    }

    return {
        startedAtMs,
        totalMs: safeTotalMs,
        elapsedMs,
        remainingMs,
        hasTimeFor,
        shouldContinue,
    };
}
