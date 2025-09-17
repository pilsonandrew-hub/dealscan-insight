# Rover Smoke & E2E Test Guidance

> **🧪 Comprehensive testing strategy for the Rover premium module**
>
> This guide provides sample test scripts and documentation for smoke testing, end-to-end testing, and load testing of the Rover recommendation engine and premium features.

## 🎯 Testing Strategy Overview

### Test Pyramid for Rover

```
    ┌─────────────────────┐
    │   E2E Tests (10%)   │  ← User journeys, critical paths
    │   Playwright + k6   │
    ├─────────────────────┤
    │ Integration (20%)   │  ← API contracts, data flows  
    │ Vitest + Supertest  │
    ├─────────────────────┤
    │  Unit Tests (70%)   │  ← Component logic, utilities
    │   Vitest + RTL      │
    └─────────────────────┘
```

### Test Categories

1. **Smoke Tests**: Basic functionality verification after deployment
2. **Integration Tests**: API endpoints and service interactions
3. **E2E Tests**: Complete user workflows in browser environment
4. **Load Tests**: Performance under realistic traffic patterns
5. **Security Tests**: Authentication, authorization, and data protection

---

## 🔥 Smoke Tests

### API Smoke Test (Vitest + Supertest)

```typescript
// tests/smoke/rover-api.smoke.test.ts

import { describe, it, expect, beforeAll } from 'vitest';
import request from 'supertest';
import { createApp } from '../../src/app';
import { generateTestJWT } from '../utils/auth-helpers';

const app = createApp();
let authToken: string;
let premiumAuthToken: string;

beforeAll(async () => {
  authToken = await generateTestJWT({ userId: 'user-123', premium: false });
  premiumAuthToken = await generateTestJWT({ userId: 'premium-user-123', premium: true });
});

describe('Rover API Smoke Tests', () => {
  describe('Health Checks', () => {
    it('should respond to health check', async () => {
      const response = await request(app)
        .get('/api/rover/health')
        .expect(200);
      
      expect(response.body).toMatchObject({
        status: 'healthy',
        service: 'rover-recommendations',
        timestamp: expect.any(String),
        checks: {
          database: 'healthy',
          redis: 'healthy',
          mlPipeline: 'healthy'
        }
      });
    });

    it('should check ML model availability', async () => {
      const response = await request(app)
        .get('/api/rover/health/ml-model')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .expect(200);
      
      expect(response.body.modelStatus).toBe('ready');
      expect(response.body.lastTraining).toBeDefined();
    });
  });

  describe('Authentication & Authorization', () => {
    it('should reject requests without auth token', async () => {
      await request(app)
        .get('/api/rover/recommendations')
        .expect(401);
    });

    it('should reject non-premium users', async () => {
      await request(app)
        .get('/api/rover/recommendations')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(403)
        .expect((res) => {
          expect(res.body.error).toContain('premium subscription required');
        });
    });

    it('should allow premium users access', async () => {
      await request(app)
        .get('/api/rover/recommendations')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .expect(200);
    });
  });

  describe('Core Functionality', () => {
    it('should generate recommendations for premium user', async () => {
      const response = await request(app)
        .get('/api/rover/recommendations')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .query({
          make: 'Toyota',
          model: 'Camry',
          maxMileage: 50000,
          maxPrice: 25000
        })
        .expect(200);
      
      expect(response.body).toMatchObject({
        recommendations: expect.any(Array),
        metadata: {
          totalResults: expect.any(Number),
          mlConfidence: expect.any(Number),
          generatedAt: expect.any(String)
        }
      });

      // Verify recommendation structure
      if (response.body.recommendations.length > 0) {
        const recommendation = response.body.recommendations[0];
        expect(recommendation).toMatchObject({
          id: expect.any(String),
          score: expect.any(Number),
          confidence: expect.any(Number),
          arbitrageScore: expect.any(Number),
          roiPercentage: expect.any(Number),
          explanation: expect.any(String)
        });
      }
    });

    it('should track user interactions', async () => {
      const eventData = {
        eventType: 'recommendation_viewed',
        recommendationId: 'rec-123',
        dealId: 'deal-456',
        userResponse: 'positive'
      };

      await request(app)
        .post('/api/rover/events')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .send(eventData)
        .expect(201);
    });

    it('should update user preferences', async () => {
      const preferences = {
        preferredMakes: ['Toyota', 'Honda'],
        maxMileage: 50000,
        preferredPriceRange: [15000, 30000],
        riskTolerance: 'moderate'
      };

      await request(app)
        .put('/api/rover/preferences')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .send(preferences)
        .expect(200);
    });
  });

  describe('Performance Validation', () => {
    it('should respond within performance thresholds', async () => {
      const startTime = Date.now();
      
      await request(app)
        .get('/api/rover/recommendations')
        .set('Authorization', `Bearer ${premiumAuthToken}`)
        .expect(200);
      
      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(2000); // 2 second threshold
    });
  });
});
```

