#!/usr/bin/env python3
"""
HTTP 404 Correctness Test - Phase 1 CI Gate
Validates unknown routes return proper 404 JSON responses
"""

import requests
import json
import os
from pathlib import Path
from typing import Dict, Any

API_BASE = os.getenv('API_BASE', 'http://localhost:4173')

def test_404_correctness() -> Dict[str, Any]:
    """Test that unknown routes return proper 404 responses"""
    print("🔍 Testing 404 correctness...")
    
    test_cases = [
        {
            'url': f"{API_BASE}/api/nonexistent",
            'description': 'API route that does not exist'
        },
        {
            'url': f"{API_BASE}/api/opportunities/invalid-id",
            'description': 'API route with invalid parameter'
        },
        {
            'url': f"{API_BASE}/nonexistent-page",
            'description': 'Frontend route that does not exist'
        },
        {
            'url': f"{API_BASE}/api/unknown-endpoint",
            'description': 'Unknown API endpoint'
        }
    ]
    
    results = []
    passed_tests = 0
    
    for test_case in test_cases:
        try:
            response = requests.get(test_case['url'], timeout=10)
            
            # Check status code
            is_404 = response.status_code == 404
            
            # Check if response is JSON
            is_json = False
            has_error_field = False
            
            try:
                json_data = response.json()
                is_json = True
                has_error_field = 'error' in json_data
            except:
                pass
            
            # Check Content-Type header
            content_type = response.headers.get('content-type', '')
            is_json_content_type = 'application/json' in content_type
            
            test_result = {
                'url': test_case['url'],
                'description': test_case['description'],
                'status_code': response.status_code,
                'is_404': is_404,
                'is_json': is_json,
                'is_json_content_type': is_json_content_type,
                'has_error_field': has_error_field,
                'passed': is_404 and (is_json or is_json_content_type)
            }
            
            if test_result['passed']:
                passed_tests += 1
                print(f"✅ {test_case['description']}: 404 OK")
            else:
                print(f"❌ {test_case['description']}: Status {response.status_code}, JSON: {is_json}")
                
            results.append(test_result)
            
        except Exception as e:
            print(f"❌ {test_case['description']}: Request failed - {e}")
            results.append({
                'url': test_case['url'],
                'description': test_case['description'],
                'error': str(e),
                'passed': False
            })
    
    # Calculate statistics
    total_tests = len(test_cases)
    pass_rate = (passed_tests / total_tests) * 100
    
    stats = {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': total_tests - passed_tests,
        'pass_rate': pass_rate
    }
    
    # Save report
    report = {
        'test_name': '404 Correctness Test',
        'timestamp': time.time(),
        'configuration': {
            'api_base': API_BASE
        },
        'statistics': stats,
        'test_results': results
    }
    
    # Ensure reports directory exists
    Path('reports').mkdir(exist_ok=True)
    
    with open(f'reports/404-correctness-{int(time.time())}.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Console output
    print(f"\n🔍 404 Correctness Results:")
    print(f"Passed Tests: {passed_tests}/{total_tests}")
    print(f"Pass Rate: {pass_rate:.1f}%")
    
    # Validation
    if pass_rate >= 100.0:
        print("✅ PASS: All 404 tests returned proper JSON error responses")
        return stats
    else:
        print("❌ FAIL: Some routes did not return proper 404 responses")
        exit(1)

if __name__ == "__main__":
    import time
    test_404_correctness()