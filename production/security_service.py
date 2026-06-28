# production/security_service.py
# NeuroSentinel Lite (Level 4 Deployable Production Layer)
# Fully unified syntax with Dual-Layer Detection + Groq API Support + Enterprise Auth

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS

# ─────────────────────────────────────────────────────────────
# GNN IMPORTS — TEMPORARILY DISABLED FOR RENDER DEPLOYMENT
# ─────────────────────────────────────────────────────────────
# from core.gnn import GNNPropagationDetector

# ─────────────────────────────────────────────────────────────
# KAFKA IMPORTS — DISABLED FOR RENDER DEPLOYMENT
# ─────────────────────────────────────────────────────────────
# from core.kafka_producer import kafka_producer

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("NeuroSentinel-Service")
settings = SystemSettings()

app = FastAPI(
    title="NeuroSentinel Security Service",
    description="Dual-Layer Detection: Structural Fingerprinting + Semantic Drift",
    version="2.0.0"
)

# --- CORRECTED PERMISSIVE CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# API KEY AUTHENTICATION — ENTERPRISE MODE
# ─────────────────────────────────────────────────────────────

API_KEYS = {
    "demo_key": {"tenant": "demo", "name": "Demo User", "active": True},
    # Add more keys for testing
}

def verify_api_key(api_key: str) -> Optional[Dict]:
    """Verify API key and return tenant info."""
    if not api_key:
        return None
    tenant_info = API_KEYS.get(api_key)
    if tenant_info and tenant_info.get("active", True):
        return tenant_info
    return None

# ─────────────────────────────────────────────────────────────
# AUTHENTICATION MIDDLEWARE
# ─────────────────────────────────────────────────────────────

@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    # Skip auth for health check and docs
    public_paths = ["/api/health", "/docs", "/openapi.json", "/redoc"]
    if any(request.url.path.startswith(path) for path in public_paths):
        return await call_next(request)
    
    # Get API key from header
    api_key = request.headers.get("X-API-Key")
    
    # For demo mode: if no key, use default demo key
    if not api_key:
        logger.warning(f"⚠️ No API key provided for {request.url.path}")
        request.state.tenant = "demo"
        request.state.api_key = None
        return await call_next(request)
    
    # Verify API key
    tenant_info = verify_api_key(api_key)
    if not tenant_info:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid API key. Please provide a valid key."}
        )
    
    # Set tenant info in request state
    request.state.tenant = tenant_info["tenant"]
    request.state.api_key = api_key
    logger.info(f"🔑 Authenticated tenant: {tenant_info['tenant']}")
    
    return await call_next(request)

# --- REDIS BACKEND CONNECTION ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASS = os.getenv("REDIS_PASSWORD", None)

