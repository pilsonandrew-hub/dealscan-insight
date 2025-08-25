/**
 * Rust State Classification and Geographic Adjustments
 * Based on the investor report requirements for vehicle arbitrage
 */

export interface StateClassification {
  state: string;
  name: string;
  category: 'non-rust' | 'rust' | 'moderate';
  devaluation_factor: number;
  distance_to_ca: number;
  market_demand: 'high' | 'medium' | 'low';
  notes: string;
}

export interface GeographicAdjustment {
  original_value: number;
  rust_penalty: number;
  distance_penalty: number;
  market_adjustment: number;
  adjusted_value: number;
  confidence_reduction: number;
}

export class StateClassificationService {
  private static readonly STATE_DATA: Record<string, StateClassification> = {
    // NON-RUST STATES (Whitelisted) - Dry climates with minimal salt usage
    'CA': { state: 'CA', name: 'California', category: 'non-rust', devaluation_factor: 1.0, distance_to_ca: 0, market_demand: 'high', notes: 'Prime market - no rust penalty' },
    'AZ': { state: 'AZ', name: 'Arizona', category: 'non-rust', devaluation_factor: 1.0, distance_to_ca: 475, market_demand: 'high', notes: 'Desert climate - excellent condition' },
    'NV': { state: 'NV', name: 'Nevada', category: 'non-rust', devaluation_factor: 1.0, distance_to_ca: 300, market_demand: 'high', notes: 'Dry climate - minimal corrosion' },
    'OR': { state: 'OR', name: 'Oregon', category: 'non-rust', devaluation_factor: 0.98, distance_to_ca: 600, market_demand: 'medium', notes: 'Mild winters - limited salt use' },
    'WA': { state: 'WA', name: 'Washington', category: 'non-rust', devaluation_factor: 0.97, distance_to_ca: 900, market_demand: 'medium', notes: 'Coastal but minimal road salt' },
    'TX': { state: 'TX', name: 'Texas', category: 'non-rust', devaluation_factor: 0.98, distance_to_ca: 1400, market_demand: 'high', notes: 'Large market - minimal winter salt' },
    'FL': { state: 'FL', name: 'Florida', category: 'non-rust', devaluation_factor: 0.95, distance_to_ca: 2000, market_demand: 'high', notes: 'Salt air but no road salt' },
    'CO': { state: 'CO', name: 'Colorado', category: 'moderate', devaluation_factor: 0.92, distance_to_ca: 1200, market_demand: 'medium', notes: 'Mountain climate - some salt use' },
    'NM': { state: 'NM', name: 'New Mexico', category: 'non-rust', devaluation_factor: 0.98, distance_to_ca: 900, market_demand: 'medium', notes: 'Dry climate - minimal salt' },
    'UT': { state: 'UT', name: 'Utah', category: 'moderate', devaluation_factor: 0.93, distance_to_ca: 750, market_demand: 'medium', notes: 'Some winter salt usage' },
    'ID': { state: 'ID', name: 'Idaho', category: 'moderate', devaluation_factor: 0.92, distance_to_ca: 800, market_demand: 'medium', notes: 'Moderate salt usage in winter' },
    'MT': { state: 'MT', name: 'Montana', category: 'moderate', devaluation_factor: 0.90, distance_to_ca: 1000, market_demand: 'low', notes: 'Cold winters - moderate salt' },
    'WY': { state: 'WY', name: 'Wyoming', category: 'moderate', devaluation_factor: 0.90, distance_to_ca: 1000, market_demand: 'low', notes: 'Harsh winters - some salt' },

    // RUST STATES (Penalized) - Heavy winter salt usage
    'AL': { state: 'AL', name: 'Alabama', category: 'rust', devaluation_factor: 0.80, distance_to_ca: 1800, market_demand: 'medium', notes: 'Heavy salt use - rust common' },
    'AR': { state: 'AR', name: 'Arkansas', category: 'rust', devaluation_factor: 0.82, distance_to_ca: 1600, market_demand: 'medium', notes: 'Winter salt - rust issues' },
    'KY': { state: 'KY', name: 'Kentucky', category: 'rust', devaluation_factor: 0.78, distance_to_ca: 1700, market_demand: 'medium', notes: 'Heavy salt - significant rust' },
    'LA': { state: 'LA', name: 'Louisiana', category: 'rust', devaluation_factor: 0.85, distance_to_ca: 1500, market_demand: 'medium', notes: 'Humidity + salt air' },
    'MS': { state: 'MS', name: 'Mississippi', category: 'rust', devaluation_factor: 0.80, distance_to_ca: 1700, market_demand: 'low', notes: 'High humidity - rust prone' },
    'NC': { state: 'NC', name: 'North Carolina', category: 'rust', devaluation_factor: 0.83, distance_to_ca: 2000, market_demand: 'medium', notes: 'Mountain salt + coastal air' },
    'OK': { state: 'OK', name: 'Oklahoma', category: 'rust', devaluation_factor: 0.85, distance_to_ca: 1400, market_demand: 'medium', notes: 'Ice storms - salt usage' },
    'SC': { state: 'SC', name: 'South Carolina', category: 'rust', devaluation_factor: 0.82, distance_to_ca: 1900, market_demand: 'medium', notes: 'Coastal salt air' },
    'TN': { state: 'TN', name: 'Tennessee', category: 'rust', devaluation_factor: 0.80, distance_to_ca: 1800, market_demand: 'medium', notes: 'Winter salt - rust problems' },
    'VA': { state: 'VA', name: 'Virginia', category: 'rust', devaluation_factor: 0.82, distance_to_ca: 2100, market_demand: 'medium', notes: 'Heavy winter salt use' },
    'GA': { state: 'GA', name: 'Georgia', category: 'rust', devaluation_factor: 0.83, distance_to_ca: 1900, market_demand: 'medium', notes: 'Humidity + occasional salt' },
    
    // HEAVY RUST STATES (Severe penalties)
    'NY': { state: 'NY', name: 'New York', category: 'rust', devaluation_factor: 0.70, distance_to_ca: 2400, market_demand: 'high', notes: 'Extreme salt use - severe rust' },
    'MI': { state: 'MI', name: 'Michigan', category: 'rust', devaluation_factor: 0.68, distance_to_ca: 2000, market_demand: 'medium', notes: 'Rust belt - extreme corrosion' },
    'OH': { state: 'OH', name: 'Ohio', category: 'rust', devaluation_factor: 0.72, distance_to_ca: 1900, market_demand: 'medium', notes: 'Heavy salt - rust belt' },
    'PA': { state: 'PA', name: 'Pennsylvania', category: 'rust', devaluation_factor: 0.70, distance_to_ca: 2200, market_demand: 'medium', notes: 'Severe salt use - heavy rust' },
    'IL': { state: 'IL', name: 'Illinois', category: 'rust', devaluation_factor: 0.73, distance_to_ca: 1800, market_demand: 'medium', notes: 'Midwest salt - significant rust' },
    'IN': { state: 'IN', name: 'Indiana', category: 'rust', devaluation_factor: 0.72, distance_to_ca: 1800, market_demand: 'medium', notes: 'Heavy winter salt use' },
    'WI': { state: 'WI', name: 'Wisconsin', category: 'rust', devaluation_factor: 0.70, distance_to_ca: 1700, market_demand: 'medium', notes: 'Severe winters - heavy salt' },
    'MN': { state: 'MN', name: 'Minnesota', category: 'rust', devaluation_factor: 0.68, distance_to_ca: 1600, market_demand: 'medium', notes: 'Extreme cold - heavy salt' },
    'IA': { state: 'IA', name: 'Iowa', category: 'rust', devaluation_factor: 0.75, distance_to_ca: 1500, market_demand: 'low', notes: 'Winter salt - moderate rust' },
    'MO': { state: 'MO', name: 'Missouri', category: 'rust', devaluation_factor: 0.76, distance_to_ca: 1600, market_demand: 'medium', notes: 'Ice storms - salt use' },
    'NE': { state: 'NE', name: 'Nebraska', category: 'rust', devaluation_factor: 0.78, distance_to_ca: 1300, market_demand: 'low', notes: 'Winter conditions - some rust' },
    'KS': { state: 'KS', name: 'Kansas', category: 'rust', devaluation_factor: 0.80, distance_to_ca: 1200, market_demand: 'low', notes: 'Moderate salt use' },
    'ND': { state: 'ND', name: 'North Dakota', category: 'rust', devaluation_factor: 0.70, distance_to_ca: 1400, market_demand: 'low', notes: 'Harsh winters - heavy salt' },
    'SD': { state: 'SD', name: 'South Dakota', category: 'rust', devaluation_factor: 0.72, distance_to_ca: 1300, market_demand: 'low', notes: 'Cold climate - salt use' },

    // NORTHEAST RUST BELT (Highest penalties)
    'ME': { state: 'ME', name: 'Maine', category: 'rust', devaluation_factor: 0.65, distance_to_ca: 2600, market_demand: 'low', notes: 'Coastal salt + road salt' },
    'NH': { state: 'NH', name: 'New Hampshire', category: 'rust', devaluation_factor: 0.68, distance_to_ca: 2500, market_demand: 'low', notes: 'Mountain winters - heavy salt' },
    'VT': { state: 'VT', name: 'Vermont', category: 'rust', devaluation_factor: 0.67, distance_to_ca: 2500, market_demand: 'low', notes: 'Severe winters - extreme salt' },
    'MA': { state: 'MA', name: 'Massachusetts', category: 'rust', devaluation_factor: 0.68, distance_to_ca: 2500, market_demand: 'medium', notes: 'Coastal + road salt combo' },
    'CT': { state: 'CT', name: 'Connecticut', category: 'rust', devaluation_factor: 0.70, distance_to_ca: 2450, market_demand: 'medium', notes: 'Heavy salt use - rust issues' },
    'RI': { state: 'RI', name: 'Rhode Island', category: 'rust', devaluation_factor: 0.69, distance_to_ca: 2500, market_demand: 'low', notes: 'Coastal environment' },
    'NJ': { state: 'NJ', name: 'New Jersey', category: 'rust', devaluation_factor: 0.72, distance_to_ca: 2400, market_demand: 'medium', notes: 'Salt air + road salt' },
    'MD': { state: 'MD', name: 'Maryland', category: 'rust', devaluation_factor: 0.75, distance_to_ca: 2200, market_demand: 'medium', notes: 'Coastal areas - some rust' },
    'DE': { state: 'DE', name: 'Delaware', category: 'rust', devaluation_factor: 0.74, distance_to_ca: 2300, market_demand: 'low', notes: 'Coastal state - salt exposure' },
    'DC': { state: 'DC', name: 'Washington DC', category: 'rust', devaluation_factor: 0.75, distance_to_ca: 2200, market_demand: 'medium', notes: 'Winter salt use' },
    'WV': { state: 'WV', name: 'West Virginia', category: 'rust', devaluation_factor: 0.75, distance_to_ca: 2000, market_demand: 'low', notes: 'Mountain winters - salt use' },

    // SPECIAL CASES
    'AK': { state: 'AK', name: 'Alaska', category: 'rust', devaluation_factor: 0.60, distance_to_ca: 3000, market_demand: 'low', notes: 'Extreme conditions - heavy salt/corrosion' },
    'HI': { state: 'HI', name: 'Hawaii', category: 'moderate', devaluation_factor: 0.88, distance_to_ca: 2500, market_demand: 'low', notes: 'Salt air but no road salt' }
  };

