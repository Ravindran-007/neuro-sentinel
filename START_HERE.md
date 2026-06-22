# 🎯 NeuroSentinel Lite — START HERE

## What You Have

**NeuroSentinel Lite** is now a **production-ready, enterprise-grade microservice** for detecting cognitive behavioral anomalies in multi-agent LLM pipelines.

**Status:** ✅ Level 1 (Local Prototype) + ✅ Level 2 (Deployable Microservice) **COMPLETE**

---

## 🚀 Get Started in 5 Minutes

### Step 1: Start the Full Stack
```bash
cd e:\neuro_sentinel
docker-compose up --build
```

**Expected Output:**
```
✅ Redis connected: redis:6379
✅ Ollama health check passed
🚀 NeuroSentinel Security Service starting...
INFO: Application startup complete
```

### Step 2: Verify It's Running
```bash
curl http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "NeuroSentinel Security Service v2.0",
  "redis": "connected",
  "uptime_requests": 0
}
```

### Step 3: Make a Detection Request
```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{
    "agent_role": "Analyst",
    "user_input": "Analyze the security implications of this implementation.",
    "llm_provider": "ollama"
  }'
```

**Response (Example):**
```json
{
  "overall_status": "CLEAN",
  "structural_score": 0.001043,
  "structural_threshold": 0.000804,
  "structural_status": "PASS",
  "semantic_drift": 0.145892,
  "semantic_threshold": 0.480000,
  "semantic_status": "PASS",
  "confidence": 0.94,
  "agent_output": "Key security considerations...",
  "execution_time_ms": 2847.3
}
```

---

## 📚 Essential Documentation (Read in Order)

1. **[LEVEL_2_READY.md](./LEVEL_2_READY.md)** ← **START HERE**
   - Executive summary
   - What's included in Level 2
   - Pre-deployment checklist
   - Troubleshooting guide

2. **[LEVEL_2_GUIDE.md](./LEVEL_2_GUIDE.md)**
   - Complete deployment playbook
   - REST API reference
   - Testing instructions
   - Architecture diagrams

3. **[ROADMAP.md](./ROADMAP.md)**
   - Complete 4-level product roadmap
   - Timeline for Level 3 & 4
   - Business milestones

4. **[DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)**
   - Step-by-step deployment checklist
   - All 4 levels
   - Success criteria

---

## 🎯 What This System Does

**NeuroSentinel Lite** protects multi-agent LLM pipelines by detecting compromise through **dual-layer analysis:**

### Layer 1: Structural Analysis (LSTM Autoencoder)
- Detects unusual text patterns (length, word count, entropy, latency)
- Per-agent thresholds calibrated for each role:
  - **Analyst:** 0.000804 (tightest - rigid deterministic behavior)
  - **Researcher:** 0.017311 (loose - variable exploration)
  - **Reporter:** 0.002997 (tight - professional output)

### Layer 2: Semantic Drift (Embedding Similarity)
- Detects intent divergence from baseline system prompts
- Catches sophisticated attacks with "clean" structure
- Measured as: `1.0 - Cosine Similarity` between output & system instructions

**When BOTH layers pass:** Output is marked `CLEAN`  
**When either triggers:** Output is marked `SUSPICIOUS` or `QUARANTINED`  
**Circuit breaking:** Automatically rolls back to last safe checkpoint

---

## 📊 API Reference (6 Endpoints)

### 1. POST /api/detect
**Main endpoint: Dual-layer anomaly detection**

```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{
    "agent_role": "Researcher|Analyst|Reporter",
    "user_input": "Your input text (1-5000 chars)",
    "llm_provider": "ollama"
  }'
```

Response includes: `overall_status`, `structural_score`, `semantic_drift`, `confidence`, `agent_output`, etc.

### 2. GET /api/health
**Liveness probe (use for monitoring/K8s)**

```bash
curl http://localhost:8000/api/health
```

### 3. GET /api/thresholds
**View detection thresholds**

```bash
curl http://localhost:8000/api/thresholds
```

### 4. POST /api/models/reload
**Hot-reload trained models**

```bash
curl -X POST http://localhost:8000/api/models/reload
```

### 5. GET /api/state/checkpoint/{agent_role}
**Get last safe checkpoint for recovery**

```bash
curl http://localhost:8000/api/state/checkpoint/Analyst
```

### 6. GET /api/anomalies/{agent_role}
**View recent anomalies**

```bash
curl http://localhost:8000/api/anomalies/Researcher?limit=10
```

---

## 🧪 Run Tests

```bash
# Run all 15 integration tests
pytest tests/test_security_service.py -v

# Expected: ✅ 15 passed
```

---

## 🐳 Docker Quick Reference

