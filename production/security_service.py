import os
import re
import json
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS
from core.semantic import SemanticDriftDetector
from core.keyword_detector import keyword_detector
from core.quarantine import SANITIZED_QUARANTINE_RESPONSE, redact_sensitive_info
from core.gnn.detector import GNNPropagationDetector

import platform
import psutil

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("NeuroSentinel-Service")

# ─────────────────────────────────────────────────────────────
# FORCE CLOUD_MODE OFF
# ─────────────────────────────────────────────────────────────
os.environ["CLOUD_MODE"] = "false"
logger.info("[CONFIG] FORCED: CLOUD_MODE = false (overriding RENDER)")

# ─────────────────────────────────────────────────────────────
# CHECK GROQ API KEY
# ─────────────────────────────────────────────────────────────
# Characters of agent output used for scoring. The structural autoencoder was
# trained on short outputs, so long LLM replies are scored on their opening only.
SCORING_MAX_CHARS = int(os.getenv("SCORING_MAX_CHARS", "400"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
if GROQ_API_KEY:
    logger.info("[CONFIG] GROQ_API_KEY configured: yes")
else:
    logger.info("[CONFIG] GROQ_API_KEY configured: no")

# ─────────────────────────────────────────────────────────────
# VALID AGENT ROLES
# ─────────────────────────────────────────────────────────────
VALID_AGENT_ROLES = {"Researcher", "Analyst", "Reporter"}

def validate_agent_role(agent_role: str):
    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent role '{agent_role}'. Must be one of: {', '.join(VALID_AGENT_ROLES)}"
        )

# ─────────────────────────────────────────────────────────────
# FASTAPI APP & LIFESPAN
# ─────────────────────────────────────────────────────────────
settings = SystemSettings()

# ─────────────────────────────────────────────────────────────
# REDIS CONNECTION (INITIALIZED BEFORE LIFESPAN)
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "").strip()
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() in ("1", "true", "yes")

try:
    if REDIS_URL and REDIS_URL != "":
        redis_client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5
        )
    else:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            ssl=REDIS_SSL,
            decode_responses=True,
            socket_connect_timeout=5
        )
    redis_client.ping()
    logger.info(f"✅ Redis connected: {REDIS_URL if REDIS_URL else f'{REDIS_HOST}:{REDIS_PORT}'}")
except Exception as e:
    logger.warning(f"⚠️ Redis unavailable ({e}). Falling back to in-memory storage.")
    redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 NeuroSentinel Security Service starting...")
    logger.info(f"📍 Target Model: {settings.TARGET_MODEL}")
    logger.info(f"📍 Redis: {'connected' if redis_client else 'in-memory fallback'}")
    logger.info(f"📍 Platform: {platform.system()} {platform.release()}")
    logger.info(f"📍 Python: {platform.python_version()}")
    yield
    logger.info("🛑 NeuroSentinel Security Service shutting down...")
    if redis_client:
        try:
            redis_client.close()
        except Exception:
            pass

app = FastAPI(
    title="NeuroSentinel Security Service",
    description="Dual-Layer Detection: Structural Fingerprinting + Semantic Drift",
    version="2.0.0",
    lifespan=lifespan
)

cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if cors_origins_env:
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    allowed_origins = [
        "https://neurosentinel.vercel.app",
        "https://neuro-sentinel.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# PYDANTIC MODELS
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
        default="groq",
        description="LLM backend: groq, ollama, openai, claude, custom"
    )
    custom_endpoint: Optional[str] = Field(
        default=None,
        description="Custom LLM endpoint URL (if llm_provider=custom)"
    )

    @field_validator('agent_role')
    @classmethod
    def validate_agent_role_field(cls, v):
        if v not in VALID_AGENT_ROLES:
            raise ValueError(f"Agent role must be one of: {', '.join(VALID_AGENT_ROLES)}")
        return v

