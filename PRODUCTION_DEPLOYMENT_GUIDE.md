# DealerScope Production Deployment Guide

## Infrastructure Requirements

### **Minimum Server Requirements**
```yaml
Frontend (Static):
  CPU: 2 vCPU
  RAM: 4GB
  Storage: 20GB SSD
  Bandwidth: 100GB/month

Backend API:
  CPU: 4 vCPU  
  RAM: 8GB
  Storage: 100GB SSD
  Database: PostgreSQL 13+
```

### **Recommended Architecture**
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CDN/Proxy    │    │   Load Balancer  │    │   API Servers   │
│   (Cloudflare) │────│   (NGINX/HAProxy)│────│   (FastAPI)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
                       ┌──────────────────┐    ┌─────────────────┐
                       │   WebSocket      │    │   PostgreSQL    │
                       │   Server         │    │   Database      │
                       └──────────────────┘    └─────────────────┘
```

## Environment Configuration

### **Production Environment Variables**
```bash
# Frontend (.env.production)
VITE_API_URL=https://api.dealerscope.com
VITE_WS_URL=wss://ws.dealerscope.com
VITE_APP_VERSION=4.8.0
VITE_BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VITE_GIT_COMMIT=$(git rev-parse HEAD)

# Backend
DATABASE_URL=postgresql://user:pass@db:5432/dealerscope
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your-super-secure-secret-key
CORS_ORIGINS=https://dealerscope.com,https://www.dealerscope.com
```

## Deployment Steps

### **1. Frontend Deployment (Static)**
```bash
# Build optimized production bundle
npm run build

# Deploy to CDN (example with AWS S3/CloudFront)
aws s3 sync dist/ s3://dealerscope-frontend --delete
aws cloudfront create-invalidation --distribution-id E1234567890 --paths "/*"
```

### **2. Backend API Deployment**
```dockerfile
# Dockerfile for FastAPI backend
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### **3. Docker Compose (Development/Staging)**
```yaml
version: '3.8'
services:
  frontend:
    build: .
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
      
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/dealerscope
    depends_on:
      - db
      
  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=dealerscope
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Performance Optimization

### **CDN Configuration**
```nginx
# NGINX configuration for optimal caching
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    add_header Vary Accept-Encoding;
    gzip_static on;
}

location / {
    try_files $uri $uri/ /index.html;
    add_header Cache-Control "no-cache";
}
```

### **Database Optimization**
```sql
-- Essential indexes for production
CREATE INDEX CONCURRENTLY idx_opportunities_state ON opportunities(state);
CREATE INDEX CONCURRENTLY idx_opportunities_score ON opportunities(score DESC);
CREATE INDEX CONCURRENTLY idx_opportunities_created ON opportunities(created_at DESC);
CREATE INDEX CONCURRENTLY idx_listings_auction_end ON listings(auction_end);
```

## Monitoring & Alerting

### **Health Check Endpoints**
```typescript
// Backend health endpoints
GET /health          // Basic health check
GET /health/detailed // Component-specific health
GET /metrics         // Prometheus metrics
```

### **Logging Configuration**
```json
{
  "logging": {
    "level": "INFO",
    "format": "json",
    "outputs": ["stdout", "file"],
    "retention": "30d"
  }
}
```

## Security Hardening

### **SSL/TLS Configuration**
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
```

### **Security Headers**
```typescript
// Add to API responses
{
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
  "X-Content-Type-Options": "nosniff",  
  "X-Frame-Options": "DENY",
  "X-XSS-Protection": "1; mode=block",
  "Referrer-Policy": "strict-origin-when-cross-origin"
}
```

## Backup & Recovery

### **Database Backup Strategy**
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL > /backups/dealerscope_$DATE.sql
aws s3 cp /backups/dealerscope_$DATE.sql s3://dealerscope-backups/
```

### **Application Backup**
```bash
# Static assets and configuration backup
tar -czf app_backup_$(date +%Y%m%d).tar.gz \
  dist/ \
  .env.production \
  docker-compose.yml
```

## Scaling Considerations

### **Horizontal Scaling**
- Load balancer with multiple API instances
- Database read replicas for analytics
- Redis cluster for distributed caching
- CDN for global static asset delivery

### **Vertical Scaling Triggers**
- CPU usage > 80% for 5 minutes
- Memory usage > 85%
- Database connection pool > 80% utilized
- Response time > 2 seconds

---

**Note:** This deployment guide assumes the FastAPI backend from the bootstrap script is implemented. Frontend is production-ready and can be deployed immediately.