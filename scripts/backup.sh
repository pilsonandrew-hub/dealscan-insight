#!/bin/bash

# DealerScope Database Backup Script
# Creates daily backups with retention

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="dealerscope"
DB_USER="dealerscope"
DB_HOST="db"
RETENTION_DAYS=7

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create backup
echo "Starting backup for $DB_NAME at $(date)"
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f "$BACKUP_DIR/dealerscope_backup_$DATE.sql"

# Compress backup
gzip "$BACKUP_DIR/dealerscope_backup_$DATE.sql"

echo "Backup completed: dealerscope_backup_$DATE.sql.gz"

# Remove old backups (keep only last 7 days)
find "$BACKUP_DIR" -name "dealerscope_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Old backups cleaned up (retention: $RETENTION_DAYS days)"

# Verify backup integrity
if [ -f "$BACKUP_DIR/dealerscope_backup_$DATE.sql.gz" ]; then
    echo "✅ Backup verification: Success"
    
    # Optional: Test restore to a temporary database
    # gunzip -c "$BACKUP_DIR/dealerscope_backup_$DATE.sql.gz" | psql -h "$DB_HOST" -U "$DB_USER" -d "test_restore" > /dev/null 2>&1
    # if [ $? -eq 0 ]; then
    #     echo "✅ Restore test: Success"
    #     psql -h "$DB_HOST" -U "$DB_USER" -c "DROP DATABASE test_restore;" > /dev/null 2>&1
    # else
    #     echo "❌ Restore test: Failed"
    # fi
else
    echo "❌ Backup verification: Failed"
    exit 1
fi

echo "Backup process completed successfully"