### UI Smoke Test (Vitest + Testing Library)

```typescript
// tests/smoke/rover-ui.smoke.test.tsx

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RoverDashboard } from '../../src/components/RoverDashboard';
import { RoverCard } from '../../src/components/RoverCard';
import { TestWrapper } from '../utils/test-wrapper';

// Mock the rover API service
vi.mock('../../src/services/roverAPI', () => ({
  roverAPI: {
    getRecommendations: vi.fn(() => Promise.resolve({
      recommendations: [
        {
          id: 'rec-1',
          dealId: 'deal-1',
          score: 0.85,
          confidence: 0.9,
          arbitrageScore: 75,
          roiPercentage: 18.5,
          explanation: 'High ROI with low risk',
          make: 'Toyota',
          model: 'Camry',
          year: 2020,
          mileage: 35000,
          price: 22000,
          estimatedValue: 26000
        }
      ],
      metadata: {
        totalResults: 1,
        mlConfidence: 0.9,
        generatedAt: new Date().toISOString()
      }
    })),
    trackEvent: vi.fn(() => Promise.resolve()),
    updatePreferences: vi.fn(() => Promise.resolve())
  }
}));

describe('Rover UI Smoke Tests', () => {
  describe('RoverDashboard Component', () => {
    it('should render dashboard with loading state', () => {
      render(
        <TestWrapper>
          <RoverDashboard />
        </TestWrapper>
      );
      
      expect(screen.getByText(/loading recommendations/i)).toBeInTheDocument();
    });

    it('should render recommendations when loaded', async () => {
      render(
        <TestWrapper>
          <RoverDashboard />
        </TestWrapper>
      );
      
      await waitFor(() => {
        expect(screen.getByText('Toyota Camry')).toBeInTheDocument();
        expect(screen.getByText('18.5% ROI')).toBeInTheDocument();
      });
    });

    it('should handle user interactions', async () => {
      const user = userEvent.setup();
      
      render(
        <TestWrapper>
          <RoverDashboard />
        </TestWrapper>
      );
      
      await waitFor(() => {
        expect(screen.getByText('Toyota Camry')).toBeInTheDocument();
      });
      
      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);
      
      // Verify interaction tracking
      const { roverAPI } = await import('../../src/services/roverAPI');
      expect(roverAPI.trackEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          eventType: 'save',
          dealId: 'deal-1'
        })
      );
    });
  });

  describe('RoverCard Component', () => {
    const mockItem = {
      id: 'rec-1',
      dealId: 'deal-1',
      score: 0.85,
      confidence: 0.9,
      arbitrageScore: 75,
      roiPercentage: 18.5,
      explanation: 'High ROI with low risk',
      make: 'Toyota',
      model: 'Camry',
      year: 2020,
      mileage: 35000,
      price: 22000,
      estimatedValue: 26000
    };

    it('should render recommendation card with all key information', () => {
      const mockOnInteraction = vi.fn();
      
      render(
        <TestWrapper>
          <RoverCard 
            item={mockItem} 
            onInteraction={mockOnInteraction}
            showExplanation={true}
          />
        </TestWrapper>
      );
      
      expect(screen.getByText('Toyota Camry')).toBeInTheDocument();
      expect(screen.getByText('2020')).toBeInTheDocument();
      expect(screen.getByText('35,000')).toBeInTheDocument();
      expect(screen.getByText('$22,000')).toBeInTheDocument();
      expect(screen.getByText('High ROI with low risk')).toBeInTheDocument();
    });

    it('should handle card interactions', async () => {
      const user = userEvent.setup();
      const mockOnInteraction = vi.fn();
      
      render(
        <TestWrapper>
          <RoverCard 
            item={mockItem} 
            onInteraction={mockOnInteraction}
          />
        </TestWrapper>
      );
      
      const bidButton = screen.getByRole('button', { name: /place bid/i });
      await user.click(bidButton);
      
      expect(mockOnInteraction).toHaveBeenCalledWith(mockItem, 'bid');
    });
  });
});
```

