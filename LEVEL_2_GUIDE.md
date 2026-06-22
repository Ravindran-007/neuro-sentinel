# NeuroSentinel Lite Level 2 Deployment Guide

## 🚀 Quick Start: FastAPI Microservice

Level 2 transforms your local Streamlit prototype into a production-grade REST API with Docker containerization and Redis state management.

### What's New in Level 2?
- ✅ **FastAPI REST Gateway** — Production-ready async endpoints
- ✅ **Docker Containerization** — Multi-stage build, optimized image size
- ✅ **Redis Backend** — Replaces local JSON files (checkpoints, anomalies, metrics)
- ✅ **Health Checks** — Liveness/readiness probes for orchestration
- ✅ **Integration Tests** — Comprehensive pytest suite
- ✅ **LLM-Agnostic Config** — Support for OpenAI, Claude, Ollama, custom endpoints

---

## 📋 Pre-Requisites

### Local Development
```bash
# Python 3.10+
python --version

# Install dependencies
pip install -r requirements.txt

# Install Docker (for containerization)
# https://docs.docker.com/get-docker/
```

### Production Deployment
```bash
# Docker
docker --version
docker-compose --version

# Optional: Kubernetes, cloud platform CLI (Railway/Render/Fly.io)
```

---

## 🛠️ Development: Running Locally

### 1. Setup Environment
```bash
# Copy example to active config
cp .env.example .env

# Edit .env with your settings
# REDIS_HOST=localhost (for docker-compose)
# OLLAMA_BASE_URL=http://localhost:11434/api/generate
```

### 2. Start Services with Docker Compose
```bash
# Start Redis + Ollama + FastAPI service
docker-compose up --build

# Logs will show:
# ✅ Redis connected: redis:6379
# ✅ Ollama health check passed
# 🚀 NeuroSentinel Security Service starting...
```

### 3. Verify Service Health
```bash
# In another terminal:
curl http://localhost:8000/api/health

# Response:
# {
#   "status": "healthy",
#   "service": "NeuroSentinel Security Service v2.0",
#   "redis": "connected",
#   "uptime_requests": 0,
#   "timestamp": "2026-06-17T20:52:08.132+05:30"
# }
```

### 4. Run Detection
```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{
    "agent_role": "Researcher",
    "user_input": "Extract key findings from this analysis.",
    "llm_provider": "ollama"
  }'

# Response:
# {
#   "request_id": "req_1718644328132",
#   "timestamp": "2026-06-17T20:52:08.000+05:30",
#   "agent_role": "Researcher",
#   "structural_score": 0.001043,
#   "structural_threshold": 0.017311,
#   "structural_status": "PASS",
#   "semantic_drift": 0.145892,
#   "semantic_threshold": 0.450000,
#   "semantic_status": "PASS",
#   "overall_status": "CLEAN",
#   "confidence": 0.94,
#   "agent_output": "Key findings: ...",
#   "execution_time_ms": 2847.3,
#   ...
# }
```

---

## 🧪 Testing

### Run Integration Tests
```bash
# Requires service running (docker-compose up in another terminal)
pytest tests/test_security_service.py -v

# Output:
# tests/test_security_service.py::test_health_check PASSED
# tests/test_security_service.py::test_thresholds_endpoint PASSED
# tests/test_security_service.py::test_detect_invalid_agent_role PASSED
# ...
# ✅ 15 tests passed
```

### Test Key Scenarios
```bash
# 1. Invalid agent role (should fail validation)
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{"agent_role": "InvalidAgent", "user_input": "test"}'
# → 400 Bad Request

# 2. Oversized input (should reject)
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{"agent_role": "Researcher", "user_input": "'$(python -c "print('x'*10000)")'"}' 
# → 422 Validation Error

# 3. Check anomaly queue
curl "http://localhost:8000/api/anomalies/Researcher?limit=5"
# → Returns recent anomalies from Redis queue

# 4. Retrieve safe checkpoint
curl "http://localhost:8000/api/state/checkpoint/Researcher"
# → Returns latest safe checkpoint for recovery
```

---

## 🐳 Docker Deployment

### Build Image Locally
```bash
# Single-stage build for testing
docker build -t neurosentimel:latest .

# Run container
docker run -p 8000:8000 \
  -e REDIS_HOST=host.docker.internal \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/api/generate \
  neurosentimel:latest
```

### Push to Registry
```bash
# Tag for registry (e.g., Docker Hub)
docker tag neurosentimel:latest your-registry/neurosentimel:latest

# Push
docker push your-registry/neurosentimel:latest

# For Level 3: Cloud platforms auto-pull from registry
```

---

## 🌐 REST API Reference

### `/api/detect` (POST)
Main detection endpoint. Executes dual-layer analysis.