  static classifyState(state: string): StateClassification {
    const normalized = state.toUpperCase();
    return this.STATE_DATA[normalized] || {
      state: normalized,
      name: 'Unknown',
      category: 'moderate',
      devaluation_factor: 0.85,
      distance_to_ca: 1500,
      market_demand: 'medium',
      notes: 'Unknown state - default moderate penalty'
    };
  }

  static calculateGeographicAdjustment(
    baseValue: number,
    state: string,
    age: number = 5,
    mileage: number = 100000
  ): GeographicAdjustment {
    const classification = this.classifyState(state);
    
    // Base rust penalty calculation
    let rustPenalty = 0;
    if (classification.category === 'rust') {
      // Age and mileage amplify rust effects
      const ageMultiplier = Math.min(2.0, 1 + (age - 5) * 0.1); // Older cars rust more
      const mileageMultiplier = Math.min(1.5, 1 + (mileage - 100000) / 500000); // Higher mileage = more exposure
      
      rustPenalty = baseValue * (1 - classification.devaluation_factor) * ageMultiplier * mileageMultiplier;
    } else if (classification.category === 'moderate') {
      rustPenalty = baseValue * (1 - classification.devaluation_factor) * 0.5; // Reduced penalty
    }

    // Distance penalty (transportation costs reduce effective value)
    const distancePenalty = classification.distance_to_ca * 1.4; // $1.40 per mile transportation

    // Market demand adjustment
    const demandMultiplier = classification.market_demand === 'high' ? 1.05 : 
                           classification.market_demand === 'low' ? 0.95 : 1.0;
    const marketAdjustment = baseValue * (demandMultiplier - 1);

    // Confidence reduction for rust states
    const confidenceReduction = classification.category === 'rust' ? 0.15 : 
                               classification.category === 'moderate' ? 0.05 : 0;

    const adjustedValue = Math.max(
      baseValue * 0.4, // Never go below 40% of original value
      baseValue - rustPenalty - distancePenalty + marketAdjustment
    );

    return {
      original_value: baseValue,
      rust_penalty: rustPenalty,
      distance_penalty: distancePenalty,
      market_adjustment: marketAdjustment,
      adjusted_value: adjustedValue,
      confidence_reduction: confidenceReduction
    };
  }