---

## 🔍 E2E Tests (Playwright)

### Rover User Journey E2E Test

```typescript
// tests/e2e/rover-user-journey.spec.ts

import { test, expect, Page } from '@playwright/test';

test.describe('Rover Premium User Journey', () => {
  let page: Page;

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage();
    
    // Set up premium user session
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'premium-user@example.com');
    await page.fill('[data-testid="password"]', 'SecurePassword123!');
    await page.click('[data-testid="login-button"]');
    
    // Wait for successful login
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
  });

  test('Premium user can access Rover dashboard', async () => {
    // Navigate to Rover dashboard
    await page.click('[data-testid="rover-nav-link"]');
    
    // Verify Rover dashboard loads
    await expect(page.locator('[data-testid="rover-dashboard"]')).toBeVisible();
    await expect(page.locator('h1')).toContainText('Rover Intelligence');
  });

  test('User can generate and interact with recommendations', async () => {
    await page.goto('/rover');
    
    // Set search preferences
    await page.selectOption('[data-testid="make-select"]', 'Toyota');
    await page.selectOption('[data-testid="model-select"]', 'Camry');
    await page.fill('[data-testid="max-mileage"]', '50000');
    await page.fill('[data-testid="max-price"]', '25000');
    
    // Generate recommendations
    await page.click('[data-testid="generate-recommendations"]');
    
    // Wait for recommendations to load
    await expect(page.locator('[data-testid="recommendation-card"]').first()).toBeVisible();
    
    // Verify recommendation content
    const firstCard = page.locator('[data-testid="recommendation-card"]').first();
    await expect(firstCard.locator('.make-model')).toContainText('Toyota');
    await expect(firstCard.locator('.roi-percentage')).toBeVisible();
    await expect(firstCard.locator('.confidence-score')).toBeVisible();
    
    // Test saving a recommendation
    await firstCard.locator('[data-testid="save-button"]').click();
    await expect(page.locator('.toast-success')).toContainText('Recommendation saved');
    
    // Test placing a bid
    await firstCard.locator('[data-testid="bid-button"]').click();
    await expect(page.locator('[data-testid="bid-modal"]')).toBeVisible();
    
    await page.fill('[data-testid="bid-amount"]', '23000');
    await page.click('[data-testid="confirm-bid"]');
    await expect(page.locator('.toast-success')).toContainText('Bid placed successfully');
  });

  test('User can update preferences and see personalized results', async () => {
    await page.goto('/rover/preferences');
    
    // Update user preferences
    await page.check('[data-testid="make-toyota"]');
    await page.check('[data-testid="make-honda"]');
    await page.selectOption('[data-testid="risk-tolerance"]', 'conservative');
    await page.fill('[data-testid="budget-min"]', '15000');
    await page.fill('[data-testid="budget-max"]', '30000');
    
    await page.click('[data-testid="save-preferences"]');
    await expect(page.locator('.toast-success')).toContainText('Preferences updated');
    
    // Verify preferences were applied
    await page.goto('/rover');
    await page.click('[data-testid="generate-recommendations"]');
    
    // Check that recommendations respect preferences
    const recommendations = page.locator('[data-testid="recommendation-card"]');
    const count = await recommendations.count();
    
    for (let i = 0; i < count; i++) {
      const card = recommendations.nth(i);
      const makeText = await card.locator('.make-model').textContent();
      expect(['Toyota', 'Honda'].some(make => makeText?.includes(make))).toBeTruthy();
    }
  });

  test('User receives real-time recommendation updates', async () => {
    await page.goto('/rover');
    
    // Wait for initial recommendations
    await expect(page.locator('[data-testid="recommendation-card"]').first()).toBeVisible();
    const initialCount = await page.locator('[data-testid="recommendation-card"]').count();
    
    // Simulate real-time update (this would be triggered by background jobs)
    await page.evaluate(() => {
      // Trigger WebSocket message or polling update
      window.dispatchEvent(new CustomEvent('rover-update', {
        detail: { type: 'new-recommendations', count: 3 }
      }));
    });
    
    // Verify notification appears
    await expect(page.locator('[data-testid="new-recommendations-badge"]')).toBeVisible();
    await expect(page.locator('[data-testid="new-recommendations-badge"]')).toContainText('3 new');
    
    // Click to refresh recommendations
    await page.click('[data-testid="refresh-recommendations"]');
    
    // Verify recommendations were updated
    await expect(page.locator('[data-testid="recommendation-card"]')).toHaveCount(initialCount + 3);
  });

  test('Non-premium user sees upgrade prompts', async () => {
    // Logout and login as non-premium user
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout"]');
    
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'basic-user@example.com');
    await page.fill('[data-testid="password"]', 'SecurePassword123!');
    await page.click('[data-testid="login-button"]');
    
    // Try to access Rover
    await page.goto('/rover');
    
    // Verify upgrade prompt appears
    await expect(page.locator('[data-testid="upgrade-prompt"]')).toBeVisible();
    await expect(page.locator('[data-testid="upgrade-prompt"]')).toContainText('Premium subscription required');
    
    // Verify upgrade button works
    await page.click('[data-testid="upgrade-button"]');
    await expect(page.url()).toContain('/pricing');
  });
});
```