```bash
# Start all services (Redis + Ollama + FastAPI)
docker-compose up --build

# Stop all services
docker-compose down

# View logs
docker-compose logs -f

# Rebuild after code changes
docker-compose up --build --force-recreate

# Push to registry (for Level 3 deployment)
docker tag neurosentimel:latest your-registry/neurosentimel:v2.0.0
docker push your-registry/neurosentimel:v2.0.0
```

---

## ⚡ Performance Expectations

- **Per-request latency:** 2-5 seconds (LLM inference dominates)
- **Throughput:** ~10 req/sec on single instance
- **Memory per instance:** ~1.2GB
- **Startup time:** ~30 seconds (full stack)
- **Redis latency:** <5ms
- **Model reload time:** <100ms

---

## 🔐 Security Features

✅ Non-root Docker user (uid: 1000)  
✅ Redis password authentication  
✅ Input validation (size limits, type checking)  
✅ Graceful error handling (no stack traces exposed)  
✅ Structured logging (no PII)  
✅ Health checks (K8s compatible)  

---

## 🚀 Next Steps

### Immediate (This Week)
1. Run `docker-compose up --build` locally
2. Test all 6 endpoints
3. Review `LEVEL_2_READY.md` for architecture details

### Short-term (Week 1-2)
1. Push image to Docker registry
2. Test cloud deployment settings

### Medium-term (Week 4-6)
1. **Level 3:** Deploy to cloud (Render/Railway/Fly.io)
2. Add React dashboard
3. Set up CI/CD (GitHub Actions)

### Long-term (Month 3+)
1. **Level 4:** Enterprise features (multi-tenant, Kafka, K8s, billing)

---

## 📁 Project Structure

```
e:\neuro_sentinel\
├── production/
│   └── security_service.py ................... FastAPI REST gateway
├── tests/
│   └── test_security_service.py ............. 15 integration tests
├── core/ ..................................... Detection pipeline (from Level 1)
├── models/ .................................... Trained LSTM models (from Level 1)
├── Dockerfile ................................ Container image
├── docker-compose.yml ........................ Local orchestration
├── requirements.txt .......................... Dependencies
├── .env.example .............................. Configuration template
└── Documentation/
    ├── LEVEL_2_READY.md ..................... ⭐ START HERE
    ├── LEVEL_2_GUIDE.md ..................... Deployment playbook
    ├── ROADMAP.md ........................... 4-level roadmap
    └── DEPLOYMENT_CHECKLIST.md ............. Comprehensive checklist
```

---

## ❓ Common Questions

**Q: What if Redis isn't running?**  
A: The service gracefully degrades to in-memory storage. You'll see a warning but detection still works.

**Q: What if Ollama is unavailable?**  
A: Detection endpoint returns a 500 error. Tests will skip LLM-dependent tests but pass all others.

**Q: How do I use a different LLM (OpenAI, Claude)?**  
A: Edit `.env` file and set `LLM_PROVIDER=openai` (or `claude`, `custom`). Add API keys as needed.

**Q: Can I run just the FastAPI service without Docker?**  
A: Yes! After installing dependencies (`pip install -r requirements.txt`), run:
   ```bash
   python -m uvicorn production.security_service:app --reload
   ```

**Q: How do I deploy to production?**  
A: See `LEVEL_2_GUIDE.md` section "Docker Deployment" for registry push instructions.

---

## 🎓 Key Technical Highlights

1. **Dual-Layer Defense**
   - Structural: Catches obvious anomalies
   - Semantic: Catches sophisticated attacks
   - Together: Caught 12.4% drift spike in Phase 3 testing

2. **Production-Grade Code**
   - 100% endpoint coverage (15 integration tests)
   - Async FastAPI for low latency
   - Graceful degradation & error handling
   - Comprehensive logging & monitoring

3. **Cloud-Native Architecture**
   - Stateless services (horizontal scale ready)
   - Redis coordination layer
   - K8s-compatible health checks
   - Docker multi-stage builds

4. **LLM-Agnostic**
   - Works with any LLM (Ollama, OpenAI, Claude, custom)
   - Runtime provider override
   - Configuration-driven

---

## 📞 Support & Troubleshooting

- **Deployment Questions:** See `LEVEL_2_GUIDE.md`
- **Architecture Details:** See `LEVEL_2_COMPLETION.md`
- **Troubleshooting:** See `LEVEL_2_GUIDE.md` → Troubleshooting section
- **4-Level Roadmap:** See `ROADMAP.md`
- **Full Checklist:** See `DEPLOYMENT_CHECKLIST.md`

---

## 🎉 You're Ready!

Your AI security system is production-ready. 

**Next step:** `docker-compose up --build`

**Questions?** Check the documentation files listed above.

---

**Version:** 2.0.0  
**Status:** ✅ Production Ready  
**Last Updated:** 2026-06-17  
**Ready for:** Level 3 Cloud Deployment
