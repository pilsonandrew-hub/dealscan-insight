import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
let errorRate = new Rate('errors');
let responseTime = new Trend('response_time');

export let options = {
  stages: [
    { duration: '30s', target: 10 },  // Ramp up to 10 users
    { duration: '1m', target: 20 },   // Stay at 20 users
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<200'], // 95% of requests under 200ms
    'http_req_failed': ['rate<0.1'],    // Error rate under 10%
    'errors': ['rate<0.1'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:4173';

export default function() {
  // Test homepage
  let response = http.get(`${BASE_URL}/`);
  
  let checkResult = check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 200ms': (r) => r.timings.duration < 200,
    'has content': (r) => r.body.length > 0,
  });
  
  errorRate.add(!checkResult);
  responseTime.add(response.timings.duration);
  
  // Test API endpoints if available
  if (__ENV.API_BASE_URL) {
    let apiResponse = http.get(`${__ENV.API_BASE_URL}/health`);
    check(apiResponse, {
      'API status is 200': (r) => r.status === 200,
      'API response time < 100ms': (r) => r.timings.duration < 100,
    });
  }
  
  sleep(1);
}

export function handleSummary(data) {
  return {
    'reports/k6-summary.json': JSON.stringify(data, null, 2),
    'reports/k6-summary.txt': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const indent = options?.indent || '';
  const enableColors = options?.enableColors || false;
  
  let summary = '';
  summary += `${indent}✓ checks.........................: ${data.metrics.checks.values.passes}/${data.metrics.checks.values.fails + data.metrics.checks.values.passes}\n`;
  summary += `${indent}✓ data_received..................: ${(data.metrics.data_received.values.count / 1024).toFixed(2)} KB\n`;
  summary += `${indent}✓ data_sent......................: ${(data.metrics.data_sent.values.count / 1024).toFixed(2)} KB\n`;
  summary += `${indent}✓ http_req_duration..............: avg=${data.metrics.http_req_duration.values.avg.toFixed(2)}ms min=${data.metrics.http_req_duration.values.min.toFixed(2)}ms med=${data.metrics.http_req_duration.values.med.toFixed(2)}ms max=${data.metrics.http_req_duration.values.max.toFixed(2)}ms p(90)=${data.metrics.http_req_duration.values['p(90)'].toFixed(2)}ms p(95)=${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
  summary += `${indent}✓ http_req_failed................: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  summary += `${indent}✓ http_reqs......................: ${data.metrics.http_reqs.values.count}\n`;
  summary += `${indent}✓ iterations.....................: ${data.metrics.iterations.values.count}\n`;
  
  return summary;
}