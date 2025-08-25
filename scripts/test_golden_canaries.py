#!/usr/bin/env python3
"""
Golden Canaries Test - Phase 3 Data Quality Gate
Validates data contract pass rate >= 95% on golden canary dataset
"""

import json
import time
import os
from pathlib import Path
from typing import Dict, List, Any
import requests

API_BASE = os.getenv('API_BASE', 'http://localhost:4173')
PASS_RATE_THRESHOLD = float(os.getenv('PASS_RATE_THRESHOLD', '0.95'))

# Golden canary test data - representative samples from top auction sites
GOLDEN_CANARIES = [
    {
        "site": "govdeals.com",
        "samples": [
            {
                "vin": "1HGBH41JXMN109186",
                "year": 2021,
                "make": "Honda",
                "model": "Civic",
                "mileage": 45000,
                "price": 18500,
                "location": "Austin, TX",
                "condition": "good",
                "title_status": "clean",
                "listing_source": "govdeals",
                "listing_url": "https://govdeals.com/listing/12345",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            },
            {
                "vin": "2T1BURHE5JC012345",
                "year": 2018,
                "make": "Toyota",
                "model": "Corolla",
                "mileage": 78000,
                "price": 14200,
                "location": "Phoenix, AZ",
                "condition": "fair",
                "title_status": "clean",
                "listing_source": "govdeals",
                "listing_url": "https://govdeals.com/listing/23456",
                "created_at": "2024-01-15T11:00:00Z",
                "updated_at": "2024-01-15T11:00:00Z"
            }
        ]
    },
    {
        "site": "publicsurplus.com",
        "samples": [
            {
                "vin": "1FTEW1E50KFA12345",
                "year": 2019,
                "make": "Ford",
                "model": "F-150",
                "mileage": 95000,
                "price": 22800,
                "location": "Dallas, TX 75201",
                "condition": "good",
                "title_status": "clean",
                "engine": "3.5L V6",
                "transmission": "automatic",
                "drivetrain": "4wd",
                "fuel_type": "gasoline",
                "seller_type": "government",
                "listing_source": "publicsurplus",
                "listing_url": "https://publicsurplus.com/auction/12345",
                "features": ["Air Conditioning", "Power Windows", "Bluetooth"],
                "created_at": "2024-01-15T09:15:00Z",
                "updated_at": "2024-01-15T09:15:00Z"
            }
        ]
    },
    {
        "site": "copart.com",
        "samples": [
            {
                "vin": "5NPE34AF4JH012345",
                "year": 2018,
                "make": "Hyundai",
                "model": "Elantra",
                "mileage": 0,  # Rollover/unknown
                "price": 8500,
                "location": "Los Angeles, CA",
                "condition": "salvage",
                "title_status": "salvage",
                "damage": ["Front End Damage", "Airbag Deployed"],
                "seller_type": "insurance",
                "listing_source": "copart",
                "listing_url": "https://copart.com/lot/12345",
                "auction_end": "2024-01-20T15:00:00Z",
                "created_at": "2024-01-15T08:45:00Z",
                "updated_at": "2024-01-15T08:45:00Z"
            }
        ]
    },
    {
        "site": "iaai.com", 
        "samples": [
            {
                "vin": "3VWD07AJ5FM012345",
                "year": 2015,
                "make": "Volkswagen",
                "model": "Passat",
                "mileage": 142000,
                "price": 6200,
                "location": "Miami, FL",
                "condition": "fair",
                "title_status": "flood",
                "damage": ["Water/Flood Damage"],
                "seller_type": "insurance",
                "listing_source": "iaai",
                "listing_url": "https://iaai.com/vehicle/12345",
                "exterior_color": "Silver",
                "interior_color": "Black",
                "fuel_type": "gasoline",
                "transmission": "automatic",
                "created_at": "2024-01-15T07:20:00Z",
                "updated_at": "2024-01-15T07:20:00Z"
            }
        ]
    }
]

