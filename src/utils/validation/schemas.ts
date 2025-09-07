/**
 * Enterprise Data Schemas
 * Comprehensive type definitions and validation schemas
 */

import { Schema } from 'ajv';

// Vehicle data interface
export interface Vehicle {
  make: string;
  model: string;
  year: number;
  vin: string;
  price: number;
  condition: string;
  mileage?: number;
  color?: string;
  transmission?: string;
  fuelType?: string;
}

// Vehicle validation schema
export const vehicleSchema: Schema = {
  type: 'object',
  properties: {
    make: {
      type: 'string',
      minLength: 1,
      maxLength: 50,
      pattern: '^[a-zA-Z0-9\\s\\-]+$'
    },
    model: {
      type: 'string',
      minLength: 1,
      maxLength: 100,
      pattern: '^[a-zA-Z0-9\\s\\-\\.]+$'
    },
    year: {
      type: 'number',
      minimum: 1900,
      maximum: new Date().getFullYear() + 1
    },
    vin: {
      type: 'string',
      pattern: '^[A-HJ-NPR-Z0-9]{17}$'
    },
    price: {
      type: 'number',
      minimum: 0,
      maximum: 10000000
    },
    condition: {
      type: 'string',
      enum: ['New', 'Used', 'Certified', 'Damaged', 'Parts']
    },
    mileage: {
      type: 'number',
      minimum: 0,
      maximum: 1000000,
      nullable: true
    },
    color: {
      type: 'string',
      maxLength: 30,
      nullable: true
    },
    transmission: {
      type: 'string',
      enum: ['Manual', 'Automatic', 'CVT', 'Semi-Automatic'],
      nullable: true
    },
    fuelType: {
      type: 'string',
      enum: ['Gasoline', 'Diesel', 'Electric', 'Hybrid', 'Hydrogen'],
      nullable: true
    }
  },
  required: ['make', 'model', 'year', 'vin', 'price', 'condition'],
  additionalProperties: false
};

// Auction data interface
export interface AuctionListing {
  id: string;
  title: string;
  description: string;
  startPrice: number;
  currentPrice?: number;
  startDate: string;
  endDate: string;
  location: string;
  category: string;
  images?: string[];
  seller: string;
  vehicle?: Vehicle;
}

// Auction listing schema
export const auctionListingSchema: Schema = {
  type: 'object',
  properties: {
    id: {
      type: 'string',
      minLength: 1,
      maxLength: 100
    },
    title: {
      type: 'string',
      minLength: 1,
      maxLength: 200
    },
    description: {
      type: 'string',
      maxLength: 5000
    },
    startPrice: {
      type: 'number',
      minimum: 0
    },
    currentPrice: {
      type: 'number',
      minimum: 0,
      nullable: true
    },
    startDate: {
      type: 'string',
      format: 'date-time'
    },
    endDate: {
      type: 'string',
      format: 'date-time'
    },
    location: {
      type: 'string',
      minLength: 1,
      maxLength: 200
    },
    category: {
      type: 'string',
      enum: ['Vehicles', 'Heavy Equipment', 'Electronics', 'Furniture', 'Other']
    },
    images: {
      type: 'array',
      items: {
        type: 'string',
        format: 'uri'
      },
      nullable: true,
      maxItems: 20
    },
    seller: {
      type: 'string',
      minLength: 1,
      maxLength: 100
    },
    vehicle: {
      type: 'object',
      properties: vehicleSchema.properties,
      required: vehicleSchema.required,
      additionalProperties: false,
      nullable: true
    }
  },
  required: ['id', 'title', 'description', 'startPrice', 'startDate', 'endDate', 'location', 'category', 'seller'],
  additionalProperties: false
};