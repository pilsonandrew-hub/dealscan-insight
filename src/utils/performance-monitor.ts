/**
 * Minimal performance timing utility.
 * Current live surface is limited to upload timing around startTimer() and monitorAPI().
 */

class PerformanceMonitor {
  startTimer(operationName = 'operation'): { end: (success?: boolean) => number } {
    const startTime = performance.now();

    return {
      end: (_success = true) => performance.now() - startTime,
    };
  }

  monitorAPI(operationName: string, method: string): { end: (success?: boolean) => number } {
    return this.startTimer(`${operationName}_${method}`);
  }
}

export const performanceMonitor = new PerformanceMonitor();
