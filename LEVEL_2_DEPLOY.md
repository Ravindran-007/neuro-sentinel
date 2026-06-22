# 🚀 Level 2 Deployment Checklist

## Current Status
- ✅ Docker Desktop is running
- ✅ All Level 2 files created (37KB code + 54KB docs)
- ⏳ Ready to deploy services

---

## Step 1: Deploy Services (3-5 minutes)

Open PowerShell and run:

```bash
cd e:\neuro_sentinel
docker-compose up --build
```

**Expected output:**
```
Creating network "neuro_sentinel_default" with the default driver
Building security_service
Step 1/15 : FROM python:3.11-slim as builder
...
Creating neuro_sentinel-redis-1 ... done
Creating neuro_sentinel-ollama-1 ... done
Creating neuro_sentinel-security_service-1 ... done
```

**Success indicator - look for:**
```
✓ Uvicorn running on 0.0.0.0:8000
✓ Application startup complete
```

⚠️ **Keep this terminal open.** Services run in foreground.

---

## Step 2: Verify Services (in new terminal)

### 2a: Test Health Endpoint
```bash
curl http://localhost:8000/api/health
```

**Expected response:**
```json
{"status": "healthy", "service": "NeuroSentinel Security Service v2.0"}
```

### 2b: Check Running Containers
```bash
docker ps
```

**Expected output:**
```
CONTAINER ID   IMAGE                                 STATUS
abc123...      neuro_sentinel-security_service      Up 2 minutes
def456...      redis:7-alpine                       Up 2 minutes
ghi789...      ollama/ollama:latest                 Up 2 minutes
```

### 2c: View Service Logs
```bash
docker-compose logs -f security_service
```

**Expected output:**
```
security_service-1  | INFO:     Started server process [1]
security_service-1  | INFO:     Waiting for application startup.
security_service-1  | INFO:     Application startup complete
```

---

## Step 3: Run Integration Tests (2 minutes)

Open new terminal and run:

```bash
cd e:\neuro_sentinel
pytest tests/test_security_service.py -v
```

**Expected output:**
```
test_health_check PASSED
test_detect_request PASSED
test_invalid_agent_role PASSED
test_threshold_retrieval PASSED
test_checkpoint_retrieval PASSED
test_anomalies_list PASSED
...
======================== 15 passed in 2.34s =========================
```

**Success:** All 15 tests pass ✅

---

## Step 4: Manual Endpoint Testing (5 minutes)

### 4a: Test Detection Endpoint

```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_role\": \"Researcher\",
    \"output\": \"This is a normal analysis of market trends for Q2 2024.\"
  }"
```

**Expected response:**
```json
{
  "request_id": "abc123...",
  "agent_role": "Researcher",
  "is_anomaly": false,
  "structural_score": 0.012,
  "semantic_drift": 0.15,
  "processing_time_ms": 342
}
```

### 4b: Test Thresholds Endpoint

```bash
curl http://localhost:8000/api/thresholds
```

**Expected response:**
```json
{
  "Researcher": 0.017311,
  "Analyst": 0.000804,
  "Reporter": 0.002997
}
```

### 4c: Test Model Reload

```bash
curl -X POST http://localhost:8000/api/models/reload
```

**Expected response:**
```json
{"status": "success", "models_reloaded": ["lstm_researcher", "lstm_analyst", "lstm_reporter"]}
```

---

## Step 5: Performance Baseline (1 minute)

Test response times under load:

```bash
# Single request
time curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d "{\"agent_role\": \"Analyst\", \"output\": \"Analysis complete.\"}"
```

**Expected:** 300-800ms (first request may be slower)

---

## Troubleshooting

### Error: "Connection refused" on health check
- **Cause:** Services still starting
- **Fix:** Wait 30 seconds, try again

### Error: "Cannot connect to Docker daemon"
- **Cause:** Docker Desktop crashed
- **Fix:** Restart Docker Desktop

### Error: "Port 8000 already in use"
- **Cause:** Service already running in another process
- **Fix:** `docker-compose down && docker-compose up --build`

### Error: "Redis connection failed"
- **Cause:** Redis service didn't start
- **Fix:** `docker-compose logs redis` to check

### Tests timeout
- **Cause:** Services too slow to respond
- **Fix:** Check `docker-compose logs` for errors

---

## Success Criteria: Level 2 VERIFIED ✅

- [ ] `docker-compose up --build` completes without errors
- [ ] `docker ps` shows 3 containers running (security_service, redis, ollama)
- [ ] `curl /api/health` returns `{"status": "healthy"}`
- [ ] `pytest tests/test_security_service.py -v` shows 15/15 PASSED
- [ ] `/api/detect` endpoint responds with JSON anomaly scores
- [ ] `/api/thresholds` shows all 3 agent thresholds
- [ ] All requests complete in <1 second

---

## Next Steps After Verification

Once all checks pass, you can:

1. **Stop services for now:**
   ```bash
   # In first terminal where docker-compose is running
   Press Ctrl+C
   ```

2. **View what Level 2 includes:**
   ```bash
   cat LEVEL_2_COMPLETION.md
   ```

3. **Prepare for Level 3** (Cloud Deployment):
   - Create Docker Hub account
   - Push image to registry
   - Deploy to Render.com or Railway
   - Setup CI/CD pipeline

---

## Important Files

- `docker-compose.yml` - Service orchestration
- `production/security_service.py` - FastAPI application
- `tests/test_security_service.py` - Integration tests
- `Dockerfile` - Container build definition
- `.env.example` - Configuration template

---

**Status:** Docker running. Ready to deploy Level 2 services.
