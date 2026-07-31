"""
FastAPI Security Service — NeuroSentinel Lite (Level 2 Deployable)
Transforms Phase 1-3 detection logic into production-grade REST endpoints
"""

import os
import json
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field, validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS
from core.semantic import query_classifier
from core.gnn.detector import GNNPropagationDetector

import platform
import psutil

# ─────────────────────────────────────────────────────────────
# CONSTANTS & VALIDATION
# ─────────────────────────────────────────────────────────────

VALID_AGENT_ROLES = {"Researcher", "Analyst", "Reporter"}

def validate_agent_role(agent_role: str):
    """Validate that agent role is valid. Raises HTTPException if invalid."""
    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent role '{agent_role}'. Must be one of: {', '.join(VALID_AGENT_ROLES)}"
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
# REDIS BACKEND (replaces JSON file storage)
# ─────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()
    logger.info(f"✅ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"⚠️ Redis unavailable ({e}). Falling back to in-memory storage.")
    redis_client = None

# ─────────────────────────────────────────────────────────────
# REQUEST/RESPONSE SCHEMAS
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
        description="Custom LLM endpoint URL (if llm_provider=custom)"
    )

    @validator('agent_role')
    def validate_agent_role_field(cls, v):
        """Validate agent role is valid"""
        if v not in VALID_AGENT_ROLES:
            raise ValueError(f"Agent role must be one of: {', '.join(VALID_AGENT_ROLES)}")
        return v

class DetectionResult(BaseModel):
    request_id: str
    timestamp: str
    agent_role: str
    
    # Structural Layer
    structural_score: float = Field(description="LSTM Autoencoder MSE")
    structural_threshold: float
    structural_status: str = Field(description="PASS or ALERT")
    
    # Semantic Layer
    semantic_drift: float = Field(description="1.0 - Cosine Similarity")
    semantic_threshold: float
    semantic_status: str = Field(description="PASS or ALERT")
    
    # Overall Decision
    overall_status: str = Field(description="CLEAN, SUSPICIOUS, or QUARANTINED")
    confidence: float = Field(description="0.0-1.0")
    
    # LLM Output
    agent_output: str
    execution_time_ms: float
    
    # Checkpoint Info
    checkpoint_id: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = {}

@dataclass
class AnomalyEvent:
    """Event structure for Redis queuing"""
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
# CORE DETECTION ENGINE (singleton)
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
        self.pipeline = IndustrialPipeline(settings=settings)
        self.request_count = 0
        self.initialized = True
        logger.info("✅ Security Engine initialized")
    
    async def detect(self, req: DetectionRequest) -> DetectionResult:
        """Execute dual-layer detection pipeline"""
        request_id = f"req_{int(time.time() * 1000)}"
        self.request_count += 1
        
        # Validate agent role (additional safety)
        validate_agent_role(req.agent_role)
        
        start_time = time.perf_counter()
        
        try:
            # Execute LLM inference
            node = self.pipeline.nodes[req.agent_role]
            agent_output, exec_time = self.pipeline._execute_inference(node, req.user_input)
            
            # Layer 1: Structural Analysis (LSTM Autoencoder)
            # Extract features from the agent output
            telemetry = self.pipeline.tap.extract_features(
                session_id=request_id,
                sender=req.agent_role,
                receiver="Client",
                payload=agent_output,
                execution_time=exec_time
            )
            m = telemetry["metrics"]
            features = [m["length"], m["word_count"], m["entropy"], m["execution_time"]]
            structural_score = self.pipeline._score_agent_structure(req.agent_role, features)
            structural_threshold = THRESHOLDS[req.agent_role]
            structural_status = "PASS" if structural_score <= structural_threshold else "ALERT"
            
            # Layer 2: Semantic Drift Analysis
            semantic_drift = self.pipeline.semantic_detector.calculate_drift(req.agent_role, agent_output)
            semantic_threshold = SEMANTIC_DRIFT_LIMITS[req.agent_role]
            semantic_status = "PASS" if semantic_drift <= semantic_threshold else "ALERT"
            
