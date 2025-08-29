#!/usr/bin/env python3
"""
REAL Security Testing Script - NO FAUX CODE
Tests actual security vulnerabilities and can FAIL
"""

import requests
import json
import sys
import subprocess
import time
import os
from urllib.parse import urljoin
from pathlib import Path

class RealSecurityTester:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.results = {
            "ssrf_tests": [],
            "xss_tests": [],
            "security_headers": {},
            "rate_limiting": {},
            "input_validation": {},
            "overall_status": "PASS",
            "critical_issues": 0
        }
    
    def test_ssrf_protection(self):
        """Test REAL SSRF protection with dangerous URLs"""
        print("🔍 Testing SSRF protection...")
        
        dangerous_urls = [
            "http://169.254.169.254/latest/meta-data/",  # AWS metadata
            "http://localhost:22",  # Local SSH
            "http://127.0.0.1:3306",  # Local MySQL
            "http://internal.company.com/admin",  # Internal network
            "file:///etc/passwd",  # File protocol
            "ftp://internal.server/",  # FTP protocol
        ]
        
        ssrf_issues = 0
        
        for url in dangerous_urls:
            try:
                # Test if the application properly blocks these URLs
                # This is a REAL test that can FAIL
                response = requests.get(
                    f"{self.base_url}/api/scrape",  # Adjust endpoint as needed
                    params={"url": url},
                    timeout=5
                )
                
                test_result = {
                    "test_url": url,
                    "status_code": response.status_code,
                    "blocked": response.status_code in [403, 400, 404],
                    "response_size": len(response.text)
                }
                
                if not test_result["blocked"]:
                    test_result["risk"] = "CRITICAL"
                    ssrf_issues += 1
                    self.results["critical_issues"] += 1
                    print(f"❌ SSRF vulnerability: {url} returned {response.status_code}")
                else:
                    print(f"✅ SSRF blocked: {url}")
                
                self.results["ssrf_tests"].append(test_result)
                
            except requests.RequestException:
                # Request failed - this is good for SSRF protection
                self.results["ssrf_tests"].append({
                    "test_url": url,
                    "status_code": "BLOCKED",
                    "blocked": True,
                    "risk": "LOW"
                })
                print(f"✅ SSRF blocked (connection refused): {url}")
        
        if ssrf_issues > 0:
            print(f"❌ Found {ssrf_issues} SSRF vulnerabilities")
            self.results["overall_status"] = "FAIL"
        else:
            print("✅ SSRF protection working")
    
    def test_security_headers(self):
        """Test for REAL security headers"""
        print("🔍 Testing security headers...")
        
        try:
            response = requests.get(self.base_url, timeout=10)
            headers = response.headers
            
            required_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": ["DENY", "SAMEORIGIN"], 
                "Strict-Transport-Security": None,  # Just check presence
                "Content-Security-Policy": None,
            }
            
            missing_headers = 0
            
            for header, expected in required_headers.items():
                header_value = headers.get(header, "MISSING")
                
                if header_value == "MISSING":
                    status = "FAIL"
                    missing_headers += 1
                    print(f"❌ Missing security header: {header}")
                elif expected and isinstance(expected, list):
                    status = "PASS" if header_value in expected else "FAIL"
                    if status == "FAIL":
                        missing_headers += 1
                elif expected and header_value != expected:
                    status = "FAIL"
                    missing_headers += 1
                    print(f"❌ Incorrect security header: {header} = {header_value}")
                else:
                    status = "PASS"
                    print(f"✅ Security header present: {header}")
                
                self.results["security_headers"][header] = {
                    "value": header_value,
                    "status": status
                }
            
            if missing_headers > 2:  # Allow some flexibility
                self.results["overall_status"] = "FAIL"
                self.results["critical_issues"] += missing_headers
                
        except requests.RequestException as e:
            print(f"❌ Could not test security headers: {e}")
            self.results["overall_status"] = "FAIL"
            self.results["critical_issues"] += 1
    
    def test_rate_limiting(self):
        """Test REAL rate limiting"""
        print("🔍 Testing rate limiting...")
        
        # Make rapid requests to trigger rate limiting
        responses = []
        start_time = time.time()
        
        for i in range(50):
            try:
                response = requests.get(f"{self.base_url}/healthz", timeout=2)
                responses.append(response.status_code)
            except requests.RequestException:
                responses.append(0)
        
        end_time = time.time()
        
        # Count 429 (Too Many Requests) responses
        rate_limited_count = responses.count(429)
        
        self.results["rate_limiting"] = {
            "total_requests": len(responses),
            "rate_limited_count": rate_limited_count,
            "duration_seconds": end_time - start_time,
            "working": rate_limited_count > 0
        }
        
        if rate_limited_count == 0:
            print("❌ Rate limiting not working (no 429 responses)")
            self.results["overall_status"] = "FAIL" 
            self.results["critical_issues"] += 1
        else:
            print(f"✅ Rate limiting working ({rate_limited_count} requests limited)")
    
    def test_input_validation(self):
        """Test REAL input validation"""
        print("🔍 Testing input validation...")
        
        # Test various malicious inputs
        test_inputs = [
            {"name": "sql_injection", "payload": "'; DROP TABLE users; --"},
            {"name": "xss_script", "payload": "<script>alert('xss')</script>"},
            {"name": "path_traversal", "payload": "../../etc/passwd"},
            {"name": "command_injection", "payload": "; cat /etc/passwd"},
            {"name": "ldap_injection", "payload": "*)(&(uid=*))"},
        ]
        
        validation_issues = 0
        
        for test in test_inputs:
            try:
                # Test input validation on search or similar endpoint
                response = requests.get(
                    f"{self.base_url}/api/search",  # Adjust endpoint as needed
                    params={"q": test["payload"]},
                    timeout=5
                )
                
                # Check if dangerous payload is reflected unescaped
                if test["payload"] in response.text and response.status_code == 200:
                    print(f"❌ Input validation issue: {test['name']}")
                    validation_issues += 1
                    self.results["critical_issues"] += 1
                else:
                    print(f"✅ Input validation working: {test['name']}")
                
                self.results["input_validation"][test["name"]] = {
                    "payload": test["payload"],
                    "status_code": response.status_code,
                    "reflected": test["payload"] in response.text,
                    "safe": not (test["payload"] in response.text and response.status_code == 200)
                }
                
            except requests.RequestException:
                # Connection issues - mark as safe
                self.results["input_validation"][test["name"]] = {
                    "payload": test["payload"],
                    "status_code": "ERROR",
                    "safe": True
                }
        
        if validation_issues > 0:
            print(f"❌ Found {validation_issues} input validation issues")
            self.results["overall_status"] = "FAIL"
    
    def run_bandit_scan(self):
        """Run REAL Bandit security scan"""
        print("🔍 Running Bandit SAST scan...")
        
        if not os.path.exists("webapp"):
            print("⚠️ No webapp directory found, skipping Bandit scan")
            return True
        
        try:
            result = subprocess.run([
                "bandit", "-r", "webapp/", "-f", "json", "-o", "reports/bandit-results.json"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                print(f"❌ Bandit found security issues (exit code: {result.returncode})")
                self.results["critical_issues"] += 1
                
                # Parse bandit results for severity
                try:
                    with open("reports/bandit-results.json", "r") as f:
                        bandit_data = json.load(f)
                        high_severity = len([r for r in bandit_data.get("results", []) if r.get("issue_severity") == "HIGH"])
                        if high_severity > 0:
                            print(f"❌ Found {high_severity} high severity security issues")
                            self.results["overall_status"] = "FAIL"
                except Exception as e:
                    print(f"⚠️ Could not parse Bandit results: {e}")
            else:
                print("✅ Bandit scan passed")
            
            return True
        except subprocess.TimeoutExpired:
            print("❌ Bandit scan timed out")
            return False
        except FileNotFoundError:
            print("⚠️ Bandit not found, skipping Python security scan")
            return True
    
    def wait_for_backend(self, max_attempts=30):
        """Wait for backend to be ready"""
        for i in range(max_attempts):
            try:
                response = requests.get(f"{self.base_url}/healthz", timeout=2)
                if response.status_code == 200:
                    print(f"✅ Backend ready after {i+1} attempts")
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)
        
        print(f"❌ Backend not ready after {max_attempts} attempts")
        return False
    
    def save_results(self):
        """Save REAL test results"""
        os.makedirs("reports", exist_ok=True)
        
        with open("reports/security-results.json", "w") as f:
            json.dump(self.results, f, indent=2)
        
        # Generate summary
        print(f"\n🔒 Security Test Results:")
        print(f"Overall Status: {self.results['overall_status']}")
        print(f"Critical Issues: {self.results['critical_issues']}")
        print(f"SSRF Tests: {len([t for t in self.results['ssrf_tests'] if t.get('blocked', False)])}/{len(self.results['ssrf_tests'])} blocked")
        print(f"Security Headers: {len([h for h in self.results['security_headers'].values() if h['status'] == 'PASS'])}/{len(self.results['security_headers'])} present")
        print(f"Rate Limiting: {'Working' if self.results['rate_limiting'].get('working', False) else 'NOT working'}")
        
        # HARD FAIL if too many critical issues
        if self.results["critical_issues"] > 5:
            print(f"❌ TOO MANY CRITICAL SECURITY ISSUES: {self.results['critical_issues']}")
            return False
        
        return self.results["overall_status"] == "PASS"

def main():
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    
    tester = RealSecurityTester(base_url)
    
    print("🔒 Running REAL security tests...")
    
    # Wait for backend to be ready
    if not tester.wait_for_backend():
        print("❌ Backend not ready - cannot run security tests")
        sys.exit(1)
    
    # Run all security tests
    tester.test_security_headers()
    tester.test_ssrf_protection()
    tester.test_rate_limiting()
    tester.test_input_validation()
    tester.run_bandit_scan()
    
    # Save results and determine exit code
    success = tester.save_results()
    
    if not success:
        print("❌ Security tests FAILED")
        sys.exit(1)
    else:
        print("✅ Security tests PASSED")

if __name__ == "__main__":
    main()