class DetectionResult(BaseModel):
    request_id: str
    timestamp: str
    agent_role: str

    structural_score: float = Field(description="LSTM Autoencoder MSE")
    structural_threshold: float
    structural_status: str = Field(description="PASS, ALERT or SKIPPED")

    semantic_drift: float = Field(description="1.0 - Cosine Similarity")
    semantic_threshold: float
    semantic_status: str = Field(description="PASS, ALERT or SKIPPED")

    overall_status: str = Field(description="CLEAN, SUSPICIOUS, QUARANTINED or UNSCORED")
    confidence: float = Field(description="0.0-1.0")

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

# ─────────────────────────────────────────────────────────────
# SECURITY ENGINE
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
        try:
            self.pipeline = IndustrialPipeline(settings=settings)
            logger.info("✅ IndustrialPipeline initialized with DetectionEnsemble")
        except Exception as e:
            logger.error(f"❌ Failed to initialize IndustrialPipeline: {e}")
            raise

        self.request_count = 0
        self.initialized = True
        logger.info("✅ Security Engine initialized")

    async def detect(self, req: DetectionRequest) -> DetectionResult:
        request_id = f"req_{int(time.time() * 1000)}"
        self.request_count += 1

        validate_agent_role(req.agent_role)
        start_time = time.perf_counter()

        try:
            node = self.pipeline.nodes.get(req.agent_role)
            if node is None:
                from core.engine import AgentNode
                node = AgentNode(req.agent_role, f"Process input for {req.agent_role}")
                self.pipeline.nodes[req.agent_role] = node
                logger.info(f"🆕 Created new agent node: {req.agent_role}")

            # ── 1. Pre-execution Prompt Inspection ──
            kw_prompt = keyword_detector.detect(req.user_input)
            has_high_prompt_injection = any(m.get("level") == "high" for m in kw_prompt.get("matches", []))

            # ── 2. LLM Inference Execution ──
            inf_res = self.pipeline._execute_inference(node, req.user_input, requested_provider=req.llm_provider)
            agent_output = inf_res.output
            exec_time = inf_res.latency
            inf_meta = inf_res.metadata

            # If no real model answered (canned fallback text or an empty reply),
            # there is nothing genuine to score. Never report such a request as CLEAN.
            degraded = inf_meta.get("actual_provider") == "fallback" or not (agent_output or "").strip()
            if degraded:
                return await self._finish_degraded(
                    req, request_id, kw_prompt, has_high_prompt_injection,
                    inf_meta, exec_time, start_time
                )
            scored_output = agent_output[:SCORING_MAX_CHARS]

            # ── 3. Feature Extraction on Generated Output ──
            try:
                telemetry = self.pipeline.tap.extract_features(
                    session_id=request_id,
                    sender=req.agent_role,
                    receiver="Client",
                    payload=scored_output,
                    execution_time=min(exec_time, 2.0)
                )
                m = telemetry["metrics"]
                features = [m["length"], m["word_count"], m["entropy"], m["execution_time"]]
            except Exception as e:
                logger.warning(f"⚠️ Feature extraction fallback: {e}")
                features = [len(scored_output), len(scored_output.split()), 4.0, min(exec_time, 2.0)]

            # ── 4. Unified Detection Ensemble ──
            ens_res = self.pipeline.ensemble.detect(scored_output, req.agent_role, features)

            structural_score = ens_res["structural_score"]
            structural_threshold = ens_res["structural_limit"]
            structural_status = ens_res["structural_status"]

            semantic_drift = ens_res["semantic_drift"]
            semantic_threshold = ens_res["semantic_limit"]
            semantic_status = ens_res["semantic_status"]

            # ── 5. Decision Policy ──
            if has_high_prompt_injection or ens_res["overall_status"] == "QUARANTINED":
                overall_status = "QUARANTINED"
            elif kw_prompt["is_suspicious"] or ens_res["overall_status"] == "SUSPICIOUS":
                overall_status = "SUSPICIOUS"
            else:
                overall_status = "CLEAN"

            confidence = ens_res["confidence"]

            # ── 6. Critical Quarantine Enforcement ──
            checkpoint_id = None
            if overall_status == "QUARANTINED":
                logger.warning(f"Agent {req.agent_role} output QUARANTINED - suppressing unapproved content")
                # Report which checkpoint a rollback would use, but never return
                # that older request's text as this response.
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval notice: {e}")
                delivered_output = SANITIZED_QUARANTINE_RESPONSE
            else:
                # Save clean checkpoints only (degraded requests returned earlier).
                if overall_status == "CLEAN":
                    try:
                        telemetry_to_save = dict(m) if "m" in locals() else {}
                        telemetry_to_save["semantic_drift"] = float(semantic_drift)
                        checkpoint_id = self.pipeline.checkpoints.save(
                            agent_id=req.agent_role,
                            input_text=req.user_input,
                            output_text=agent_output,
                            telemetry=telemetry_to_save,
                            mse=structural_score
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save clean checkpoint: {e}")
                delivered_output = agent_output[:1000]

            elapsed_time = (time.perf_counter() - start_time) * 1000
            is_cloud = os.getenv("CLOUD_MODE", "false").lower() == "true"

            result = DetectionResult(
                request_id=request_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent_role=req.agent_role,
                structural_score=float(structural_score),
                structural_threshold=float(structural_threshold),
                structural_status=structural_status,
                semantic_drift=float(semantic_drift),
                semantic_threshold=float(semantic_threshold),
                semantic_status=semantic_status,
                overall_status=overall_status,
                confidence=float(confidence),
                agent_output=delivered_output,
                execution_time_ms=float(elapsed_time),
                checkpoint_id=checkpoint_id,
                metadata={
                    "features": features,
                    "requested_provider": inf_meta.get("requested_provider", req.llm_provider),
                    "actual_provider": inf_meta.get("actual_provider", "fallback"),
                    "fallback_used": inf_meta.get("fallback_used", False),
                    "inference_status": inf_meta.get("inference_status", "success"),
                    "llm_execution_ms": float(exec_time * 1000),
                    "cloud_mode": is_cloud,
                    "keyword_hit": kw_prompt["is_suspicious"],
                    "output_sanitized": overall_status == "QUARANTINED",
                    "quarantined": overall_status == "QUARANTINED",
                    "llm_error": inf_meta.get("error"),
                    "alerts_count": ens_res["alerts_count"],
                    "marginal": ens_res.get("marginal", False),
                    "semantic_backend": ens_res.get("semantic_backend"),
                    "alert_signals": ens_res.get("alert_signals"),
                    "scored_chars": len(scored_output)
                }
            )

            # Persist and queue with redacted content
            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)

            if redis_client:
                await self._persist_detection(result)

            return result

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            logger.error(f"🚨 Detection pipeline failure: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Internal detection service failure")

    async def _finish_degraded(self, req, request_id, kw_prompt, high_injection,
                               inf_meta, exec_time, start_time):
        """Result for requests where no real LLM output exists.

        Only input-side signals (prompt keywords) are used. The structural and
        semantic layers are skipped, and nothing is saved as a checkpoint.
        """
        if high_injection:
            overall_status = "QUARANTINED"
            delivered_output = SANITIZED_QUARANTINE_RESPONSE
            confidence = 0.80
        elif kw_prompt["is_suspicious"]:
            overall_status = "SUSPICIOUS"
            delivered_output = "[LLM unavailable: output not generated or scored]"
            confidence = 0.50
        else:
            overall_status = "UNSCORED"
            delivered_output = "[LLM unavailable: output not generated or scored]"
            confidence = 0.0

        result = DetectionResult(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_role=req.agent_role,
            structural_score=0.0,
            structural_threshold=float(THRESHOLDS.get(req.agent_role, 0.05)),
            structural_status="SKIPPED",
            semantic_drift=0.0,
            semantic_threshold=float(SEMANTIC_DRIFT_LIMITS.get(req.agent_role, 0.6)),
            semantic_status="SKIPPED",
            overall_status=overall_status,
            confidence=confidence,
            agent_output=delivered_output,
            execution_time_ms=float((time.perf_counter() - start_time) * 1000),
            checkpoint_id=None,
            metadata={
                "features": [],
                "requested_provider": inf_meta.get("requested_provider", req.llm_provider),
                "actual_provider": inf_meta.get("actual_provider", "fallback"),
                "fallback_used": True,
                "inference_status": "degraded",
                "llm_execution_ms": float(exec_time * 1000),
                "keyword_hit": kw_prompt["is_suspicious"],
                "output_sanitized": overall_status == "QUARANTINED",
                "quarantined": overall_status == "QUARANTINED",
                "llm_error": inf_meta.get("error"),
                "alerts_count": 0,
                "degraded": True,
            },
        )
        logger.warning(f"Degraded detection ({overall_status}): {inf_meta.get('error')}")
        if overall_status != "UNSCORED":
            await self._queue_anomaly_event(result, req.user_input)
        if redis_client:
            await self._persist_detection(result)
        return result

    async def _queue_anomaly_event(self, result: DetectionResult, user_input: str):
        try:
            safe_input = redact_sensitive_info(user_input)
            event = AnomalyEvent(
                event_id=result.request_id,
                timestamp=result.timestamp,
                agent_role=result.agent_role,
                structural_score=result.structural_score,
                semantic_drift=result.semantic_drift,
                user_input=safe_input,
                detection_result=redact_sensitive_info(result.model_dump())
            )

            if redis_client:
                queue_key = f"neurosentin_l:anomaly_queue:{result.agent_role}"
                redis_client.lpush(queue_key, event.to_json())
                redis_client.expire(queue_key, 86400)
                logger.info(f"✅ Anomaly logged in queue: {result.request_id}")
        except Exception as e:
            logger.warning(f"Failed to queue anomaly event: {e}")

    async def _persist_detection(self, result: DetectionResult):
        try:
            key = f"neurosentin_l:detection:{result.request_id}"
            redis_client.set(
                key,
                json.dumps(redact_sensitive_info(result.model_dump())),
                ex=86400
            )
        except Exception as e:
            logger.warning(f"Failed to persist detection: {e}")