---

## ⚡ Load Tests (k6)

### Rover API Load Test

```javascript
// tests/load/rover-api-load.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
export const errorRate = new Rate('errors');
export const recommendationLatency = new Trend('recommendation_latency');

export const options = {
  stages: [
    // Ramp up
    { duration: '30s', target: 10 },   // 10 users for 30s
    { duration: '1m', target: 50 },    // Ramp to 50 users over 1min
    { duration: '3m', target: 100 },   // Peak load: 100 users for 3min
    { duration: '1m', target: 50 },    // Scale down to 50 users
    { duration: '30s', target: 0 },    // Ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests must complete below 2s
    http_req_failed: ['rate<0.05'],    // Error rate must be below 5%
    recommendation_latency: ['p(95)<1500'], // Recommendation generation < 1.5s
    errors: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

// Simulated JWT tokens for premium users
const AUTH_TOKENS = [
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...[premium-user-1]',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...[premium-user-2]',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...[premium-user-3]',
  // Add more tokens for different users
];

const SEARCH_SCENARIOS = [
  { make: 'Toyota', model: 'Camry', maxMileage: 50000, maxPrice: 25000 },
  { make: 'Honda', model: 'Accord', maxMileage: 60000, maxPrice: 28000 },
  { make: 'Ford', model: 'F-150', maxMileage: 40000, maxPrice: 35000 },
  { make: 'BMW', model: '3 Series', maxMileage: 30000, maxPrice: 40000 },
  { make: 'Mercedes', model: 'C-Class', maxMileage: 25000, maxPrice: 45000 },
];

export default function () {
  // Select random user and search scenario
  const authToken = AUTH_TOKENS[Math.floor(Math.random() * AUTH_TOKENS.length)];
  const scenario = SEARCH_SCENARIOS[Math.floor(Math.random() * SEARCH_SCENARIOS.length)];
  
  const headers = {
    'Authorization': `Bearer ${authToken}`,
    'Content-Type': 'application/json',
  };

  // 1. Health Check (10% of requests)
  if (Math.random() < 0.1) {
    const healthResponse = http.get(`${BASE_URL}/api/rover/health`, { headers });
    check(healthResponse, {
      'health check status is 200': (r) => r.status === 200,
      'health check response time < 500ms': (r) => r.timings.duration < 500,
    });
    errorRate.add(healthResponse.status !== 200);
  }

  // 2. Get Recommendations (Main workflow - 70% of requests)
  if (Math.random() < 0.7) {
    const params = new URLSearchParams(scenario).toString();
    const startTime = Date.now();
    
    const recResponse = http.get(`${BASE_URL}/api/rover/recommendations?${params}`, { headers });
    
    const duration = Date.now() - startTime;
    recommendationLatency.add(duration);
    
    const isSuccess = check(recResponse, {
      'recommendation status is 200': (r) => r.status === 200,
      'recommendation has results': (r) => {
        try {
          const data = JSON.parse(r.body);
          return data.recommendations && Array.isArray(data.recommendations);
        } catch {
          return false;
        }
      },
      'recommendation response time < 2s': (r) => r.timings.duration < 2000,
    });
    
    errorRate.add(!isSuccess);
  }

  // 3. Track User Interaction (15% of requests)
  if (Math.random() < 0.15) {
    const eventData = {
      eventType: ['view', 'click', 'save', 'bid'][Math.floor(Math.random() * 4)],
      dealId: `deal-${Math.floor(Math.random() * 10000)}`,
      recommendationId: `rec-${Math.floor(Math.random() * 10000)}`,
      userResponse: Math.random() > 0.3 ? 'positive' : 'negative',
    };

    const eventResponse = http.post(
      `${BASE_URL}/api/rover/events`,
      JSON.stringify(eventData),
      { headers }
    );

    check(eventResponse, {
      'event tracking status is 201': (r) => r.status === 201,
      'event tracking response time < 500ms': (r) => r.timings.duration < 500,
    });
    
    errorRate.add(eventResponse.status !== 201);
  }

  // 4. Update Preferences (5% of requests)
  if (Math.random() < 0.05) {
    const preferences = {
      preferredMakes: ['Toyota', 'Honda', 'Ford'].slice(0, Math.floor(Math.random() * 3) + 1),
      maxMileage: [30000, 50000, 75000][Math.floor(Math.random() * 3)],
      preferredPriceRange: [[15000, 25000], [20000, 35000], [30000, 50000]][Math.floor(Math.random() * 3)],
      riskTolerance: ['conservative', 'moderate', 'aggressive'][Math.floor(Math.random() * 3)],
    };

    const prefResponse = http.put(
      `${BASE_URL}/api/rover/preferences`,
      JSON.stringify(preferences),
      { headers }
    );

    check(prefResponse, {
      'preference update status is 200': (r) => r.status === 200,
      'preference update response time < 1s': (r) => r.timings.duration < 1000,
    });
    
    errorRate.add(prefResponse.status !== 200);
  }

  // Random sleep between 1-3 seconds to simulate real user behavior
  sleep(Math.random() * 2 + 1);
}

export function handleSummary(data) {
  return {
    'load-test-results.json': JSON.stringify(data, null, 2),
    'load-test-summary.txt': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options = {}) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;
  
  return `