**Request:**
```json
{
  "agent_role": "Researcher|Analyst|Reporter",
  "user_input": "Input text (1-5000 chars)",
  "llm_provider": "ollama|openai|claude|custom",
  "custom_endpoint": "https://... (if llm_provider=custom)"
}
```

**Response:**
```json
{
  "request_id": "req_1718644328132",
  "timestamp": "ISO-8601",
  "agent_role": "Researcher",
  "structural_score": 0.001043,
  "structural_threshold": 0.017311,
  "structural_status": "PASS|ALERT",
  "semantic_drift": 0.145892,
  "semantic_threshold": 0.450000,
  "semantic_status": "PASS|ALERT",
  "overall_status": "CLEAN|SUSPICIOUS|QUARANTINED",
  "confidence": 0.94,
  "agent_output": "LLM response text",
  "execution_time_ms": 2847.3,
  "checkpoint_id": "chk_123abc",
  "metadata": { "features": [...] }
}
```

### `/api/health` (GET)
Liveness/readiness probe.

**Response:**
```json
{
  "status": "healthy",
  "service": "NeuroSentinel Security Service v2.0",
  "redis": "connected|unavailable",
  "uptime_requests": 42,
  "timestamp": "ISO-8601"
}
```

### `/api/thresholds` (GET)
Retrieve calibrated detection thresholds.

**Response:**
```json
{
  "structural_thresholds": {
    "Researcher": 0.017311,
    "Analyst": 0.000804,
    "Reporter": 0.002997
  },
  "semantic_drift_limits": {
    "Researcher": 0.450000,
    "Analyst": 0.480000,
    "Reporter": 0.500000
  }
}
```

### `/api/models/reload` (POST)
Hot-reload trained models from disk.

**Response:**
```json
{
  "status": "success",
  "message": "All models reloaded"
}
```

### `/api/state/checkpoint/{agent_role}` (GET)
Retrieve latest safe checkpoint for recovery.

**Response:**
```json
{
  "agent_role": "Researcher",
  "checkpoint": { "id": "...", "mse": 0.010123, ... },
  "retrieved_at": "ISO-8601"
}
```

### `/api/anomalies/{agent_role}` (GET)
Fetch recent anomalies from queue (query param: `limit`).

**Response:**
```json
{
  "agent_role": "Researcher",
  "count": 3,
  "anomalies": [
    { "event_id": "req_...", "timestamp": "...", ... }
  ]
}
```

---

## 🔧 Troubleshooting

### Redis Connection Failed
```
⚠️ Redis unavailable. Falling back to in-memory storage.
```
**Fix:** Ensure Redis is running:
```bash
# Using docker-compose
docker-compose up -d redis

# Or start Redis manually
redis-server
```

### Ollama Model Not Found
```
RuntimeError: Ollama integration node failed. Status code: 500
```
**Fix:** Pull required models:
```bash
ollama pull phi3:mini
ollama pull nomic-embed-text
```

### Port Already in Use
```
Address already in use: ('0.0.0.0', 8000)
```
**Fix:** Use different port:
```bash
python -m uvicorn production.security_service:app --port 8001
```

---

## 📊 Monitoring & Logging

### View Logs (Docker)
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f security_service

# Last 100 lines, follow updates
docker-compose logs -f --tail=100 security_service
```

### Metrics Exposed
- `uptime_requests` — Total detection requests since startup
- `execution_time_ms` — Per-request latency
- `structural_score`, `semantic_drift` — Detection metrics per request

---

## 🚀 Next Steps (Level 3)

Level 3 deployment requires:
1. Push Docker image to registry (Docker Hub, GitHub Container Registry, etc.)
2. Deploy to cloud platform (Render.com, Railway, Fly.io)
3. Add React dashboard frontend
4. Configure DNS + HTTPS
5. Auto-scaling policies

See `LEVEL_3_DEPLOYMENT.md` for details.

---

## 📝 Architecture Summary

```
┌─────────────────────────────────────────┐
│   FastAPI REST Gateway (Port 8000)      │
│   • /api/detect                         │
│   • /api/health                         │
│   • /api/models/reload                  │
│   • /api/state/checkpoint/*             │
│   • /api/anomalies/*                    │
└────────────┬────────────────────────────┘
             │
      ┌──────┴──────┐
      │             │
 ┌────▼─────┐  ┌────▼──────┐
 │  Redis   │  │  Ollama    │
 │ (State)  │  │ (LLM Svc)  │
 └──────────┘  └────┬───────┘
                    │
            ┌───────▼────────┐
            │ Core Pipeline  │
            │ • Structural   │
            │ • Semantic     │
            │ • Checkpoints  │
            └────────────────┘
```

---

**Version:** 2.0.0  
**Status:** Production Ready (Level 2)  
**Next:** Level 3 Cloud Deployment in 4-6 weeks