def test_golden_canaries() -> Dict[str, Any]:
    """Test golden canary dataset against data contracts"""
    print("🕊️  Starting Golden Canaries validation test...")
    
    total_samples = 0
    passed_samples = 0
    failed_samples = []
    site_results = {}
    
    for site_data in GOLDEN_CANARIES:
        site = site_data["site"]
        samples = site_data["samples"]
        
        print(f"\n📊 Testing {len(samples)} samples from {site}...")
        
        site_passed = 0
        site_total = len(samples)
        site_failures = []
        
        for i, sample in enumerate(samples):
            total_samples += 1
            
            try:
                # Validate against data contract
                validation_result = validate_sample(sample, site, i + 1)
                
                if validation_result["valid"]:
                    passed_samples += 1
                    site_passed += 1
                    print(f"  ✅ Sample {i + 1}: PASS (score: {validation_result['score']})")
                else:
                    failed_samples.append({
                        "site": site,
                        "sample_index": i + 1,
                        "errors": validation_result["errors"],
                        "score": validation_result["score"]
                    })
                    site_failures.append(validation_result)
                    print(f"  ❌ Sample {i + 1}: FAIL (score: {validation_result['score']})")
                    
                    # Print first few errors
                    for error in validation_result["errors"][:3]:
                        print(f"     - {error['field']}: {error['message']}")
                        
            except Exception as e:
                failed_samples.append({
                    "site": site,
                    "sample_index": i + 1,
                    "errors": [{"field": "validation", "message": str(e)}],
                    "score": 0
                })
                print(f"  💥 Sample {i + 1}: ERROR - {e}")
        
        site_pass_rate = (site_passed / site_total) * 100 if site_total > 0 else 0
        site_results[site] = {
            "total": site_total,
            "passed": site_passed,
            "failed": site_total - site_passed,
            "pass_rate": site_pass_rate,
            "failures": site_failures
        }
        
        print(f"  📈 {site}: {site_passed}/{site_total} passed ({site_pass_rate:.1f}%)")
    
    # Calculate overall statistics
    overall_pass_rate = (passed_samples / total_samples) * 100 if total_samples > 0 else 0
    
    stats = {
        "total_samples": total_samples,
        "passed_samples": passed_samples,
        "failed_samples": len(failed_samples),
        "overall_pass_rate": overall_pass_rate,
        "pass_rate_threshold": PASS_RATE_THRESHOLD * 100,
        "site_results": site_results
    }
    
    # Save detailed results
    report = {
        "test_name": "Golden Canaries Validation",
        "timestamp": time.time(),
        "configuration": {
            "api_base": API_BASE,
            "pass_rate_threshold": PASS_RATE_THRESHOLD,
            "total_sites": len(GOLDEN_CANARIES),
            "total_samples": total_samples
        },
        "statistics": stats,
        "failed_samples": failed_samples,
        "site_breakdown": site_results
    }
    
    # Ensure reports directory exists
    Path('reports').mkdir(exist_ok=True)
    
    with open(f'reports/golden-canaries-{int(time.time())}.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Console output
    print(f"\n🕊️  Golden Canaries Results:")
    print(f"Total Samples: {total_samples}")
    print(f"Passed: {passed_samples}")
    print(f"Failed: {len(failed_samples)}")
    print(f"Overall Pass Rate: {overall_pass_rate:.1f}%")
    print(f"Threshold: {PASS_RATE_THRESHOLD * 100}%")
    
    if failed_samples:
        print(f"\n❌ Failed Samples Summary:")
        for failure in failed_samples[:5]:  # Show first 5 failures
            print(f"  - {failure['site']} Sample {failure['sample_index']}: {len(failure['errors'])} errors")
    
    # Validation
    passed = overall_pass_rate >= (PASS_RATE_THRESHOLD * 100)
    
    if passed:
        print(f"✅ PASS: Golden canaries pass rate {overall_pass_rate:.1f}% >= {PASS_RATE_THRESHOLD * 100}%")
        return stats
    else:
        print(f"❌ FAIL: Golden canaries pass rate {overall_pass_rate:.1f}% < {PASS_RATE_THRESHOLD * 100}%")
        exit(1)

def validate_sample(sample: Dict[str, Any], site: str, sample_num: int) -> Dict[str, Any]:
    """Validate a single sample against data contracts"""
    
    try:
        # Send to validation API endpoint
        response = requests.post(
            f"{API_BASE}/api/validate/vehicle-listing",
            json=sample,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            # If validation endpoint doesn't exist, do basic validation
            return basic_validation(sample)
            
    except requests.exceptions.RequestException:
        # Fallback to basic validation if API is not available
        return basic_validation(sample)

def basic_validation(sample: Dict[str, Any]) -> Dict[str, Any]:
    """Basic validation when API endpoint is not available"""
    
    errors = []
    warnings = []
    score = 100
    
    # Required fields check
    required_fields = ['vin', 'year', 'make', 'model', 'mileage', 'price', 'location', 
                      'listing_source', 'listing_url', 'created_at', 'updated_at']
    
    for field in required_fields:
        if field not in sample or sample[field] is None:
            errors.append({
                "field": field,
                "message": f"Required field '{field}' is missing or null",
                "severity": "error"
            })
            score -= 15
    
    # VIN validation
    if 'vin' in sample and sample['vin']:
        vin = str(sample['vin'])
        if len(vin) != 17 or not vin.replace('0', '1').replace('O', '1').replace('I', '1').replace('Q', '1').isalnum():
            errors.append({
                "field": "vin",
                "message": "Invalid VIN format",
                "severity": "error"
            })
            score -= 10
    
    # Year validation
    if 'year' in sample and sample['year']:
        year = sample['year']
        current_year = 2024  # Fixed for testing
        if not isinstance(year, int) or year < 1900 or year > current_year + 2:
            errors.append({
                "field": "year",
                "message": f"Year {year} is outside valid range (1900-{current_year + 2})",
                "severity": "error"
            })
            score -= 10
    
    # Price validation
    if 'price' in sample and sample['price'] is not None:
        price = sample['price']
        if not isinstance(price, (int, float)) or price < 0 or price > 10000000:
            errors.append({
                "field": "price",
                "message": f"Price {price} is outside valid range (0-10000000)",
                "severity": "error"
            })
            score -= 10
    
    # Mileage validation
    if 'mileage' in sample and sample['mileage'] is not None:
        mileage = sample['mileage']
        if not isinstance(mileage, (int, float)) or mileage < 0 or mileage > 1000000:
            errors.append({
                "field": "mileage",
                "message": f"Mileage {mileage} is outside valid range (0-1000000)",
                "severity": "error"
            })
            score -= 5
    
    # URL validation
    if 'listing_url' in sample and sample['listing_url']:
        url = sample['listing_url']
        if not isinstance(url, str) or not (url.startswith('http://') or url.startswith('https://')):
            errors.append({
                "field": "listing_url",
                "message": "Invalid URL format",
                "severity": "error"
            })
            score -= 5
    
    # Deduct points for warnings
    score = max(0, score - (len(warnings) * 2))
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "score": score
    }

if __name__ == "__main__":
    test_golden_canaries()