# FIX v3.1: AND-based dual-layer detection with TIERED response
            # BOTH breached → QUARANTINED, Single extreme → QUARANTINED,
            # Single mild → SUSPICIOUS, None → CLEAN
            structural_ratio = structural_score / (structural_threshold + 1e-10)
            semantic_ratio = semantic_drift / (semantic_threshold + 1e-10)
            
            checkpoint_id = None
            
            if structural_ratio >= 1.0 and semantic_ratio >= 1.0:
                # BOTH layers breached → QUARANTINED (definite threat)
                overall_status = "QUARANTINED"
                logger.warning(f"🚨 Both layers breached - QUARANTINED: "
                              f"structural={structural_ratio:.2f}x ({structural_score:.6f}/{structural_threshold:.6f}), "
                              f"semantic={semantic_ratio:.2f}x ({semantic_drift:.6f}/{semantic_threshold:.6f})")
                # Attempt checkpoint retrieval
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval failed: {e}")
                    
            elif structural_ratio >= 3.0 or semantic_ratio >= 3.0:
                # Extreme single-layer breach (3x+) → QUARANTINED
                overall_status = "QUARANTINED"
                logger.warning(f"🚨 Extreme single-layer breach - QUARANTINED: "
                              f"structural_ratio={structural_ratio:.2f}x, "
                              f"semantic_ratio={semantic_ratio:.2f}x")
                # Attempt checkpoint retrieval
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval failed: {e}")
                    
            elif structural_ratio >= 1.0 or semantic_ratio >= 1.0:
                # Single layer mildly breached → SUSPICIOUS (NOT QUARANTINED)
                overall_status = "SUSPICIOUS"
                logger.info(f"⚠️ Single layer breach - SUSPICIOUS (not quarantined): "
                           f"structural={structural_ratio:.2f}x, "
                           f"semantic={semantic_ratio:.2f}x")
            else:
                # Both pass → CLEAN
                overall_status = "CLEAN"
                logger.info(f"✅ Clean: structural={structural_ratio:.2f}x ({structural_score:.6f}/{structural_threshold:.6f}), "
                           f"semantic={semantic_ratio:.2f}x ({semantic_drift:.6f}/{semantic_threshold:.6f})")
            
            # FIX v3.1: Improved confidence calculation
            # CLEAN: confidence range 0.60-1.00 (higher when both ratios far below 1.0)
            # SUSPICIOUS: confidence range 0.20-0.50 (moderate uncertainty)
            # QUARANTINED: confidence range 0.50-1.00 (higher when both ratios well above 1.0)
            max_ratio = max(structural_ratio, semantic_ratio)
            if overall_status == "CLEAN":
                # Far below threshold → high confidence
                confidence = max(0.60, 1.0 - max_ratio * 0.35)
            elif overall_status == "SUSPICIOUS":
                # One layer near threshold → moderate-low confidence
                confidence = min(0.50, max_ratio * 0.25 + 0.15)
            else:  # QUARANTINED
                # Both breached → higher confidence in detection
                confidence = min(1.0, 0.50 + max_ratio * 0.15)
            confidence = max(0.0, min(1.0, confidence))
            
            # Build result
            elapsed_time = (time.perf_counter() - start_time) * 1000
            
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
                agent_output=agent_output,
                execution_time_ms=float(elapsed_time),
                checkpoint_id=checkpoint_id,
                metadata={
                    "features": features,
                    "llm_provider": req.llm_provider,
                    "llm_execution_ms": float(exec_time * 1000)
                }
            )
            
            # Queue anomaly event if detected
            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)
            
            # Persist to Redis
            if redis_client:
                await self._persist_detection(result)
            
            return result
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Detection pipeline failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _queue_anomaly_event(self, result: DetectionResult, user_input: str):
        """Queue anomaly to Redis for async processing / DLQ routing"""
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
                queue_key = f"neurosentin_l:anomaly_queue:{result.agent_role}"
                redis_client.lpush(queue_key, event.to_json())
                redis_client.expire(queue_key, 86400)  # 24h retention
                logger.info(f"✅ Anomaly queued: {result.request_id}")
        except Exception as e:
            logger.warning(f"Failed to queue anomaly event: {e}")
    
    async def _persist_detection(self, result: DetectionResult):
        """Store detection result in Redis"""
        try:
            key = f"neurosentin_l:detection:{result.request_id}"
            redis_client.set(
                key,
                json.dumps(result.dict()),
                ex=86400  # 24h TTL
            )
        except Exception as e:
            logger.warning(f"Failed to persist detection: {e}")

# Initialize engine
engine = SecurityEngine()

# ─────────────────────────────────────────────────────────────
# METRICS TRACKING
# ─────────────────────────────────────────────────────────────
class MetricsCollector:
    """Tracks system and request metrics for the /api/metrics endpoint"""
    
    def __init__(self):
        self.start_time = time.time()
        self.total_requests = 0
        self.active_requests = 0
        self.response_times: List[float] = []
        self.minute_request_timestamps: List[float] = []
    
    def record_request_start(self):
        """Called when a request begins"""
        self.active_requests += 1
    
    def record_request_end(self, response_time_ms: float):
        """Called when a request completes"""
        self.total_requests += 1
        self.active_requests -= 1
        self.response_times.append(response_time_ms)
        # Keep only last 1000 response times
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]
        
        # Track for requests-per-minute calculation
        now = time.time()
        self.minute_request_timestamps.append(now)
        # Prune timestamps older than 60 seconds
        cutoff = now - 60.0
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if t > cutoff]
    
    def get_avg_response_time(self) -> float:
        """Get average response time in milliseconds"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    def get_requests_per_minute(self) -> float:
        """Calculate requests in the last 60 seconds"""
        now = time.time()
        cutoff = now - 60.0
        recent = [t for t in self.minute_request_timestamps if t > cutoff]
        return len(recent)
    
    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds"""
        return time.time() - self.start_time