try:
    redis_client = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        db=REDIS_DB, 
        password=REDIS_PASS, 
        decode_responses=True, 
        socket_connect_timeout=5
    )
    redis_client.ping()
    logger.info(f"💾 Redis connected: {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"⚠️ Redis unavailable ({e}). Using in-memory fallback.")
    redis_client = None

# ─────────────────────────────────────────────────────────────
# AGENT ROLE VALIDATION — ENTERPRISE MODE
# ─────────────────────────────────────────────────────────────
# Accept ANY agent name — companies can use their own agent names

def validate_agent_role(agent_role: str):
    # Accept any agent name — no validation
    logger.info(f"📝 Agent role: {agent_role}")
    return agent_role

# --- REQUEST / RESPONSE SCHEMAS ---
class DetectionRequest(BaseModel):
    agent_role: str = Field(..., description="Target agent name (any name accepted)")
    user_input: str = Field(..., min_length=1, max_length=5000, description="Input prompt to analyze")
    llm_provider: str = Field(default="groq", description="LLM backend: groq, ollama, openai, claude, custom")
    custom_endpoint: Optional[str] = Field(default=None, description="Custom LLM endpoint URL")

    @validator('agent_role')
    def validate_role(cls, v):
        # Accept any agent name — enterprise mode
        if not v or len(v.strip()) == 0:
            raise ValueError("Agent role cannot be empty")
        return v.strip()

class DetectionResult(BaseModel):
    request_id: str
    timestamp: str
    agent_role: str
    structural_score: float
    structural_threshold: float
    structural_status: str
    semantic_drift: float
    semantic_threshold: float
    semantic_status: str
    overall_status: str
    confidence: float
    agent_output: str
    execution_time_ms: float
    checkpoint_id: Optional[str] = None
    metadata: Dict[str, Any] = {}

@dataclass
class AnomalyEvent:
    event_id: str
    timestamp: str
    agent_role: str
    structural_score: float
    semantic_drift: float
    user_input: str
    detection_result: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

# --- CORE DETECTION ENGINE SINGLETON ---
class SecurityEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        logger.info("🔧 Initializing NeuroSentinel Security Engine...")
        self.pipeline = IndustrialPipeline(settings=settings)
        self.request_count = 0
        self.initialized = True
        logger.info("🚀 Security Engine initialized successfully.")

    async def detect(self, req: DetectionRequest) -> DetectionResult:
        request_id = f"req_{int(time.time() * 1000)}"
        self.request_count += 1
        validate_agent_role(req.agent_role)
        start_time = time.perf_counter()
        is_cloud = os.getenv("RENDER", "false").lower() == "true"

        try:
            node = self.pipeline.nodes.get(req.agent_role)
            if not node:
                # For custom agents, use a default node
                from core.engine import AgentNode
                node = AgentNode(req.agent_role, f"Process input for {req.agent_role}")
                # Register in pipeline for future use
                self.pipeline.nodes[req.agent_role] = node
                logger.info(f"🆕 New agent registered: {req.agent_role}")
            
            # ── Layer 0: LLM Inference Engine ──
            backend = "groq" if os.getenv("GROQ_API_KEY") else "ollama"
            logger.info(f"🔀 LLM backend: {backend}")
            agent_output, exec_time = self.pipeline._execute_inference(node, req.user_input)

            # ── Layer 1: Structural Analysis ──
            telemetry = self.pipeline.tap.extract_features(
                session_id=request_id, 
                sender=req.agent_role, 
                receiver="SecurityService", 
                payload=agent_output, 
                execution_time=exec_time
            )
            m = telemetry["metrics"]
            features = [m["length"], m["word_count"], m["entropy"], m["execution_time"]]
            
            structural_score = self.pipeline._score_agent_structure(req.agent_role, features)
            structural_threshold = THRESHOLDS.get(req.agent_role, 0.01)
            structural_status = "PASS" if structural_score <= structural_threshold else "ALERT"

            # ── Layer 2: Semantic Drift ──
            semantic_drift = self.pipeline.semantic_detector.calculate_drift(req.agent_role, agent_output)
            semantic_threshold = SEMANTIC_DRIFT_LIMITS.get(req.agent_role, 0.45)
            semantic_status = "PASS" if semantic_drift <= semantic_threshold else "ALERT"

            # Overall Decision
            if structural_status == "ALERT" or semantic_status == "ALERT":
                overall_status = "SUSPICIOUS"
            else:
                overall_status = "CLEAN"

            confidence = 1.0 - (structural_score / (structural_threshold + 1e-5))
            confidence = max(0.0, min(1.0, confidence))

            # Quarantine Rollback
            checkpoint_id = None
            if overall_status == "SUSPICIOUS":
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                    overall_status = "QUARANTINED"
                except Exception as e:
                    logger.warning(f"State rollbacks skipped: {e}")

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            result = DetectionResult(
                request_id=request_id,
                timestamp=datetime.utcnow().isoformat(),
                agent_role=req.agent_role,
                structural_score=float(structural_score),
                structural_threshold=float(structural_threshold),
                structural_status=structural_status,
                semantic_drift=float(semantic_drift),
                semantic_threshold=float(semantic_threshold),
                semantic_status=semantic_status,
                overall_status=overall_status,
                confidence=float(confidence),
                agent_output=(agent_output or "No output")[:1000],
                execution_time_ms=float(elapsed_ms),
                checkpoint_id=checkpoint_id,
                metadata={
                    "features": features,
                    "llm_provider": req.llm_provider,
                    "llm_execution_ms": float(exec_time * 1000),
                    "cloud_mode": is_cloud,
                    "llm_backend": backend
                }
            )

            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)

            if redis_client:
                await self._persist_detection(result)

            return result

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            logger.error(f"🚨 System pipeline error: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _queue_anomaly_event(self, result: DetectionResult, user_input: str):
        try:
            event = AnomalyEvent(
                event_id=result.request_id,
                timestamp=result.timestamp,
                agent_role=result.agent_role,
                structural_score=result.structural_score,
                semantic_drift=result.semantic_drift,
                user_input=user_input,
                detection_result=result.dict()
            )
            if redis_client:
                queue_key = f"neurosentinel:anomaly_queue:{result.agent_role}"
                redis_client.lpush(queue_key, event.to_json())
                redis_client.expire(queue_key, 86400)
                logger.info(f"🚨 Incident queued: {result.request_id}")
        except Exception as e:
            logger.warning(f"Incident queuing bypassed: {e}")

    async def _persist_detection(self, result: DetectionResult):
        try:
            key = f"neurosentinel:detection:{result.request_id}"
            redis_client.set(key, json.dumps(result.dict()), ex=86400)
        except Exception as e:
            logger.warning(f"Persistence bypassed: {e}")

# Instantiates Singleton Engines
engine = SecurityEngine()

# --- REST ENDPOINTS ---
@app.post("/api/detect", response_model=DetectionResult)
async def detect_anomaly(request: DetectionRequest, fastapi_request: Request):
    tenant = getattr(fastapi_request.state, "tenant", "unknown")
    logger.info(f"🏢 Tenant: {tenant} | Agent: {request.agent_role} | Text size: {len(request.user_input)}")
    result = await engine.detect(request)
    result.metadata["tenant"] = tenant
    return result

@app.get("/api/health")
async def health_check():
    redis_status = "connected" if redis_client else "unavailable"
    return {
        "status": "healthy",
        "service": "NeuroSentinel Security Service v2.0",
        "redis": redis_status,
        "uptime_requests": engine.request_count,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/thresholds")
async def get_thresholds():
    return {
        "structural_thresholds": THRESHOLDS,
        "semantic_drift_limits": SEMANTIC_DRIFT_LIMITS,
        "note": "Analyst has the tightest structural threshold (0.000804) due to deterministic validation paths."
    }

@app.post("/api/models/reload")
async def reload_models():
    try:
        engine.pipeline = IndustrialPipeline(settings=settings)
        logger.info("🔄 Models reloaded")
        return {"status": "success", "message": "All models reloaded"}
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state/checkpoint/{agent_role}")
async def get_checkpoint(agent_role: str):
    try:
        checkpoint = engine.pipeline.checkpoints.retrieve_safe_checkpoint(agent_role)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"No checkpoint for {agent_role}")
        return {
            "agent_role": agent_role,
            "checkpoint": checkpoint,
            "retrieved_at": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anomalies/{agent_role}")
async def get_recent_anomalies(agent_role: str, limit: int = 10):
    if not redis_client:
        return {"message": "Redis unavailable", "anomalies": []}
    try:
        queue_key = f"neurosentinel:anomaly_queue:{agent_role}"
        raw = redis_client.lrange(queue_key, 0, limit - 1)
        parsed = []
        for item in raw:
            try:
                parsed.append(json.loads(item))
            except Exception:
                pass
        return {"agent_role": agent_role, "count": len(parsed), "anomalies": parsed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SYSTEM EVENT LOOPS ---
@app.on_event("startup")
async def startup_event():
    logger.info("🛫 NeuroSentinel starting...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛬 NeuroSentinel shutting down...")
    if redis_client:
        redis_client.close()

@app.on_event("startup")
async def list_routes():
    logger.info("📋 === REGISTERED ENDPOINTS ===")
    for route in sorted(app.routes, key=lambda r: r.path):
        if hasattr(route, "path") and hasattr(route, "methods"):
            logger.info(f"   {list(route.methods)} -> {route.path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")