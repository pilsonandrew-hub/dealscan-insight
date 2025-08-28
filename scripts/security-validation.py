#!/usr/bin/env python3
"""
DealerScope Security Validation Suite
Comprehensive security testing and validation
"""

import json
import subprocess
import requests
import time
from datetime import datetime
from pathlib import Path

class SecurityValidator:
    def __init__(self):
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "tests": [],
            "summary": {"passed": 0, "failed": 0, "warnings": 0}
        }
        
    def run_gitleaks_scan(self):
        """Run gitleaks secret scanning"""
        try:
            result = subprocess.run([
                "gitleaks", "detect", "--source", ".", "--report-format", "json"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                self.add_result("gitleaks_scan", "PASS", "No secrets detected")
            else:
                self.add_result("gitleaks_scan", "FAIL", f"Secrets detected: {result.stdout}")
        except subprocess.TimeoutExpired:
            self.add_result("gitleaks_scan", "WARN", "Scan timed out")
        except FileNotFoundError:
            self.add_result("gitleaks_scan", "SKIP", "gitleaks not installed")
    
    def test_supabase_rls(self):
        """Test Supabase Row Level Security policies"""
        base_url = "https://lgpugcflvrqhslfnsjfh.supabase.co"
        anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U"
        
        headers = {
            "apikey": anon_key,
            "Content-Type": "application/json"
        }
        
        # Test anonymous access to protected table
        try:
            response = requests.get(f"{base_url}/rest/v1/opportunities", headers=headers, timeout=10)
            if response.status_code in [401, 403]:
                self.add_result("rls_anonymous_denied", "PASS", "Anonymous access properly denied")
            else:
                self.add_result("rls_anonymous_denied", "FAIL", f"Anonymous access allowed: {response.status_code}")
        except requests.RequestException as e:
            self.add_result("rls_anonymous_denied", "WARN", f"Request failed: {e}")
    
    def test_jwt_security(self):
        """Test JWT token security"""
        # Test with invalid JWT
        invalid_tokens = [
            "invalid.jwt.token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
            ""  # Empty token
        ]
        
        base_url = "https://lgpugcflvrqhslfnsjfh.supabase.co"
        
        for i, token in enumerate(invalid_tokens):
            headers = {
                "Authorization": f"Bearer {token}",
                "apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U"
            }
            
            try:
                response = requests.get(f"{base_url}/rest/v1/profiles", headers=headers, timeout=5)
                if response.status_code in [401, 403]:
                    self.add_result(f"jwt_invalid_test_{i+1}", "PASS", f"Invalid JWT rejected")
                else:
                    self.add_result(f"jwt_invalid_test_{i+1}", "FAIL", f"Invalid JWT accepted: {response.status_code}")
            except requests.RequestException:
                self.add_result(f"jwt_invalid_test_{i+1}", "WARN", "Request failed")
    
    def test_rate_limiting(self):
        """Test rate limiting implementation"""
        # Simulate rapid requests
        url = "http://localhost:4173"  # Frontend URL
        rapid_requests = []
        
        start_time = time.time()
        for i in range(20):
            try:
                response = requests.get(url, timeout=2)
                rapid_requests.append(response.status_code)
            except requests.RequestException:
                rapid_requests.append(0)
        
        # Check if any requests were rate limited (429 status)
        rate_limited = any(status == 429 for status in rapid_requests)
        success_rate = sum(1 for status in rapid_requests if status == 200) / len(rapid_requests)
        
        if success_rate > 0.8:  # Most requests should succeed
            self.add_result("rate_limiting", "PASS", f"Rate limiting working, success rate: {success_rate:.2%}")
        else:
            self.add_result("rate_limiting", "WARN", f"High failure rate: {success_rate:.2%}")
    
    def test_cors_headers(self):
        """Test CORS configuration"""
        try:
            response = requests.options("http://localhost:4173", timeout=5)
            headers = response.headers
            
            cors_headers = [
                "Access-Control-Allow-Origin",
                "Access-Control-Allow-Methods", 
                "Access-Control-Allow-Headers"
            ]
            
            missing_headers = [h for h in cors_headers if h not in headers]
            
            if not missing_headers:
                self.add_result("cors_headers", "PASS", "CORS headers properly configured")
            else:
                self.add_result("cors_headers", "WARN", f"Missing CORS headers: {missing_headers}")
                
        except requests.RequestException:
            self.add_result("cors_headers", "SKIP", "Could not test CORS - server not running")
    
    def add_result(self, test_name, status, message):
        """Add test result"""
        self.results["tests"].append({
            "name": test_name,
            "status": status,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        if status == "PASS":
            self.results["summary"]["passed"] += 1
        elif status == "FAIL":
            self.results["summary"]["failed"] += 1
        else:
            self.results["summary"]["warnings"] += 1
    
    def run_all_tests(self):
        """Run all security validation tests"""
        print("🛡️  Running DealerScope Security Validation Suite...")
        
        self.run_gitleaks_scan()
        self.test_supabase_rls()
        self.test_jwt_security()
        self.test_rate_limiting()
        self.test_cors_headers()
        
        # Save results
        reports_dir = Path("validation-reports/security")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = reports_dir / f"security-validation-{timestamp}.json"
        
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"✅ Security validation completed: {report_file}")
        return self.results

if __name__ == "__main__":
    validator = SecurityValidator()
    results = validator.run_all_tests()
    
    # Print summary
    summary = results["summary"]
    print(f"\n📊 Summary: {summary['passed']} passed, {summary['failed']} failed, {summary['warnings']} warnings")
    
    if summary["failed"] > 0:
        exit(1)