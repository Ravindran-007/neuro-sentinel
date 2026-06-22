"""
FastAPI Security Service — NeuroSentinel Lite (Level 2 Deployable)
Transforms Phase 1-3 detection logic into production-grade REST endpoints
Fixed: compute_drift → calculate_drift (matches core/engine.py)
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
VALID_AGENT_ROLES = {"Researcher", "Analyst", "Reporter"}

def validate_agent_role(agent_role: str):
    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent role '{agent_role}'. "
                   f"Must be one of: {', '.join(VALID_AGENT_ROLES)}"
        )

# ─────────────────────────────────────────────────────────────
# LOGGING & CONFIGURATION
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("NeuroSentinel-Service")

settings = SystemSettings()
app = FastAPI(
    title="NeuroSentinel Security Service",
    description="Dual-Layer Detection: Structural Fingerprinting + Semantic Drift",
    version="2.0.0"
)

# ─────────────────────────────────────────────────────────────
# REDIS BACKEND
# ─────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))
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
    logger.info(f"✅ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"⚠️ Redis unavailable ({e}). Using in-memory fallback.")
    redis_client = None

# ─────────────────────────────────────────────────────────────
# REQUEST / RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────
class DetectionRequest(BaseModel):
    agent_role: str = Field(
        ...,
        description="Target agent: Researcher, Analyst, or Reporter"
    )
    user_input: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Input prompt to analyze"
    )
    llm_provider: str = Field(
        default="ollama",
        description="LLM backend: ollama, openai, claude, custom"
    )
    custom_endpoint: Optional[str] = Field(
        default=None,
        description="Custom LLM endpoint URL"
    )

    @validator('agent_role')
    def validate_role(cls, v):
        if v not in VALID_AGENT_ROLES:
            raise ValueError(
                f"Agent role must be one of: {', '.join(VALID_AGENT_ROLES)}"
            )
        return v


class DetectionResult(BaseModel):
    request_id:           str
    timestamp:            str
    agent_role:           str
    structural_score:     float
    structural_threshold: float
    structural_status:    str
    semantic_drift:       float
    semantic_threshold:   float
    semantic_status:      str
    overall_status:       str
    confidence:           float
    agent_output:         str
    execution_time_ms:    float
    checkpoint_id:        Optional[str] = None
    metadata:             Dict[str, Any] = {}


@dataclass
class AnomalyEvent:
    event_id:         str
    timestamp:        str
    agent_role:       str
    structural_score: float
    semantic_drift:   float
    user_input:       str
    detection_result: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self))


# ─────────────────────────────────────────────────────────────
# CORE DETECTION ENGINE
# ─────────────────────────────────────────────────────────────
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
        self.pipeline      = IndustrialPipeline(settings=settings)
        self.request_count = 0
        self.initialized   = True
        logger.info("✅ Security Engine initialized")

    async def detect(self, req: DetectionRequest) -> DetectionResult:
        """Execute dual-layer detection pipeline."""
        request_id = f"req_{int(time.time() * 1000)}"
        self.request_count += 1

        validate_agent_role(req.agent_role)

        start_time = time.perf_counter()
        is_cloud   = os.getenv("RENDER", "false").lower() == "true"

        try:
            node = self.pipeline.nodes[req.agent_role]

            # ── LLM Inference ────────────────────────────────
            if is_cloud:
                logger.info("☁️ Cloud mode: Skipping Ollama inference")
                agent_output = (
                    f"[Cloud Mode] Analyzed input: {req.user_input[:100]}..."
                )
                exec_time = 0.1
            else:
                agent_output, exec_time = self.pipeline._execute_inference(
                    node, req.user_input
                )

            # ── Layer 1: Structural Analysis ─────────────────
            telemetry = self.pipeline.tap.extract_features(
                session_id     = request_id,
                sender         = req.agent_role,
                receiver       = "SecurityService",
                payload        = agent_output,
                execution_time = exec_time
            )
            m        = telemetry["metrics"]
            features = [
                m["length"],
                m["word_count"],
                m["entropy"],
                m["execution_time"]
            ]

            structural_score     = self.pipeline._score_agent_structure(
                req.agent_role, features
            )
            structural_threshold = THRESHOLDS[req.agent_role]
            structural_status    = (
                "PASS" if structural_score <= structural_threshold else "ALERT"
            )

            # ── Layer 2: Semantic Drift ───────────────────────
            # ✅ FIXED: calculate_drift (matches core/engine.py)
            semantic_drift     = self.pipeline.semantic_detector.calculate_drift(
                req.agent_role, agent_output
            )
            semantic_threshold = SEMANTIC_DRIFT_LIMITS[req.agent_role]
            semantic_status    = (
                "PASS" if semantic_drift <= semantic_threshold else "ALERT"
            )

            # ── Overall Decision ─────────────────────────────
            if structural_status == "ALERT" or semantic_status == "ALERT":
                overall_status = "SUSPICIOUS"
            else:
                overall_status = "CLEAN"

            confidence = 1.0 - (
                structural_score / (structural_threshold + 1e-5)
            )
            confidence = max(0.0, min(1.0, confidence))

            # ── Checkpoint rollback if compromised ───────────
            checkpoint_id = None
            if overall_status == "SUSPICIOUS":
                try:
                    checkpoint_data = (
                        self.pipeline.checkpoints
                        .retrieve_safe_checkpoint(req.agent_role)
                    )
                    if checkpoint_data:
                        checkpoint_id  = checkpoint_data.get("id")
                        overall_status = "QUARANTINED"
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval failed: {e}")

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            result = DetectionResult(
                request_id           = request_id,
                timestamp            = datetime.utcnow().isoformat(),
                agent_role           = req.agent_role,
                structural_score     = float(structural_score),
                structural_threshold = float(structural_threshold),
                structural_status    = structural_status,
                semantic_drift       = float(semantic_drift),
                semantic_threshold   = float(semantic_threshold),
                semantic_status      = semantic_status,
                overall_status       = overall_status,
                confidence           = float(confidence),
                agent_output         = (agent_output or "No output")[:1000],
                execution_time_ms    = float(elapsed_ms),
                checkpoint_id        = checkpoint_id,
                metadata             = {
                    "features":         features,
                    "llm_provider":     req.llm_provider,
                    "llm_execution_ms": float(exec_time * 1000),
                    "cloud_mode":       is_cloud
                }
            )

            # Queue anomaly event
            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)

            # Persist to Redis
            if redis_client:
                await self._persist_detection(result)

            return result

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Detection pipeline failed: {e}\n{error_details}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _queue_anomaly_event(
        self, result: DetectionResult, user_input: str
    ):
        try:
            event = AnomalyEvent(
                event_id         = result.request_id,
                timestamp        = result.timestamp,
                agent_role       = result.agent_role,
                structural_score = result.structural_score,
                semantic_drift   = result.semantic_drift,
                user_input       = user_input,
                detection_result = result.dict()
            )
            if redis_client:
                queue_key = (
                    f"neurosentin_l:anomaly_queue:{result.agent_role}"
                )
                redis_client.lpush(queue_key, event.to_json())
                redis_client.expire(queue_key, 86400)
                logger.info(f"✅ Anomaly queued: {result.request_id}")
        except Exception as e:
            logger.warning(f"Failed to queue anomaly: {e}")

    async def _persist_detection(self, result: DetectionResult):
        try:
            key = f"neurosentin_l:detection:{result.request_id}"
            redis_client.set(key, json.dumps(result.dict()), ex=86400)
        except Exception as e:
            logger.warning(f"Failed to persist detection: {e}")


# Initialize engine singleton
engine = SecurityEngine()

# ─────────────────────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.post("/api/detect", response_model=DetectionResult)
async def detect_anomaly(request: DetectionRequest):
    """
    Main detection endpoint — dual-layer structural + semantic analysis.

    Returns:
    - **CLEAN**: Both layers passed
    - **SUSPICIOUS**: One or both layers triggered
    - **QUARANTINED**: Checkpoint rollback initiated
    """
    logger.info(
        f"📥 Detection request: agent={request.agent_role}, "
        f"input_len={len(request.user_input)}"
    )
    return await engine.detect(request)


@app.get("/api/health")
async def health_check():
    """Liveness and readiness probe."""
    redis_status = "connected" if redis_client else "unavailable"
    return {
        "status":           "healthy",
        "service":          "NeuroSentinel Security Service v2.0",
        "redis":            redis_status,
        "uptime_requests":  engine.request_count,
        "timestamp":        datetime.utcnow().isoformat()
    }


@app.get("/api/thresholds")
async def get_thresholds():
    """Return calibrated per-agent detection thresholds."""
    return {
        "structural_thresholds": THRESHOLDS,
        "semantic_drift_limits": SEMANTIC_DRIFT_LIMITS,
        "note": (
            "Analyst has tightest structural threshold (0.000804) "
            "due to rigid deterministic processing"
        )
    }


@app.post("/api/models/reload")
async def reload_models():
    """Hot-reload trained autoencoder models from disk."""
    try:
        engine.pipeline = IndustrialPipeline(settings=settings)
        logger.info("✅ Models reloaded")
        return {"status": "success", "message": "All models reloaded"}
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/state/checkpoint/{agent_role}")
async def get_checkpoint(agent_role: str):
    """Retrieve latest safe checkpoint for an agent."""
    validate_agent_role(agent_role)
    try:
        checkpoint = (
            engine.pipeline.checkpoints
            .retrieve_safe_checkpoint(agent_role)
        )
        if not checkpoint:
            raise HTTPException(
                status_code=404,
                detail=f"No checkpoint for {agent_role}"
            )
        return {
            "agent_role":   agent_role,
            "checkpoint":   checkpoint,
            "retrieved_at": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Checkpoint retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anomalies/{agent_role}")
async def get_recent_anomalies(agent_role: str, limit: int = 10):
    """Fetch recent anomaly events from Redis queue."""
    validate_agent_role(agent_role)
    if not redis_client:
        return {"message": "Redis unavailable", "anomalies": []}
    try:
        queue_key = f"neurosentin_l:anomaly_queue:{agent_role}"
        raw       = redis_client.lrange(queue_key, 0, limit - 1)
        parsed    = []
        for item in raw:
            try:
                parsed.append(json.loads(item))
            except Exception:
                pass
        return {
            "agent_role": agent_role,
            "count":      len(parsed),
            "anomalies":  parsed
        }
    except Exception as e:
        logger.error(f"Anomaly retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 NeuroSentinel Security Service starting...")
    logger.info(f"📍 Target Model : {settings.TARGET_MODEL}")
    logger.info(f"📍 Redis        : {REDIS_HOST}:{REDIS_PORT}")
    is_cloud = os.getenv("RENDER", "false").lower() == "true"
    if is_cloud:
        logger.info("☁️ RENDER cloud mode — Ollama will be skipped")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 NeuroSentinel Security Service shutting down...")
    if redis_client:
        try:
            redis_client.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")