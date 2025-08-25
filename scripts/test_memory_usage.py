#!/usr/bin/env python3
"""
Memory Usage Testing Script - Phase 1 CI Gate
Validates RSS memory usage < 120MB during sustained load
"""

import psutil
import requests
import time
import json
import os
import threading
from pathlib import Path
from typing import List, Dict, Any

API_BASE = os.getenv('API_BASE', 'http://localhost:4173')
MEMORY_THRESHOLD = int(os.getenv('MEMORY_THRESHOLD', '120'))  # MB
TEST_DURATION = int(os.getenv('TEST_DURATION', '300'))  # seconds

def monitor_memory_usage() -> Dict[str, Any]:
    """Monitor memory usage during API load test"""
    print(f"🧠 Starting memory usage test - threshold: {MEMORY_THRESHOLD}MB")
    
    measurements = []
    load_running = True
    
    def generate_load():
        """Generate sustained API load"""
        session = requests.Session()
        endpoints = [
            '/api/opportunities?page=1&limit=50',
            '/api/opportunities?page=2&limit=50',
            '/api/health'
        ]
        
        while load_running:
            for endpoint in endpoints:
                try:
                    response = session.get(f"{API_BASE}{endpoint}", timeout=5)
                    if response.status_code != 200:
                        print(f"Load request failed: {response.status_code}")
                except Exception as e:
                    print(f"Load request error: {e}")
                time.sleep(0.1)  # 10 RPS per endpoint
    
    # Start load generation
    load_thread = threading.Thread(target=generate_load, daemon=True)
    load_thread.start()
    
    # Monitor memory for test duration  
    start_time = time.time()
    print(f"📊 Monitoring memory for {TEST_DURATION} seconds...")
    
    while time.time() - start_time < TEST_DURATION:
        try:
            # Get current process memory info
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            
            measurement = {
                'timestamp': time.time(),
                'elapsed_seconds': int(time.time() - start_time),
                'rss_mb': memory_mb,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'cpu_percent': process.cpu_percent()
            }
            
            measurements.append(measurement)
            
            # Progress indicator
            if len(measurements) % 20 == 0:
                elapsed = int(time.time() - start_time)
                progress = int((elapsed / TEST_DURATION) * 100)
                print(f"Progress: {elapsed}/{TEST_DURATION}s ({progress}%) - Current RSS: {memory_mb:.1f}MB")
            
        except Exception as e:
            print(f"Memory measurement error: {e}")
        
        time.sleep(5)  # Sample every 5 seconds
    
    # Stop load generation
    load_running = False
    
    if not measurements:
        raise Exception("No memory measurements recorded")
    
    # Calculate statistics
    memory_values = [m['rss_mb'] for m in measurements]
    stats = {
        'total_measurements': len(measurements),
        'min_memory_mb': min(memory_values),
        'max_memory_mb': max(memory_values),
        'avg_memory_mb': sum(memory_values) / len(memory_values),
        'final_memory_mb': memory_values[-1],
        'memory_threshold_mb': MEMORY_THRESHOLD,
        'test_duration_seconds': TEST_DURATION
    }
    
    # Memory trend analysis
    first_half = memory_values[:len(memory_values)//2]
    second_half = memory_values[len(memory_values)//2:]
    first_half_avg = sum(first_half) / len(first_half)
    second_half_avg = sum(second_half) / len(second_half)
    
    stats['memory_trend'] = 'increasing' if second_half_avg > first_half_avg + 10 else \
                           'decreasing' if second_half_avg < first_half_avg - 10 else 'stable'
    stats['memory_growth_mb'] = second_half_avg - first_half_avg
    
    # Save report
    report = {
        'test_name': 'Memory Usage Test',
        'timestamp': time.time(),
        'configuration': {
            'api_base': API_BASE,
            'memory_threshold_mb': MEMORY_THRESHOLD,
            'test_duration_seconds': TEST_DURATION
        },
        'statistics': stats,
        'raw_measurements': measurements
    }
    
    # Ensure reports directory exists
    Path('reports').mkdir(exist_ok=True)
    
    with open(f'reports/memory-usage-{int(time.time())}.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Console output
    print(f"\n🧠 Memory Usage Results:")
    print(f"Peak Memory Usage: {stats['max_memory_mb']:.1f}MB")
    print(f"Average Memory Usage: {stats['avg_memory_mb']:.1f}MB")
    print(f"Final Memory Usage: {stats['final_memory_mb']:.1f}MB")
    print(f"Memory Trend: {stats['memory_trend']} ({stats['memory_growth_mb']:.1f}MB change)")
    
    # Validation
    passed = stats['max_memory_mb'] <= MEMORY_THRESHOLD and stats['memory_trend'] != 'increasing'
    
    if passed:
        print(f"✅ PASS: Peak memory {stats['max_memory_mb']:.1f}MB <= {MEMORY_THRESHOLD}MB")
        return stats
    else:
        print(f"❌ FAIL: Peak memory {stats['max_memory_mb']:.1f}MB > {MEMORY_THRESHOLD}MB")
        exit(1)

if __name__ == "__main__":
    monitor_memory_usage()