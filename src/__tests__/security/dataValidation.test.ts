import { describe, it, expect } from 'vitest';
import { validateOrThrow } from '../../utils/validation/validator';
import { vehicleSchema, Vehicle } from '../../utils/validation/schemas';

describe('Data Validation Framework', () => {
  const validVehicle: Vehicle = {
    make: 'Honda',
    model: 'Civic',
    year: 2022,
    vin: '1HGFB2F53NL000000',
    price: 25000,
    condition: 'New'
  };

  it('should successfully validate a correct vehicle object', () => {
    expect(() => validateOrThrow<Vehicle>(validVehicle, vehicleSchema)).not.toThrow();
  });

  it('should remove additional properties not defined in the schema', () => {
    const vehicleWithExtra = { ...validVehicle, extraField: 'should be removed' };
    const validated = validateOrThrow<Vehicle>(vehicleWithExtra, vehicleSchema);
    expect(validated).not.toHaveProperty('extraField');
  });

  describe('Validation Failures', () => {
    it('should throw an error for an invalid VIN', () => {
      const invalidData = { ...validVehicle, vin: 'INVALIDVIN123' };
      expect(() => validateOrThrow(invalidData, vehicleSchema)).toThrow(/Validation failed:.*vin/);
    });

    it('should throw an error for a future year', () => {
      const invalidData = { ...validVehicle, year: new Date().getFullYear() + 2 };
      expect(() => validateOrThrow(invalidData, vehicleSchema)).toThrow(/Validation failed:.*year/);
    });

    it('should throw an error for a negative price', () => {
      const invalidData = { ...validVehicle, price: -100 };
      expect(() => validateOrThrow(invalidData, vehicleSchema)).toThrow(/Validation failed:.*price/);
    });

    it('should throw an error for a missing required field', () => {
      const { make, ...invalidData } = validVehicle;
      expect(() => validateOrThrow(invalidData, vehicleSchema)).toThrow(/Validation failed:.*must have required property 'make'/);
    });
  });
});