  static getNonRustStates(): string[] {
    return Object.entries(this.STATE_DATA)
      .filter(([_, data]) => data.category === 'non-rust')
      .map(([state, _]) => state);
  }

  static getRustStates(): string[] {
    return Object.entries(this.STATE_DATA)
      .filter(([_, data]) => data.category === 'rust')
      .map(([state, _]) => state);
  }

  static getStatesByCategory(category: 'non-rust' | 'rust' | 'moderate'): StateClassification[] {
    return Object.values(this.STATE_DATA).filter(state => state.category === category);
  }

  static shouldFilterOut(state: string, filterRustStates: boolean = false): boolean {
    if (!filterRustStates) return false;
    
    const classification = this.classifyState(state);
    // Filter out severe rust states (devaluation factor < 0.75)
    return classification.category === 'rust' && classification.devaluation_factor < 0.75;
  }

  static generateStateReport(): {
    nonRustStates: number;
    rustStates: number;
    moderateStates: number;
    averageDevaluation: Record<string, number>;
  } {
    const states = Object.values(this.STATE_DATA);
    const nonRust = states.filter(s => s.category === 'non-rust');
    const rust = states.filter(s => s.category === 'rust');
    const moderate = states.filter(s => s.category === 'moderate');

    return {
      nonRustStates: nonRust.length,
      rustStates: rust.length,
      moderateStates: moderate.length,
      averageDevaluation: {
        'non-rust': nonRust.reduce((sum, s) => sum + s.devaluation_factor, 0) / nonRust.length,
        'rust': rust.reduce((sum, s) => sum + s.devaluation_factor, 0) / rust.length,
        'moderate': moderate.reduce((sum, s) => sum + s.devaluation_factor, 0) / moderate.length
      }
    };
  }
}

export default StateClassificationService;