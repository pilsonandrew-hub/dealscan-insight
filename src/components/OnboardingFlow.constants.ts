export const MAKES = ["Ford", "Chevy", "Toyota", "Ram", "Honda", "BMW", "Mercedes", "Other"];

export const TARGET_STATES = [
  "AL", "AR", "AZ", "CA", "CO", "FL", "GA", "ID", "IL", "IN",
  "KS", "KY", "LA", "MD", "MI", "MN", "MO", "MS", "NC", "NE",
  "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "SC", "TN",
  "TX", "UT", "VA", "WA", "WI",
];

export const PRICE_BUCKETS = [
  { label: "Under $10k", value: "under_10k" },
  { label: "$10k–$20k", value: "10k_20k" },
  { label: "$20k–$40k", value: "20k_40k" },
  { label: "$40k+", value: "40k_plus" },
];

export const ONBOARDING_COMPLETED_KEY = "onboarding_completed";

export function markOnboardingCompleted(): void {
  localStorage.setItem(ONBOARDING_COMPLETED_KEY, "true");
}