${indent}Rover Load Test Summary
${indent}========================
${indent}Total Requests: ${data.metrics.http_reqs.values.count}
${indent}Failed Requests: ${data.metrics.http_req_failed.values.rate * 100}%
${indent}Average Duration: ${data.metrics.http_req_duration.values.avg}ms
${indent}P95 Duration: ${data.metrics.http_req_duration.values['p(95)']}ms
${indent}Recommendation P95: ${data.metrics.recommendation_latency?.values['p(95)'] || 'N/A'}ms
${indent}Error Rate: ${data.metrics.errors?.values.rate * 100 || 0}%
${indent}
${indent}Performance Thresholds: ${data.metrics.http_req_duration.thresholds['p(95)<2000'].ok ? '✅ PASSED' : '❌ FAILED'}
${indent}Error Rate Threshold: ${data.metrics.http_req_failed.thresholds['rate<0.05'].ok ? '✅ PASSED' : '❌ FAILED'}
  `;
}
```

### Frontend Performance Test

```javascript
// tests/load/rover-ui-load.js

import { chromium } from 'k6/experimental/browser';

export const options = {
  scenarios: {
    ui: {
      executor: 'constant-vus',
      vus: 5, // 5 concurrent browser sessions
      duration: '2m',
      options: {
        browser: {
          type: 'chromium',
        },
      },
    },
  },
  thresholds: {
    browser_web_vital_fcp: ['p(95)<3000'], // First Contentful Paint
    browser_web_vital_lcp: ['p(95)<4000'], // Largest Contentful Paint
    browser_web_vital_cls: ['p(95)<0.1'],  // Cumulative Layout Shift
  },
};

export default async function () {
  const browser = chromium.launch({ headless: true });
  const page = browser.newPage();

  try {
    // Login as premium user
    await page.goto('http://localhost:4173/login');
    await page.fill('[data-testid="email"]', 'premium-user@example.com');
    await page.fill('[data-testid="password"]', 'SecurePassword123!');
    await page.click('[data-testid="login-button"]');
    
    // Navigate to Rover dashboard
    await page.waitForSelector('[data-testid="user-menu"]');
    await page.click('[data-testid="rover-nav-link"]');
    
    // Measure page load performance
    await page.waitForSelector('[data-testid="rover-dashboard"]');
    
    // Interact with recommendations
    await page.selectOption('[data-testid="make-select"]', 'Toyota');
    await page.click('[data-testid="generate-recommendations"]');
    
    // Wait for recommendations to load
    await page.waitForSelector('[data-testid="recommendation-card"]', { timeout: 30000 });
    
    // Simulate user interactions
    const cards = page.locator('[data-testid="recommendation-card"]');
    const cardCount = await cards.count();
    
    if (cardCount > 0) {
      // Click on first recommendation
      await cards.nth(0).click();
      
      // Save recommendation
      await page.click('[data-testid="save-button"]');
      
      // Wait for success message
      await page.waitForSelector('.toast-success', { timeout: 5000 });
    }
    
  } finally {
    page.close();
    browser.close();
  }
}
```

