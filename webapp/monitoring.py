"""
Application monitoring and metrics
"""
import time
from collections import defaultdict, deque
from fastapi import FastAPI

# Simple in-memory metrics (use Prometheus in production)
metrics = defaultdict(int)
response_times = deque(maxlen=1000)

def setup_monitoring(app: FastAPI):
    """Setup monitoring middleware"""
    
    @app.middleware("http")
    async def monitor_requests(request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        # Record metrics
        process_time = time.time() - start_time
        response_times.append(process_time)
        metrics[f"requests_{response.status_code}"] += 1
        metrics["total_requests"] += 1
        
        return response

def get_metrics():
    """Get current metrics"""
    recent_response_times = list(response_times)[-100:]
    avg_response_time = sum(recent_response_times) / len(recent_response_times) if recent_response_times else 0
    
    return {
        "total_requests": metrics["total_requests"],
        "status_codes": {k: v for k, v in metrics.items() if k.startswith("requests_")},
        "avg_response_time_ms": round(avg_response_time * 1000, 2),
        "health": "healthy"
    }
