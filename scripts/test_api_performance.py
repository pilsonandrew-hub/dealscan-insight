#!/usr/bin/env python3
"""
API Performance Testing Script - Phase 1 CI Gate
Validates P95 latency < 200ms for /api/opportunities
"""

import asyncio
import aiohttp
import time
import json
import statistics
import os
from typing import List, Dict, Any
from pathlib import Path

API_BASE = os.getenv('API_BASE', 'http://localhost:4173')
P95_THRESHOLD = int(os.getenv('P95_THRESHOLD', '200'))  # ms
ITERATIONS = int(os.getenv('PERF_ITERATIONS', '100'))

async def measure_api_performance() -> Dict[str, Any]:
    """Measure API performance with concurrent requests"""
    print(f"🔥 Starting API performance test - P95 threshold: {P95_THRESHOLD}ms")
    
    async with aiohttp.ClientSession() as session:
        # Warmup phase
        print("Warming up API...")
        for i in range(10):
            try:
                async with session.get(f"{API_BASE}/api/opportunities?limit=50") as resp:
                    await resp.text()
            except Exception as e:
                print(f"Warmup request {i+1} failed: {e}")
        
        # Measurement phase
        print(f"📊 Running {ITERATIONS} performance measurements...")
        durations = []
        
        tasks = []
        for i in range(ITERATIONS):
            tasks.append(measure_single_request(session, i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        for result in results:
            if isinstance(result, dict) and 'duration' in result:
                durations.append(result['duration'])
        
        if not durations:
            raise Exception("No successful API requests recorded")
        
        # Calculate statistics
        durations.sort()
        stats = {
            'total_requests': len(durations),
            'min_duration': min(durations),
            'max_duration': max(durations), 
            'avg_duration': statistics.mean(durations),
            'p50_duration': statistics.median(durations),
            'p95_duration': durations[int(len(durations) * 0.95)],
            'p99_duration': durations[int(len(durations) * 0.99)],
            'threshold': P95_THRESHOLD,
            'success_rate': (len(durations) / ITERATIONS) * 100
        }
        
        # Save report
        report = {
            'test_name': 'API Performance Test',
            'timestamp': time.time(),
            'configuration': {
                'api_base': API_BASE,
                'iterations': ITERATIONS,
                'p95_threshold': P95_THRESHOLD
            },
            'statistics': stats
        }
        
        # Ensure reports directory exists
        Path('reports').mkdir(exist_ok=True)
        
        with open(f'reports/api-performance-{int(time.time())}.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        # Console output
        print(f"\n📈 API Performance Results:")
        print(f"Average Response Time: {stats['avg_duration']:.2f}ms")
        print(f"P95 Response Time: {stats['p95_duration']:.2f}ms")
        print(f"Success Rate: {stats['success_rate']:.2f}%")
        
        # Validation
        passed = stats['p95_duration'] <= P95_THRESHOLD and stats['success_rate'] >= 95
        
        if passed:
            print(f"✅ PASS: P95 latency {stats['p95_duration']:.2f}ms <= {P95_THRESHOLD}ms")
            return stats
        else:
            print(f"❌ FAIL: P95 latency {stats['p95_duration']:.2f}ms > {P95_THRESHOLD}ms")
            exit(1)

async def measure_single_request(session: aiohttp.ClientSession, iteration: int) -> Dict[str, Any]:
    """Measure a single API request"""
    start_time = time.time()
    
    try:
        endpoint = f"/api/opportunities?page={(iteration % 5) + 1}&limit=100"
        async with session.get(f"{API_BASE}{endpoint}") as response:
            await response.text()
            end_time = time.time()
            duration = (end_time - start_time) * 1000  # Convert to ms
            
            if response.status == 200:
                return {
                    'iteration': iteration + 1,
                    'duration': duration,
                    'status': response.status
                }
            else:
                print(f"Request {iteration + 1} failed with status: {response.status}")
                return {}
    except Exception as e:
        print(f"Request {iteration + 1} failed: {e}")
        return {}

if __name__ == "__main__":
    asyncio.run(measure_api_performance())