---

## 🛠️ Test Setup & Utilities

### Test Configuration

```typescript
// tests/config/test-config.ts

export const testConfig = {
  apiBaseUrl: process.env.TEST_API_BASE_URL || 'http://localhost:8080',
  uiBaseUrl: process.env.TEST_UI_BASE_URL || 'http://localhost:4173',
  timeout: {
    short: 5000,    // 5 seconds
    medium: 15000,  // 15 seconds  
    long: 30000,    // 30 seconds
  },
  retries: {
    smoke: 2,
    e2e: 1,
    load: 0,
  },
  performance: {
    apiResponseTime: 2000,     // 2 seconds max
    uiLoadTime: 4000,          // 4 seconds max
    recommendationTime: 1500,  // 1.5 seconds max
  },
  auth: {
    premiumUser: {
      email: 'premium-test@example.com',
      password: 'TestPassword123!',
    },
    basicUser: {
      email: 'basic-test@example.com', 
      password: 'TestPassword123!',
    },
  },
};
```

### Test Utilities

```typescript
// tests/utils/test-helpers.ts

import jwt from 'jsonwebtoken';
import { testConfig } from '../config/test-config';

export async function generateTestJWT(payload: { userId: string; premium: boolean }) {
  const secret = process.env.JWT_SECRET || 'test-secret';
  return jwt.sign(
    {
      sub: payload.userId,
      premium: payload.premium,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour
    },
    secret
  );
}

export async function waitForRecommendations(page: any, timeout = 30000) {
  await page.waitForSelector('[data-testid="recommendation-card"]', { timeout });
  
  // Wait for loading states to complete
  await page.waitForFunction(
    () => !document.querySelector('[data-testid="recommendations-loading"]'),
    { timeout: 10000 }
  );
}

export function generateMockRecommendation(overrides = {}) {
  return {
    id: `rec-${Date.now()}`,
    dealId: `deal-${Date.now()}`,
    score: 0.8 + Math.random() * 0.2,
    confidence: 0.7 + Math.random() * 0.3,
    arbitrageScore: 60 + Math.random() * 40,
    roiPercentage: 10 + Math.random() * 20,
    make: 'Toyota',
    model: 'Camry',
    year: 2020 + Math.floor(Math.random() * 4),
    mileage: 20000 + Math.floor(Math.random() * 50000),
    price: 15000 + Math.floor(Math.random() * 20000),
    estimatedValue: 18000 + Math.floor(Math.random() * 25000),
    explanation: 'Excellent arbitrage opportunity with high confidence',
    ...overrides,
  };
}

export class TestDataFactory {
  static createRecommendations(count = 5) {
    return Array.from({ length: count }, () => generateMockRecommendation());
  }

  static createUserPreferences() {
    return {
      preferredMakes: ['Toyota', 'Honda'],
      maxMileage: 50000,
      preferredPriceRange: [15000, 30000],
      riskTolerance: 'moderate' as const,
    };
  }

  static createUserEvent(type = 'view') {
    return {
      eventType: type,
      dealId: `deal-${Date.now()}`,
      recommendationId: `rec-${Date.now()}`,
      userResponse: Math.random() > 0.5 ? 'positive' : 'negative',
      timestamp: new Date().toISOString(),
    };
  }
}
```

