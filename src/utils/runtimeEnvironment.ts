export type RuntimeEnvironment = 'development' | 'staging' | 'production';

export const getEnvironment = (): RuntimeEnvironment => {
  return ((import.meta.env.VITE_APP_ENV || import.meta.env.MODE || 'development') as RuntimeEnvironment);
};

export const isDevelopment = (): boolean => getEnvironment() === 'development';
export const isProduction = (): boolean => getEnvironment() === 'production';
export const isStaging = (): boolean => getEnvironment() === 'staging';
export const isPerformanceMonitoringEnabled = (): boolean => getEnvironment() !== 'development';