engine = SecurityEngine()

# ─────────────────────────────────────────────────────────────
# METRICS COLLECTOR
# ─────────────────────────────────────────────────────────────
class MetricsCollector:
    def __init__(self):
        self.start_time = time.time()
        self.total_requests = 0
        self.active_requests = 0
        self.response_times: List[float] = []
        self.minute_request_timestamps: List[float] = []

    def record_request_start(self):
        self.active_requests += 1

    def record_request_end(self, response_time_ms: float):
        self.total_requests += 1
        self.active_requests -= 1
        self.response_times.append(response_time_ms)
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]

        now = time.time()
        self.minute_request_timestamps.append(now)
        cutoff = now - 60.0
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if t > cutoff]

    def get_avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def get_requests_per_minute(self) -> float:
        now = time.time()
        cutoff = now - 60.0
        recent = [t for t in self.minute_request_timestamps if t > cutoff]
        return len(recent)

    def get_uptime_seconds(self) -> float:
        return time.time() - self.start_time

metrics = MetricsCollector()

# ─────────────────────────────────────────────────────────────
# SECURITY & AUTHENTICATION
# ─────────────────────────────────────────────────────────────
MAX_REQUEST_SIZE = 1024 * 1024  # 1 MB
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))

_rate_limit_records: Dict[str, List[float]] = {}
_rate_limit_lock = asyncio.Lock()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_admin_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
):
    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    if admin_key:
        token = api_key
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
        if not token or token != admin_key:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Invalid or missing admin credentials"
            )
    return True