---

## 🏃‍♂️ Running the Tests

### Quick Start Commands

```bash
# Install test dependencies
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom
npm install --save-dev supertest @types/supertest
npm install --save-dev @playwright/test
npm install --save-dev k6

# Run smoke tests
npm run test:smoke

# Run integration tests  
npm run test:integration

# Run E2E tests
npm run test:e2e

# Run load tests
npm run test:load

# Run all tests
npm run test:all
```

### Package.json Scripts

```json
{
  "scripts": {
    "test:smoke": "vitest run tests/smoke/",
    "test:integration": "vitest run tests/integration/",
    "test:e2e": "playwright test tests/e2e/",
    "test:load": "k6 run tests/load/rover-api-load.js",
    "test:load:ui": "k6 run tests/load/rover-ui-load.js",
    "test:all": "npm run test:smoke && npm run test:integration && npm run test:e2e",
    "test:ci": "npm run test:smoke && npm run test:integration",
    "test:watch": "vitest watch tests/smoke/ tests/integration/"
  }
}
```

### CI/CD Integration

```yaml
# .github/workflows/rover-tests.yml
name: Rover Test Suite

on:
  push:
    paths:
      - 'src/components/Rover*'
      - 'src/services/roverAPI.ts'
      - 'tests/**'
  pull_request:
    paths:
      - 'src/components/Rover*'
      - 'src/services/roverAPI.ts'

jobs:
  smoke-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm ci
      - name: Run smoke tests
        run: npm run test:smoke

  e2e-tests:
    runs-on: ubuntu-latest
    needs: smoke-tests
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm ci
      - name: Install Playwright
        run: npx playwright install
      - name: Start application
        run: npm run dev &
      - name: Wait for server
        run: npx wait-on http://localhost:4173
      - name: Run E2E tests
        run: npm run test:e2e

  load-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Setup k6
        uses: grafana/setup-k6-action@v1
      - name: Run load tests
        run: k6 run tests/load/rover-api-load.js
```

---

## 📊 Test Reporting & Monitoring

### Test Results Dashboard

The test results are automatically published to a dashboard that tracks:

- **Test Coverage**: Unit, integration, and E2E coverage percentages
- **Performance Metrics**: API response times, UI load times, recommendation generation times
- **Error Rates**: Test failure rates over time
- **Load Test Results**: Throughput, latency percentiles, error rates under load

### Alerts & Notifications

Set up alerts for:
- Test failure rate > 5%
- Performance regression > 20%
- Load test failures
- Security test failures

---

**🎯 Testing Philosophy**: Comprehensive testing ensures Rover delivers exceptional user experience while maintaining enterprise-grade reliability and performance.

**Last Updated**: January 2025 | **Version**: 1.0 | **Owner**: Rover QA Team