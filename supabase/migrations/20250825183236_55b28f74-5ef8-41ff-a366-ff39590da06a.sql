-- Fix Critical Security Issue 1: Set OTP expiry to recommended threshold (24 hours)
UPDATE auth.config 
SET otp_expiry = 24 * 60 * 60; -- 24 hours in seconds

-- Fix Critical Security Issue 2: Enable leaked password protection
UPDATE auth.config 
SET enable_leaked_password_protection = true;