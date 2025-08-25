#!/usr/bin/env python3
"""
Cache Performance Testing Script - Phase 1 CI Gate
Validates cache hit rate >= 70% (Phase 1-2) or >= 85% (Phase 3-4)
"""

import asyncio
import aiohttp
import time
import json
import os
from pathlib import Path
from typing import List, Dict, Any

API_BASE = os.getenv('API_BASE', 'http://localhost:4173')
CACHE_HIT_THRESHOLD = float(os.getenv('CACHE_HIT_THRESHOLD', '0.70'))
WARMUP_REQUESTS = int(os.getenv('WARMUP_REQUESTS', '20'))
TEST_REQUESTS = int(os.getenv('TEST_REQUESTS', '100'))

async def measure_cache_performance() -> Dict[str, Any]:
    """Measure cache performance with hit rate analysis"""
    print(f"🚀 Starting cache performance test - hit rate threshold: {CACHE_HIT_THRESHOLD*100}%")
    
    test_endpoints = [
        '/api/opportunities?page=1&limit=50',
        '/api/opportunities?page=2&limit=50',
        '/api/opportunities?page=1&limit=100',
        '/api/health'
    ]
    
    measurements = []
    
    async with aiohttp.ClientSession() as session:
        # Phase 1: Warmup - populate cache
        print(f"🔥 Cache warmup phase: {WARMUP_REQUESTS} requests...")
        for i in range(WARMUP_REQUESTS):
            endpoint = test_endpoints[i % len(test_endpoints)]
            start_time = time.time()
            
            try:
                async with session.get(f"{API_BASE}{endpoint}") as response:
                    await response.text()
                    duration = (time.time() - start_time) * 1000
                    print(f"Warmup {i+1}/{WARMUP_REQUESTS}: {endpoint} ({duration:.1f}ms)")
            except Exception as e:
                print(f"Warmup request {i+1} failed: {e}")
            
            await asyncio.sleep(0.1)  # Small delay
        
        # Small pause between warmup and testing
        await asyncio.sleep(2)
        
        # Phase 2: Performance measurement
        print(f"📊 Cache performance measurement: {TEST_REQUESTS} requests...")
        
        for i in range(TEST_REQUESTS):
            endpoint = test_endpoints[i % len(test_endpoints)]
            start_time = time.time()
            
            try:
                headers = {'Cache-Control': 'no-cache'} if i % 10 == 0 else {}
                async with session.get(f"{API_BASE}{endpoint}", headers=headers) as response:
                    await response.text()
                    duration = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        cache_status = response.headers.get('x-cache-status', 'unknown')
                        etag = response.headers.get('etag')
                        
                        # Infer cache hits from response time
                        likely_cache_hit = duration < 50  # < 50ms likely cached
                        if likely_cache_hit and cache_status == 'unknown':
                            cache_status = 'hit_inferred'
                        
                        measurements.append({
                            'iteration': i + 1,
                            'endpoint': endpoint,
                            'duration': duration,
                            'cache_status': cache_status,
                            'has_etag': bool(etag),
                            'status': response.status
                        })
            except Exception as e:
                print(f"Test request {i+1} failed: {e}")
            
            # Progress indicator
            if (i + 1) % 25 == 0:
                progress = int(((i + 1) / TEST_REQUESTS) * 100)
                print(f"Progress: {i+1}/{TEST_REQUESTS} ({progress}%)")
            
            await asyncio.sleep(0.05)  # Small delay
        
        if not measurements:
            raise Exception("No successful cache test requests recorded")
        
        # Calculate cache statistics
        total_requests = len(measurements)
        explicit_hits = len([m for m in measurements if m['cache_status'] == 'hit'])
        inferred_hits = len([m for m in measurements if m['cache_status'] == 'hit_inferred'])
        total_hits = explicit_hits + inferred_hits
        cache_hit_rate = total_hits / total_requests
        
        # Performance analysis
        hit_durations = [m['duration'] for m in measurements 
                        if m['cache_status'] in ['hit', 'hit_inferred']]
        miss_durations = [m['duration'] for m in measurements 
                         if m['cache_status'] == 'miss' or 
                         (m['cache_status'] == 'unknown' and m['duration'] >= 50)]
        
        stats = {
            'total_requests': total_requests,
            'cache_hits': total_hits,
            'cache_misses': total_requests - total_hits,
            'cache_hit_rate': cache_hit_rate,
            'hit_rate_percentage': cache_hit_rate * 100,
            'threshold_percentage': CACHE_HIT_THRESHOLD * 100,
            'avg_hit_duration': sum(hit_durations) / len(hit_durations) if hit_durations else 0,
            'avg_miss_duration': sum(miss_durations) / len(miss_durations) if miss_durations else 0,
            'performance_improvement': 0
        }
        
        if stats['avg_miss_duration'] > 0 and stats['avg_hit_duration'] > 0:
            stats['performance_improvement'] = ((stats['avg_miss_duration'] - stats['avg_hit_duration']) / 
                                              stats['avg_miss_duration']) * 100
        
        # Save report
        report = {
            'test_name': 'Cache Performance Test',
            'timestamp': time.time(),
            'configuration': {
                'api_base': API_BASE,
                'cache_hit_threshold': CACHE_HIT_THRESHOLD,
                'warmup_requests': WARMUP_REQUESTS,
                'test_requests': TEST_REQUESTS
            },
            'statistics': stats,
            'endpoint_breakdown': [
                {
                    'endpoint': endpoint,
                    'requests': len([m for m in measurements if m['endpoint'] == endpoint]),
                    'hits': len([m for m in measurements if m['endpoint'] == endpoint and 
                               m['cache_status'] in ['hit', 'hit_inferred']]),
                    'hit_rate': len([m for m in measurements if m['endpoint'] == endpoint and 
                                   m['cache_status'] in ['hit', 'hit_inferred']]) / 
                               len([m for m in measurements if m['endpoint'] == endpoint])
                } for endpoint in test_endpoints
            ],
            'raw_measurements': measurements
        }
        
        # Ensure reports directory exists
        Path('reports').mkdir(exist_ok=True)
        
        with open(f'reports/cache-performance-{int(time.time())}.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        # Console output
        print(f"\n🚀 Cache Performance Results:")
        print(f"Cache Hit Rate: {stats['hit_rate_percentage']:.1f}%")
        print(f"Cache Hits: {stats['cache_hits']}/{stats['total_requests']}")
        print(f"Average Hit Duration: {stats['avg_hit_duration']:.1f}ms")
        print(f"Average Miss Duration: {stats['avg_miss_duration']:.1f}ms")
        print(f"Performance Improvement: {stats['performance_improvement']:.1f}%")
        
        # Validation
        passed = cache_hit_rate >= CACHE_HIT_THRESHOLD
        
        if passed:
            print(f"✅ PASS: Cache hit rate {stats['hit_rate_percentage']:.1f}% >= {CACHE_HIT_THRESHOLD*100}%")
            return stats
        else:
            print(f"❌ FAIL: Cache hit rate {stats['hit_rate_percentage']:.1f}% < {CACHE_HIT_THRESHOLD*100}%")
            exit(1)

if __name__ == "__main__":
    asyncio.run(measure_cache_performance())