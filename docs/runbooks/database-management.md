# DealerScope Database Management & Recovery Runbook

**Owner:** Database Administration Team  
**Last Updated:** 2025-09-07  
**Classification:** Internal - Operations Manual

## Overview

This document covers standard operating procedures for managing the DealerScope database infrastructure (Supabase/PostgreSQL) including backup verification, schema migrations, and disaster recovery procedures.

## 1. Database Architecture Overview

### Primary Database
- **Provider:** Supabase (Managed PostgreSQL)
- **Environment:** Production
- **Location:** US-East-1 (Primary)
- **Instance Type:** [To be documented based on actual deployment]

### Backup Strategy
- **Method:** Supabase Point-in-Time Recovery (PITR)
- **Frequency:** Continuous WAL shipping
- **Retention:** 7 days (Standard Plan) - **ACTION ITEM:** Upgrade for compliance requirements
- **Cross-Region:** Manual export required for DR

## 2. Schema Migration Procedures

> **CRITICAL:** Schema changes must NEVER be applied directly to production without following this process.

### Development Phase
1. **Migration Script Creation:**
   ```bash
   # Create timestamped migration file
   touch db/migrations/$(date +%Y%m%d_%H%M%S)_descriptive_name.sql
   ```

2. **Migration Script Structure:**
   ```sql
   -- Migration: Add vehicle index for performance
   -- Date: 2025-09-07
   -- Author: [Your Name]
   
   BEGIN;
   
   -- Add your changes here
   CREATE INDEX CONCURRENTLY idx_vehicles_make_model ON vehicles(make, model);
   
   -- Verification query
   SELECT schemaname, tablename, indexname 
   FROM pg_indexes 
   WHERE indexname = 'idx_vehicles_make_model';
   
   COMMIT;
   ```

### Review & Testing Phase
1. **Pull Request Creation:**
   - Include migration script in PR
   - Document expected impact and rollback plan
   - Require minimum 2 engineering approvals

2. **Automated Testing:**
   ```yaml
   # CI Pipeline should include migration testing
   - name: Test Migration
     run: |
       # Apply migration to test database
       supabase db push --dry-run
       # Run integration tests
       npm run test:integration
   ```

### Staging Deployment
1. **Pre-Migration Checklist:**
   - [ ] Verify staging database is up-to-date
   - [ ] Confirm no active long-running queries
   - [ ] Take manual snapshot before migration
   - [ ] Alert team of maintenance window

2. **Execute Migration:**
   ```bash
   # Apply to staging
   supabase db push --environment staging
   
   # Verify migration success
   supabase db diff --environment staging
   ```

3. **Post-Migration Validation:**
   - [ ] Run application smoke tests
   - [ ] Verify data integrity queries
   - [ ] Check application performance
   - [ ] Monitor error logs for 1 hour

### Production Deployment
1. **Maintenance Window Setup:**
   - Schedule during lowest traffic period (typically 2-4 AM EST)
   - Set status page to "Under Maintenance"
   - Enable application maintenance mode

2. **Pre-Production Checklist:**
   - [ ] Staging migration validated ✅
   - [ ] Team on standby for rollback if needed
   - [ ] Database performance baseline captured
   - [ ] Rollback plan documented and tested

3. **Production Migration Execution:**
   ```bash
   # Take final backup
   supabase db backup create --name "pre-migration-$(date +%Y%m%d)"
   
   # Apply migration
   supabase db push --environment production
   
   # Immediate verification
   supabase db diff --environment production
   ```

4. **Post-Production Validation:**
   - [ ] Application startup successful
   - [ ] Critical user flows tested
   - [ ] Database metrics within normal range
   - [ ] Remove maintenance mode
   - [ ] Update status page to operational

## 3. Point-in-Time Recovery (PITR) Procedure

> **WARNING:** This procedure is for SEV-1 data loss scenarios ONLY. Follow incident response protocol.

### Prerequisites for Recovery
- Incident Commander assigned and war room established
- Exact timestamp of data corruption/loss identified
- Legal/compliance team notified (if PII affected)
- All application writes stopped

### Recovery Steps

#### Phase 1: Preparation (5-10 minutes)
1. **Application Lockdown:**
   ```bash
   # Enable maintenance mode
   kubectl apply -f maintenance-mode.yaml
   
   # Verify no active connections
   SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
   ```

2. **Identify Recovery Point:**
   - Review incident timeline
   - Identify last known good timestamp
   - Verify recovery point with stakeholders
   - Document decision rationale

#### Phase 2: Recovery Execution (15-30 minutes)
1. **Access Supabase Dashboard:**
   - Navigate to Database → Backups
   - Select "Point-in-Time Recovery"
   