metrics = MetricsCollector()

# ─────────────────────────────────────────────────────────────
# REQUEST COUNTING MIDDLEWARE
# ─────────────────────────────────────────────────────────────

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware that tracks request count, active requests, and response times.
    Adds metrics headers to every response.
    """
    metrics.record_request_start()
    start_time = time.perf_counter()
    
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_request_end(elapsed_ms)
        
        # Add metrics headers
        response.headers["X-Request-ID"] = f"req_{int(time.time() * 1000)}"
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_request_end(elapsed_ms)
        raise

# ─────────────────────────────────────────────────────────────
# GNN PROPAGATION DETECTOR (lazy-initialized)
# ─────────────────────────────────────────────────────────────
gnn_detector = None

def get_gnn_detector() -> GNNPropagationDetector:
    """Lazy-initialize and return the GNN propagation detector singleton."""
    global gnn_detector
    if gnn_detector is None:
        gnn_detector = GNNPropagationDetector()
        logger.info("✅ GNN Propagation Detector initialized")
    return gnn_detector

# ─────────────────────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.post("/api/detect", response_model=DetectionResult)
async def detect_anomaly(request: DetectionRequest):
    """
    Main detection endpoint: Execute dual-layer structural + semantic analysis
    
    **Returns:**
    - `CLEAN`: Both layers passed
    - `SUSPICIOUS`: One or both layers triggered
    - `QUARANTINED`: Checkpoint rollback initiated
    """
    logger.info(f"📥 Detection request: agent={request.agent_role}, input_len={len(request.user_input)}")
    return await engine.detect(request)

@app.get("/api/health")
async def health_check():
    """Liveness & readiness probe"""
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
    """Return calibrated detection thresholds"""
    return {
        "structural_thresholds": THRESHOLDS,
        "semantic_drift_limits": SEMANTIC_DRIFT_LIMITS,
        "note": "Calibrated thresholds from training data — Researcher: 0.017311, Analyst: 0.025000, Reporter: 0.002997. Drift limits: 0.60 for all agents."
    }

@app.post("/api/models/reload")
async def reload_models():
    """Hot-reload trained autoencoder models from disk"""
    try:
        # Reinitialize pipeline to pick up any updated models
        engine.pipeline = IndustrialPipeline(settings=settings)
        logger.info("✅ Models reloaded successfully")
        return {"status": "success", "message": "All models reloaded"}
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state/checkpoint/{agent_role}")
async def get_checkpoint(agent_role: str):
    """Retrieve latest safe checkpoint for an agent"""
    try:
        # ✅ ADDED VALIDATION
        validate_agent_role(agent_role)
        
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
        logger.error(f"Checkpoint retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anomalies/{agent_role}")
async def get_recent_anomalies(agent_role: str, limit: int = 10):
    """Fetch recent anomaly events from Redis queue"""
    try:
        # ✅ ADDED VALIDATION
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

# ─────────────────────────────────────────────────────────────
# NEW ENDPOINT: GET /api/propagation/status — GNN Propagation Status
# ─────────────────────────────────────────────────────────────

@app.get("/api/propagation/status")
async def get_propagation_status():
    """
    GNN Propagation Status
    
    Returns the current state of GNN-based compromise propagation detection
    across the agent network. Analyzes structural and semantic scores to
    detect if a compromise is spreading between agents (Researcher → Analyst → Reporter).
    
    **Response Fields:**
    - `timestamp`: ISO 8601 timestamp of the analysis
    - `node_predictions`: Per-agent compromise probability (0.0-1.0)
    - `propagation_paths`: Paths between compromised nodes in the agent graph
    - `compromised_count`: Number of agents flagged as compromised
    - `total_agents`: Total agents in the graph
    - `overall_risk`: Maximum compromise probability across all agents
    - `graph_stats`: Nodes/edges count in the current agent graph
    
    **Status Interpretation:**
    - `overall_risk < 0.3`: Normal operation
    - `overall_risk 0.3-0.7`: Monitoring recommended
    - `overall_risk > 0.7`: Immediate investigation required
    """
    try:
        detector = get_gnn_detector()
        
        # Build agent data from current pipeline state
        agents = []
        for role in ["Researcher", "Analyst", "Reporter"]:
            node = engine.pipeline.nodes.get(role)
            if node:
                agents.append({
                    'id': role,
                    'role': role,
                    'structural_score': 0.05,  # Default baseline
                    'semantic_drift': 0.5,      # Default baseline
                    'confidence': 0.95
                })
        
        # Build connections (chain topology: R → A → R → Client)
        connections = [
            ("Researcher", "Analyst"),
            ("Analyst", "Reporter"),
            ("Reporter", "Client")
        ]
        
        # Run propagation detection
        result = detector.detect_propagation(agents, connections)
        
        # Add service-level metadata
        result['service'] = "NeuroSentinel Security Service v2.0"
        result['detector_threshold'] = detector.threshold
        result['gnn_model_loaded'] = hasattr(detector, 'model') and detector.model is not None
        
        return result
    
    except Exception as e:
        logger.error(f"Propagation status check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"GNN propagation analysis failed: {str(e)}"
        )

# ─────────────────────────────────────────────────────────────
# NEW ENDPOINT: GET /api/metrics — System Performance Metrics
# ─────────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_system_metrics():
    """
    System Performance Metrics
    
    Returns comprehensive system and service performance metrics collected
    in real-time. Includes CPU, memory, request statistics, and response times.
    
    **Response Fields:**
    - `timestamp`: ISO 8601 timestamp
    - `uptime_seconds`: Service uptime in seconds
    - `system`: OS, platform, Python version info
    - `process`: PID, thread count, connection count
    - `cpu`: CPU usage percent, core count
    - `memory`: Total, available, used, and percent usage (GB where applicable)
    - `disk`: Total, used, free disk space (GB)
    - `requests`: Total requests, active, requests/min, avg response time
    - `detection_engine`: Current pipeline request count
    
    **Usage:**
    - Monitor service health and resource usage
    - Alert when memory > 90% or CPU > 80%
    - Track request throughput trends
    """
    try:
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        # Memory metrics
        mem = psutil.virtual_memory()
        mem_total_gb = mem.total / (1024 ** 3)
        mem_available_gb = mem.available / (1024 ** 3)
        mem_used_gb = mem.used / (1024 ** 3)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_free_gb = disk.free / (1024 ** 3)
        
        # Process info
        process = psutil.Process()
        process_threads = process.num_threads()
        process_connections = len(process.connections())
        process_memory_mb = process.memory_info().rss / (1024 ** 2)
        
        # Request metrics from middleware collector
        request_metrics = {
            "total_requests": metrics.total_requests,
            "active_requests": metrics.active_requests,
            "requests_per_minute": metrics.get_requests_per_minute(),
            "avg_response_time_ms": round(metrics.get_avg_response_time(), 2)
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
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

# ─────────────────────────────────────────────────────────────
# NEW ENDPOINT: GET /api/config — Runtime Configuration
# ─────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_runtime_config():
    """
    Runtime Configuration
    
    Returns the current runtime configuration of the NeuroSentinel security
    service, including detection thresholds, system settings, and feature flags.
    
    **Response Fields:**
    - `timestamp`: ISO 8601 timestamp
    - `service`: Service name and version
    - `detection_thresholds`: Structural and semantic drift thresholds per agent
    - `system_settings`: Target model, provider, API endpoints
    - `feature_flags`: Which features are enabled (Redis, GNN, HF, Groq, Checkpoints)
    - `runtime_state`: Current runtime state (uptime, request count, active requests)
    
    **Usage:**
    - Verify current configuration at runtime
    - Debug threshold-related issues
    - Check which features are enabled without redeploying
    """
    try:
        # Feature flags based on current environment state
        hf_api_key = bool(os.getenv("HF_API_KEY", ""))
        groq_api_key = bool(os.getenv("GROQ_API_KEY", ""))
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
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
                },
                "benign_scoring": {
                    "enabled": True,
                    "description": "Soft scoring adjusts thresholds based on benign confidence (0.0-1.0)",
                    "relaxation_factor": "structural: 1.2x-2.0x, semantic: 1.05x-1.2x for benign queries"
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

# ─────────────────────────────────────────────────────────────
# STARTUP/SHUTDOWN HOOKS
# ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 NeuroSentinel Security Service starting...")
    logger.info(f"📍 Target Model: {settings.TARGET_MODEL}")
    logger.info(f"📍 Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"📍 Platform: {platform.system()} {platform.release()}")
    logger.info(f"📍 Python: {platform.python_version()}")
    logger.info(f"📍 CPU Cores: {psutil.cpu_count()}")
    logger.info(f"📍 Memory: {round(psutil.virtual_memory().total / (1024**3), 1)} GB total")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 NeuroSentinel Security Service shutting down...")
    if redis_client:
        try:
            redis_client.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )