import React, { useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { roverAPI } from "@/services/roverAPI";

const MAKES = ["Ford", "Chevy", "Toyota", "Ram", "Honda", "BMW", "Mercedes", "Other"];

const TARGET_STATES = [
  "AL", "AR", "AZ", "CA", "CO", "FL", "GA", "ID", "IL", "IN",
  "KS", "KY", "LA", "MD", "MI", "MN", "MO", "MS", "NC", "NE",
  "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "SC", "TN",
  "TX", "UT", "VA", "WA", "WI",
];

const PRICE_BUCKETS = [
  { label: "Under $10k", value: "under_10k" },
  { label: "$10k–$20k", value: "10k_20k" },
  { label: "$20k–$40k", value: "20k_40k" },
  { label: "$40k+", value: "40k_plus" },
];

interface OnboardingFlowProps {
  onComplete: () => void;
}

export const OnboardingFlow: React.FC<OnboardingFlowProps> = ({ onComplete }) => {
  const [step, setStep] = useState(1);
  const [selectedMakes, setSelectedMakes] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedBucket, setSelectedBucket] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const toggleMake = (make: string) => {
    setSelectedMakes(prev =>
      prev.includes(make) ? prev.filter(m => m !== make) : [...prev, make]
    );
  };

  const toggleState = (state: string) => {
    setSelectedStates(prev =>
      prev.includes(state) ? prev.filter(s => s !== state) : [...prev, state]
    );
  };

  const handleComplete = async () => {
    setSubmitting(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const userId = session?.user?.id;
      if (!userId) {
        finish();
        return;
      }

      const events: Promise<void>[] = [];

      // Fire Rover save events for each preferred make
      selectedMakes.forEach(make => {
        events.push(
          roverAPI.trackEvent({
            userId,
            event: "save",
            item: {
              id: `onboarding-make-${make}`,
              make,
              model: "",
              year: new Date().getFullYear(),
              price: 0,
            },
          })
        );
      });

      // Fire Rover save events for each preferred state
      selectedStates.forEach(state => {
        events.push(
          roverAPI.trackEvent({
            userId,
            event: "save",
            item: {
              id: `onboarding-state-${state}`,
              make: "",
              model: "",
              year: new Date().getFullYear(),
              price: 0,
              state,
            },
          })
        );
      });

      // Fire a Rover save event encoding the price bucket
      if (selectedBucket) {
        const priceMap: Record<string, number> = {
          under_10k: 8000,
          "10k_20k": 15000,
          "20k_40k": 30000,
          "40k_plus": 50000,
        };
        events.push(
          roverAPI.trackEvent({
            userId,
            event: "save",
            item: {
              id: `onboarding-bucket-${selectedBucket}`,
              make: "",
              model: "",
              year: new Date().getFullYear(),
              price: priceMap[selectedBucket] ?? 0,
            },
          })
        );
      }

      // All events fire-and-forget — don't block on failures
      await Promise.allSettled(events);
    } catch {
      // Non-fatal; proceed regardless
    } finally {
      setSubmitting(false);
      finish();
    }
  };

  const finish = () => {
    localStorage.setItem("onboarding_completed", "true");
    onComplete();
  };

  const btnBase =
    "px-4 py-2 rounded-lg text-sm font-medium transition-colors";
  const btnPrimary =
    `${btnBase} bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50`;
  const btnSecondary =
    `${btnBase} border border-gray-600 text-gray-300 hover:border-gray-400 hover:text-white`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/90 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-lg">
        {/* Progress bar */}
        <div className="flex gap-1 p-5 pb-0">
          {[1, 2, 3].map(n => (
            <div
              key={n}
              className={`h-1 flex-1 rounded-full transition-colors ${
                n <= step ? "bg-emerald-500" : "bg-gray-700"
              }`}
            />
          ))}
        </div>

        <div className="p-6 space-y-6">
          {/* Step 1: Makes */}
          {step === 1 && (
            <>
              <div>
                <p className="text-xs text-emerald-400 font-medium uppercase tracking-wider mb-1">
                  Step 1 of 3
                </p>
                <h2 className="text-xl font-bold text-white">
                  What makes do you prefer?
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  We'll tune Rover to surface more of what you buy.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {MAKES.map(make => (
                  <button
                    key={make}
                    onClick={() => toggleMake(make)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      selectedMakes.includes(make)
                        ? "bg-emerald-600 border-emerald-500 text-white"
                        : "bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    {make}
                  </button>
                ))}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button className={btnSecondary} onClick={finish}>
                  Skip setup
                </button>
                <button className={btnPrimary} onClick={() => setStep(2)}>
                  Next →
                </button>
              </div>
            </>
          )}

          {/* Step 2: States */}
          {step === 2 && (
            <>
              <div>
                <p className="text-xs text-emerald-400 font-medium uppercase tracking-wider mb-1">
                  Step 2 of 3
                </p>
                <h2 className="text-xl font-bold text-white">
                  What states do you source from?
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Select all that apply — we'll prioritize those markets.
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto">
                {TARGET_STATES.map(state => (
                  <button
                    key={state}
                    onClick={() => toggleState(state)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      selectedStates.includes(state)
                        ? "bg-emerald-600 border-emerald-500 text-white"
                        : "bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    {state}
                  </button>
                ))}
              </div>
              <div className="flex justify-between gap-2 pt-2">
                <button className={btnSecondary} onClick={() => setStep(1)}>
                  ← Back
                </button>
                <button className={btnPrimary} onClick={() => setStep(3)}>
                  Next →
                </button>
              </div>
            </>
          )}

          {/* Step 3: Budget */}
          {step === 3 && (
            <>
              <div>
                <p className="text-xs text-emerald-400 font-medium uppercase tracking-wider mb-1">
                  Step 3 of 3
                </p>
                <h2 className="text-xl font-bold text-white">
                  What's your typical budget per vehicle?
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Helps Rover filter deals in your investment range.
                </p>
              </div>
              <div className="space-y-2">
                {PRICE_BUCKETS.map(bucket => (
                  <button
                    key={bucket.value}
                    onClick={() => setSelectedBucket(bucket.value)}
                    className={`w-full text-left px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
                      selectedBucket === bucket.value
                        ? "bg-emerald-600 border-emerald-500 text-white"
                        : "bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    {bucket.label}
                  </button>
                ))}
              </div>
              <div className="flex justify-between gap-2 pt-2">
                <button className={btnSecondary} onClick={() => setStep(2)}>
                  ← Back
                </button>
                <button
                  className={btnPrimary}
                  onClick={handleComplete}
                  disabled={submitting}
                >
                  {submitting ? "Saving…" : "Get Started →"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default OnboardingFlow;