# ─────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────
@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Payload too large: Request size exceeds 1MB limit"}
                )
        except ValueError:
            pass
    return await call_next(request)

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    cutoff = now - 60.0

    async with _rate_limit_lock:
        if len(_rate_limit_records) > 5000:
            for ip in list(_rate_limit_records.keys()):
                _rate_limit_records[ip] = [t for t in _rate_limit_records[ip] if t > cutoff]
                if not _rate_limit_records[ip]:
                    del _rate_limit_records[ip]

        timestamps = _rate_limit_records.get(client_ip, [])
        timestamps = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            _rate_limit_records[client_ip] = timestamps
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute."}
            )
        timestamps.append(now)
        _rate_limit_records[client_ip] = timestamps

    return await call_next(request)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    metrics.record_request_start()
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_request_end(elapsed_ms)

        response.headers["X-Request-ID"] = f"req_{int(time.time() * 1000)}"
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_request_end(elapsed_ms)
        raise

gnn_detector = None

def get_gnn_detector() -> GNNPropagationDetector:
    global gnn_detector
    if gnn_detector is None:
        try:
            gnn_detector = GNNPropagationDetector()
            logger.info("✅ GNN Propagation Detector initialized")
        except Exception as e:
            logger.warning(f"⚠️ GNN not available: {e}")
            gnn_detector = None
    return gnn_detector

