#!/usr/bin/env python3
"""
DealerScope Validation Summary Generator
Aggregates all validation results into comprehensive summary reports
"""

import json
import os
import glob
from datetime import datetime, timezone
from pathlib import Path

def load_json_file(filepath):
    """Safely load a JSON file, return empty dict if fails"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return {}

def aggregate_security_results(reports_dir):
    """Aggregate all security scan results"""
    security_dir = os.path.join(reports_dir, 'security')
    results = {
        'status': 'PASS',
        'score': 0,
        'total_checks': 0,
        'vulnerabilities': 0,
        'scans_performed': []
    }
    
    if not os.path.exists(security_dir):
        return results
    
    # Load npm audit results
    npm_audit_files = glob.glob(os.path.join(security_dir, 'npm-audit-*.json'))
    if npm_audit_files:
        npm_data = load_json_file(npm_audit_files[0])
        if 'vulnerabilities' in npm_data:
            results['vulnerabilities'] += len(npm_data.get('vulnerabilities', {}))
        results['scans_performed'].append('npm audit')
        results['total_checks'] += 1
        if not npm_data.get('vulnerabilities'):
            results['score'] += 1
    
    # Load safety results
    safety_files = glob.glob(os.path.join(security_dir, 'safety-scan-*.json'))
    if safety_files:
        safety_data = load_json_file(safety_files[0])
        results['scans_performed'].append('Python safety check')
        results['total_checks'] += 1
        if not safety_data.get('vulnerabilities'):
            results['score'] += 1
    
    # Load bandit results
    bandit_files = glob.glob(os.path.join(security_dir, 'bandit-scan-*.json'))
    if bandit_files:
        bandit_data = load_json_file(bandit_files[0])
        results['scans_performed'].append('Bandit SAST')
        results['total_checks'] += 1
        if not bandit_data.get('results'):
            results['score'] += 1
    
    # Load security summary
    summary_files = glob.glob(os.path.join(security_dir, 'security-summary-*.json'))
    if summary_files:
        summary_data = load_json_file(summary_files[0])
        results['status'] = summary_data.get('status', 'UNKNOWN')
        if 'security_percentage' in summary_data:
            results['percentage'] = summary_data['security_percentage']
    
    return results

def aggregate_performance_results(reports_dir):
    """Aggregate all performance test results"""
    perf_dir = os.path.join(reports_dir, 'performance')
    results = {
        'status': 'PASS',
        'lighthouse_score': 0,
        'bundle_size': 'Unknown',
        'optimizations': []
    }
    
    if not os.path.exists(perf_dir):
        return results
    
    # Load Lighthouse simulation
    lighthouse_files = glob.glob(os.path.join(perf_dir, 'lighthouse-simulation-*.json'))
    if lighthouse_files:
        lighthouse_data = load_json_file(lighthouse_files[0])
        perf_data = lighthouse_data.get('performance', {})
        results['lighthouse_score'] = perf_data.get('desktop_score', 0)
    
    # Load bundle analysis
    bundle_files = glob.glob(os.path.join(perf_dir, 'bundle-analysis-*.json'))
    if bundle_files:
        bundle_data = load_json_file(bundle_files[0])
        results['bundle_size'] = bundle_data.get('total_size', 'Unknown')
    
    # Load performance summary
    summary_files = glob.glob(os.path.join(perf_dir, 'performance-summary-*.json'))
    if summary_files:
        summary_data = load_json_file(summary_files[0])
        results['status'] = summary_data.get('status', 'UNKNOWN')
        results['optimizations'] = summary_data.get('recommendations', [])
    
    return results

def generate_comprehensive_summary(reports_dir):
    """Generate the main summary.json file"""
    
    # Aggregate results from all validation categories
    security_results = aggregate_security_results(reports_dir)
    performance_results = aggregate_performance_results(reports_dir)
    
    # Load any existing validation results
    validation_results = {}
    for category in ['auth', 'resilience', 'observability', 'cicd', 'dbops', 'frontend']:
        category_dir = os.path.join(reports_dir, category)
        if os.path.exists(category_dir):
            validation_files = glob.glob(os.path.join(category_dir, '*-validation-*.json'))
            if validation_files:
                validation_results[category] = load_json_file(validation_files[0])
    
    # Calculate overall status
    critical_failures = 0
    total_tests = 0
    passed_tests = 0
    
    # Count security results
    if security_results['status'] == 'FAIL':
        critical_failures += 1
    elif security_results['status'] == 'PASS':
        passed_tests += 1
    total_tests += 1
    
    # Count performance results
    if performance_results['status'] == 'FAIL':
        critical_failures += 1
    elif performance_results['status'] == 'PASS':
        passed_tests += 1
    total_tests += 1
    
    # Count other validation results
    for category, result in validation_results.items():
        status = result.get('status', 'UNKNOWN')
        if status == 'FAIL':
            critical_failures += 1
        elif status == 'PASS':
            passed_tests += 1
        total_tests += 1
    
    # Determine overall status
    if critical_failures > 0:
        overall_status = 'FAIL'
    elif passed_tests == total_tests:
        overall_status = 'PASS'
    else:
        overall_status = 'WARN'
    
    # Build comprehensive summary
    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_commit': os.getenv('GITHUB_SHA', 'unknown'),
        'workflow_run': os.getenv('GITHUB_RUN_NUMBER', 'unknown'),
        'overall_status': overall_status,
        'critical_failures': critical_failures,
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': critical_failures,
        'warned_tests': total_tests - passed_tests - critical_failures,
        'score_percentage': int((passed_tests / total_tests * 100)) if total_tests > 0 else 0,
        'categories': {
            'security': {
                'status': security_results['status'],
                'vulnerabilities_found': security_results.get('vulnerabilities', 0),
                'scans_performed': security_results.get('scans_performed', []),
                'score_percentage': security_results.get('percentage', 0)
            },
            'performance': {
                'status': performance_results['status'],
                'lighthouse_score': performance_results['lighthouse_score'],
                'bundle_size': performance_results['bundle_size'],
                'optimizations': performance_results['optimizations']
            }
        },
        'validation_details': validation_results,
        'recommendations': [
            'Review any failed validation categories',
            'Address security vulnerabilities if found',
            'Monitor performance metrics in production',
            'Keep dependencies updated and secure'
        ]
    }
    
    # Add category-specific recommendations
    if security_results['status'] != 'PASS':
        summary['recommendations'].insert(0, 'Address security vulnerabilities immediately')
    
    if performance_results['status'] != 'PASS':
        summary['recommendations'].insert(1 if security_results['status'] != 'PASS' else 0, 
                                        'Optimize application performance')
    
    return summary

def main():
    """Main function to generate summary report"""
    reports_dir = os.path.join(os.getcwd(), 'validation-reports')
    final_dir = os.path.join(reports_dir, 'final')
    
    # Ensure final directory exists
    os.makedirs(final_dir, exist_ok=True)
    
    # Generate comprehensive summary
    summary = generate_comprehensive_summary(reports_dir)
    
    # Write summary.json
    summary_path = os.path.join(final_dir, 'summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✅ Generated comprehensive summary: {summary_path}")
    print(f"📊 Overall Status: {summary['overall_status']}")
    print(f"🎯 Score: {summary['score_percentage']}%")
    
    return 0 if summary['critical_failures'] == 0 else 1

if __name__ == '__main__':
    exit(main())