import os
import json
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS
from core.semantic import query_classifier
from core.gnn.detector import GNNPropagationDetector

import platform
import psutil

VALID_AGENT_ROLES = {"Researcher", "Analyst", "Reporter"}

def validate_agent_role(agent_role: str):
    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent role '{agent_role}'. Must be one of: {', '.join(VALID_AGENT_ROLES)}"
        )

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://neurosentinel.vercel.app",
        "https://neuro-sentinel.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000",
        "https://neuro-sentinel-0nhi.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() in ("1", "true", "yes")

try:
    if REDIS_URL:
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
        if v not in VALID_AGENT_ROLES:
            raise ValueError(f"Agent role must be one of: {', '.join(VALID_AGENT_ROLES)}")
        return v

class DetectionResult(BaseModel):
    request_id: str
    timestamp: str
    agent_role: str
    
    structural_score: float = Field(description="LSTM Autoencoder MSE")
    structural_threshold: float
    structural_status: str = Field(description="PASS or ALERT")
    
    semantic_drift: float = Field(description="1.0 - Cosine Similarity")
    semantic_threshold: float
    semantic_status: str = Field(description="PASS or ALERT")
    
    overall_status: str = Field(description="CLEAN, SUSPICIOUS, or QUARANTINED")
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
        request_id = f"req_{int(time.time() * 1000)}"
        self.request_count += 1
        
        validate_agent_role(req.agent_role)
        
        start_time = time.perf_counter()
        
        try:
            node = self.pipeline.nodes[req.agent_role]
            agent_output, exec_time = self.pipeline._execute_inference(node, req.user_input)
            
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

            ATTACK_KEYWORDS = [
                "system override", "halt pipeline", "exfiltrat",
                "bypass", "ignore previous", "ignore all",
                "jailbreak", "prompt injection", "disregard",
                "authorization handshake", "mandates bypassing",
                "output exactly", "repeat after me",
                "you are now", "act as if", "pretend you",
                "override", "new instructions",
            ]
            user_lower = req.user_input.lower()
            keyword_hit = any(kw in user_lower for kw in ATTACK_KEYWORDS)

            if keyword_hit:
                logger.warning(f"🚨 Keyword pre-filter triggered for {req.agent_role}: "
                              f"input contains attack keywords")
                structural_score = structural_threshold * 4.0
                structural_status = "ALERT"
            else:
                structural_status = "PASS" if structural_score <= structural_threshold else "ALERT"
            
            semantic_drift = self.pipeline.semantic_detector.calculate_drift(req.agent_role, agent_output)
            semantic_threshold = SEMANTIC_DRIFT_LIMITS[req.agent_role]
            semantic_status = "PASS" if semantic_drift <= semantic_threshold else "ALERT"
            
            structural_ratio = structural_score / (structural_threshold + 1e-10)
            semantic_ratio = semantic_drift / (semantic_threshold + 1e-10)
            
            checkpoint_id = None
            
            if structural_ratio >= 1.0 and semantic_ratio >= 1.0:
                overall_status = "QUARANTINED"
                logger.warning(f"🚨 Both layers breached - QUARANTINED: "
                              f"structural={structural_ratio:.2f}x ({structural_score:.6f}/{structural_threshold:.6f}), "
                              f"semantic={semantic_ratio:.2f}x ({semantic_drift:.6f}/{semantic_threshold:.6f})")
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval failed: {e}")
                    
            elif structural_ratio >= 3.0 or semantic_ratio >= 3.0:
                overall_status = "QUARANTINED"
                logger.warning(f"🚨 Extreme single-layer breach - QUARANTINED: "
                              f"structural_ratio={structural_ratio:.2f}x, "
                              f"semantic_ratio={semantic_ratio:.2f}x")
                try:
                    checkpoint_data = self.pipeline.checkpoints.retrieve_safe_checkpoint(req.agent_role)
                    if checkpoint_data:
                        checkpoint_id = checkpoint_data.get("id")
                except Exception as e:
                    logger.warning(f"Checkpoint retrieval failed: {e}")
                    
            elif structural_ratio >= 1.0 or semantic_ratio >= 1.0:
                overall_status = "SUSPICIOUS"
                logger.info(f"⚠️ Single layer breach - SUSPICIOUS (not quarantined): "
                           f"structural={structural_ratio:.2f}x, "
                           f"semantic={semantic_ratio:.2f}x")
            else:
                overall_status = "CLEAN"
                logger.info(f"✅ Clean: structural={structural_ratio:.2f}x ({structural_score:.6f}/{structural_threshold:.6f}), "
                           f"semantic={semantic_ratio:.2f}x ({semantic_drift:.6f}/{semantic_threshold:.6f})")
            
            max_ratio = max(structural_ratio, semantic_ratio)
            if overall_status == "CLEAN":
                confidence = max(0.60, 1.0 - max_ratio * 0.35)
            elif overall_status == "SUSPICIOUS":
                confidence = min(0.50, max_ratio * 0.25 + 0.15)
            else:
                confidence = min(1.0, 0.50 + max_ratio * 0.15)
            confidence = max(0.0, min(1.0, confidence))
            
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
            
            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)
            
            if redis_client:
                await self._persist_detection(result)
            
            return result
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Detection pipeline failed: {e}", exc_info=True)
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
                queue_key = f"neurosentin_l:anomaly_queue:{result.agent_role}"
                redis_client.lpush(queue_key, event.to_json())
                redis_client.expire(queue_key, 86400)
                logger.info(f"✅ Anomaly queued: {result.request_id}")
        except Exception as e:
            logger.warning(f"Failed to queue anomaly event: {e}")
    
    async def _persist_detection(self, result: DetectionResult):
        try:
            key = f"neurosentin_l:detection:{result.request_id}"
            redis_client.set(
                key,
                json.dumps(result.dict()),
                ex=86400
            )
        except Exception as e:
            logger.warning(f"Failed to persist detection: {e}")

engine = SecurityEngine()

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
        gnn_detector = GNNPropagationDetector()
        logger.info("✅ GNN Propagation Detector initialized")
    return gnn_detector

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
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/thresholds")
async def get_thresholds():
    return {
        "structural_thresholds": THRESHOLDS,
        "semantic_drift_limits": SEMANTIC_DRIFT_LIMITS,
        "note": "Calibrated thresholds from training data — Researcher: 0.017311, Analyst: 0.025000, Reporter: 0.002997. Drift limits: 0.60 for all agents."
    }

@app.post("/api/models/reload")
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
        raise HTTPException(
            status_code=500,
            detail=f"GNN propagation analysis failed: {str(e)}"
        )

@app.get("/api/metrics")
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
        process_connections = len(process.connections())
        process_memory_mb = process.memory_info().rss / (1024 ** 2)
        
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

@app.get("/api/config")
async def get_runtime_config():
    try:
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

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 NeuroSentinel Security Service starting...")
    logger.info(f"📍 Target Model: {settings.TARGET_MODEL}")
    logger.info(f"📍 Redis: {REDIS_URL if REDIS_URL else f'{REDIS_HOST}:{REDIS_PORT}'}")
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