# ─────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "NeuroSentinel Security Service v2.0",
        "docs": "/docs"
    }

@app.post("/api/detect", response_model=DetectionResult)
async def detect_anomaly(request: DetectionRequest):
    logger.info(f"📥 Detection request: agent={request.agent_role}, input_len={len(request.user_input)}")
    return await engine.detect(request)

@app.get("/api/health")
async def health_check():
    redis_status = "connected" if redis_client else "unavailable"
    return {
        "status": "healthy",
        "service": "NeuroSentinel Security Service v2.0",
        "redis": redis_status,
        "uptime_requests": engine.request_count,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/thresholds")
async def get_thresholds():
    return {
        "structural_thresholds": THRESHOLDS,
        "semantic_drift_limits": SEMANTIC_DRIFT_LIMITS,
        "note": "Calibrated thresholds from training data"
    }

@app.post("/api/models/reload", dependencies=[Depends(verify_admin_key)])
async def reload_models():
    try:
        engine.pipeline = IndustrialPipeline(settings=settings)
        logger.info("✅ Models reloaded successfully")
        return {"status": "success", "message": "All models reloaded"}
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state/checkpoint/{agent_role}")
async def get_checkpoint(agent_role: str):
    try:
        validate_agent_role(agent_role)

        checkpoint = engine.pipeline.checkpoints.retrieve_safe_checkpoint(agent_role)
        # No checkpoint yet is a normal state, not an error.
        return {
            "agent_role": agent_role,
            "checkpoint": checkpoint or None,
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Checkpoint retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anomalies/{agent_role}")
async def get_recent_anomalies(agent_role: str, limit: int = 10):
    try:
        validate_agent_role(agent_role)

        if not redis_client:
            return {"message": "Redis unavailable", "anomalies": []}

        queue_key = f"neurosentin_l:anomaly_queue:{agent_role}"
        anomalies = redis_client.lrange(queue_key, 0, limit - 1)

        parsed = []
        for anomaly_json in anomalies:
            try:
                parsed.append(json.loads(anomaly_json))
            except:
                pass

        return {
            "agent_role": agent_role,
            "count": len(parsed),
            "anomalies": parsed
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anomaly retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/propagation/status")
async def get_propagation_status():
    try:
        detector = get_gnn_detector()

        if detector is None:
            return {
                "status": "unavailable",
                "message": "GNN detector not initialized"
            }

        agents = []
        for role in ["Researcher", "Analyst", "Reporter"]:
            node = engine.pipeline.nodes.get(role)
            if node:
                agents.append({
                    'id': role,
                    'role': role,
                    'structural_score': 0.05,
                    'semantic_drift': 0.5,
                    'confidence': 0.95
                })

        connections = [
            ("Researcher", "Analyst"),
            ("Analyst", "Reporter"),
            ("Reporter", "Client")
        ]

        result = detector.detect_propagation(agents, connections)

        result['service'] = "NeuroSentinel Security Service v2.0"
        result['detector_threshold'] = detector.threshold
        result['gnn_model_loaded'] = hasattr(detector, 'model') and detector.model is not None

        return result

    except Exception as e:
        logger.error(f"Propagation status check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/metrics", dependencies=[Depends(verify_admin_key)])
async def get_system_metrics():
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        mem = psutil.virtual_memory()
        mem_total_gb = mem.total / (1024 ** 3)
        mem_available_gb = mem.available / (1024 ** 3)
        mem_used_gb = mem.used / (1024 ** 3)

        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_free_gb = disk.free / (1024 ** 3)

        process = psutil.Process()
        process_threads = process.num_threads()
        try:
            process_connections = len(process.net_connections())
        except (AttributeError, Exception):
            process_connections = len(process.connections())
        process_memory_mb = process.memory_info().rss / (1024 ** 2)

        request_metrics = {
            "total_requests": metrics.total_requests,
            "active_requests": metrics.active_requests,
            "requests_per_minute": metrics.get_requests_per_minute(),
            "avg_response_time_ms": round(metrics.get_avg_response_time(), 2)
        }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(metrics.get_uptime_seconds(), 2),
            "service": "NeuroSentinel Security Service v2.0",
            "system": {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
                "cpu_count": cpu_count
            },
            "process": {
                "pid": os.getpid(),
                "thread_count": process_threads,
                "open_connections": process_connections,
                "memory_mb": round(process_memory_mb, 2)
            },
            "cpu": {
                "percent": cpu_percent,
                "cores": cpu_count,
                "frequency_mhz": round(cpu_freq.current, 2) if cpu_freq else None
            },
            "memory": {
                "total_gb": round(mem_total_gb, 2),
                "available_gb": round(mem_available_gb, 2),
                "used_gb": round(mem_used_gb, 2),
                "percent": mem.percent
            },
            "disk": {
                "total_gb": round(disk_total_gb, 2),
                "used_gb": round(disk_used_gb, 2),
                "free_gb": round(disk_free_gb, 2),
                "percent": disk.percent
            },
            "requests": request_metrics,
            "detection_engine": {
                "total_detections": engine.request_count
            }
        }

    except Exception as e:
        logger.error(f"Metrics retrieval failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect system metrics: {str(e)}"
        )

@app.get("/api/config", dependencies=[Depends(verify_admin_key)])
async def get_runtime_config():
    try:
        hf_api_key = bool(os.getenv("HF_API_KEY", ""))
        groq_api_key = bool(os.getenv("GROQ_API_KEY", ""))

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": {
                "name": "NeuroSentinel Security Service",
                "version": "2.0.0",
                "description": "Dual-Layer Detection: Structural Fingerprinting + Semantic Drift"
            },
            "detection_thresholds": {
                "structural": {
                    "values": THRESHOLDS,
                    "default": 0.05,
                    "note": "LSTM Autoencoder MSE threshold per agent role"
                },
                "semantic_drift": {
                    "values": SEMANTIC_DRIFT_LIMITS,
                    "default": 0.75,
                    "note": "1.0 - Cosine Similarity limit per agent role"
                }
            },
            "system_settings": {
                "target_model": settings.TARGET_MODEL,
                "ollama_base_url": settings.OLLAMA_BASE_URL,
                "feature_dimension": settings.FEATURE_DIMENSION,
                "sliding_window_size": settings.SLIDING_WINDOW_SIZE,
                "redis_host": REDIS_HOST,
                "redis_port": REDIS_PORT
            },
            "feature_flags": {
                "redis_enabled": redis_client is not None,
                "gnn_detector_available": gnn_detector is not None,
                "huggingface_api_available": hf_api_key,
                "groq_api_available": groq_api_key,
                "checkpoint_system_enabled": True,
                "quarantine_engine_enabled": True,
                "anomaly_event_queue_enabled": redis_client is not None
            },
            "runtime_state": {
                "uptime_seconds": round(metrics.get_uptime_seconds(), 2),
                "total_detections": engine.request_count,
                "active_requests": metrics.active_requests,
                "total_api_requests": metrics.total_requests,
                "requests_per_minute": metrics.get_requests_per_minute(),
                "avg_response_time_ms": round(metrics.get_avg_response_time(), 2)
            }
        }

    except Exception as e:
        logger.error(f"Config retrieval failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve runtime configuration: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