2. **Configure Restore:**
   ```json
   {
     "recovery_target_time": "2025-09-07 14:30:00 UTC",
     "recovery_target_action": "promote",
     "confirmation": true
   }
   ```

3. **Initiate Recovery:**
   - Double-check target timestamp
   - Confirm target instance (production)
   - Execute restoration
   - Monitor progress in Supabase console

#### Phase 3: Verification & Restoration (15-30 minutes)
1. **Data Integrity Verification:**
   ```sql
   -- Check critical tables
   SELECT COUNT(*) FROM vehicles WHERE created_at < '2025-09-07 14:30:00';
   SELECT MAX(created_at) FROM auction_data;
   
   -- Verify referential integrity
   SELECT COUNT(*) FROM vehicles v 
   LEFT JOIN auctions a ON v.auction_id = a.id 
   WHERE a.id IS NULL;
   ```

2. **Application Validation:**
   - Start application in read-only mode
   - Run critical data validation queries
   - Perform manual spot checks of recent data
   - Verify user authentication system

3. **Service Restoration:**
   ```bash
   # Remove maintenance mode
   kubectl delete -f maintenance-mode.yaml
   
   # Monitor application startup
   kubectl logs -f deployment/dealerscope-api
   
   # Update status page
   curl -X POST https://status.dealerscope.com/api/incidents/resolve
   ```

#### Phase 4: Post-Recovery Actions (Within 24 hours)
- [ ] Complete incident post-mortem
- [ ] Review and update backup retention policies
- [ ] Implement additional monitoring for early detection
- [ ] Document lessons learned and process improvements

## 4. Backup Verification Procedures

### Monthly Backup Integrity Check
```bash
#!/bin/bash
# Monthly backup verification script
# Run first Sunday of each month

echo "Starting backup verification for $(date +%Y-%m)"

# Create temporary restoration environment
supabase projects create test-restore-$(date +%Y%m%d)

# Restore latest backup
supabase db restore --project test-restore --timestamp "24 hours ago"

# Run data integrity checks
supabase db sql --project test-restore --file verification-queries.sql

# Cleanup
supabase projects delete test-restore-$(date +%Y%m%d)

echo "Backup verification completed successfully"
```

### Verification Queries (`verification-queries.sql`)
```sql
-- Critical data volume checks
SELECT 
  'vehicles' as table_name,
  COUNT(*) as row_count,
  MAX(created_at) as latest_record
FROM vehicles
UNION ALL
SELECT 
  'auctions' as table_name,
  COUNT(*) as row_count,
  MAX(created_at) as latest_record  
FROM auctions;

-- Referential integrity checks
SELECT 
  COUNT(*) as orphaned_vehicles
FROM vehicles v
LEFT JOIN auctions a ON v.auction_id = a.id
WHERE a.id IS NULL AND v.auction_id IS NOT NULL;

-- Recent data consistency
SELECT 
  DATE_TRUNC('day', created_at) as date,
  COUNT(*) as daily_volume
FROM vehicles 
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;
```

## 5. Performance Monitoring & Optimization

### Daily Health Checks
```sql
-- Query performance monitoring
SELECT 
  query,
  calls,
  total_time,
  mean_time,
  rows
FROM pg_stat_statements 
WHERE mean_time > 1000  -- Queries slower than 1 second
ORDER BY mean_time DESC
LIMIT 10;

-- Index utilization
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0  -- Unused indexes
ORDER BY pg_relation_size(indexrelid) DESC;

-- Table bloat detection
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  pg_stat_get_tuples_inserted(c.oid) as inserts,
  pg_stat_get_tuples_updated(c.oid) as updates,
  pg_stat_get_tuples_deleted(c.oid) as deletes
FROM pg_tables pt
JOIN pg_class c ON c.relname = pt.tablename
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## 6. Emergency Contacts & Escalation

### Primary Contacts
- **Database Administrator:** [DBA Email] / [Phone]
- **DevOps Lead:** [DevOps Email] / [Phone]  
- **Incident Commander:** [IC Email] / [Phone]

### Supabase Support
- **Support Portal:** https://supabase.com/dashboard/support
- **Enterprise Support:** [Enterprise Support Details]
- **Emergency Escalation:** [Emergency Contact if available]

## 7. Compliance & Audit Requirements

### Data Retention Policies
- **Transaction Logs:** 90 days minimum
- **Backup Retention:** 30 days minimum (regulatory requirement)
- **Audit Logs:** 1 year retention required

### Regular Audit Tasks
- [ ] Monthly backup verification (automated)
- [ ] Quarterly security audit of database access
- [ ] Annual disaster recovery test
- [ ] Bi-annual compliance review

---

**Remember:** When in doubt, prioritize data integrity over speed. It's better to take additional time to verify a recovery than to compound data loss through hasty decisions.