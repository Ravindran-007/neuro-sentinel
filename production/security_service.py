# production/security_service.py
# NeuroSentinel Lite (Level 4 Deployable Production Layer)
# Fully unified syntax with Dual-Layer Detection and GNN Propagation Engines

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import redis
import torch

from config.settings import SystemSettings
from core.engine import IndustrialPipeline, THRESHOLDS, SEMANTIC_DRIFT_LIMITS
from core.gnn import GNNPropagationDetector
from core.kafka_producer import kafka_producer

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

# --- REQUEST / RESPONSE SCHEMAS ---
VALID_AGENT_ROLES = {"Researcher", "Analyst", "Reporter"}

def validate_agent_role(agent_role: str):
    if agent_role not in VALID_AGENT_ROLES:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown agent role '{agent_role}'. Must be one of: {', '.join(VALID_AGENT_ROLES)}"
        )

class DetectionRequest(BaseModel):
    agent_role: str = Field(..., description="Target agent: Researcher, Analyst, or Reporter")
    user_input: str = Field(..., min_length=1, max_length=5000, description="Input prompt to analyze")
    llm_provider: str = Field(default="ollama", description="LLM backend: ollama, openai, claude, custom")
    custom_endpoint: Optional[str] = Field(default=None, description="Custom LLM endpoint URL")

    @validator('agent_role')
    def validate_role(cls, v):
        if v not in VALID_AGENT_ROLES:
            raise ValueError(f"Agent role must be one of: {', '.join(VALID_AGENT_ROLES)}")
        return v

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

class AgentData(BaseModel):
    id: str
    role: str
    structural_score: float = 0.0
    semantic_drift: float = 0.0
    confidence: float = 0.0

class PropagationRequest(BaseModel):
    agents: List[AgentData]
    connections: List[List[str]]

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
            node = self.pipeline.nodes[req.agent_role]
            
            # Layer 0: LLM Inference Engine
            if is_cloud:
                logger.info("☁️ Cloud mode active: Skipping local Ollama execution loop.")
                agent_output = f"[Cloud Mode] Analyzed input: {req.user_input[:100]}..."
                exec_time = 0.1
            else:
                agent_output, exec_time = self.pipeline._execute_inference(node, req.user_input)

            # Layer 1: Structural Feature Engineering Analysis
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
            structural_threshold = THRESHOLDS[req.agent_role]
            structural_status = "PASS" if structural_score <= structural_threshold else "ALERT"

            # Layer 2: Contrastive Semantic Drift Processing
            semantic_drift = self.pipeline.semantic_detector.calculate_drift(req.agent_role, agent_output)
            semantic_threshold = SEMANTIC_DRIFT_LIMITS[req.agent_role]
            semantic_status = "PASS" if semantic_drift <= semantic_threshold else "ALERT"

            # Dynamic System Multi-Layer Evaluation Matrix
            if structural_status == "ALERT" or semantic_status == "ALERT":
                overall_status = "SUSPICIOUS"
            else:
                overall_status = "CLEAN"

            confidence = 1.0 - (structural_score / (structural_threshold + 1e-5))
            confidence = max(0.0, min(1.0, confidence))

            # Automated Sandbox Quarantine Rollback Integration
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
                    "cloud_mode": is_cloud
                }
            )

            # Async Tracking Data Management
            if overall_status != "CLEAN":
                await self._queue_anomaly_event(result, req.user_input)

            if redis_client:
                await self._persist_detection(result)

            # Level 4 Distributed Kafka Production Routing
            try:
                if result.overall_status != "CLEAN":
                    kafka_producer.produce_anomaly(result.dict())
                kafka_producer.produce_detection(result.dict())
            except Exception as e:
                logger.warning(f"Kafka distributed event delivery slipped: {e}")

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
                logger.info(f"🚨 Incident queued to memory cache: {result.request_id}")
        except Exception as e:
            logger.warning(f"Incident log queuing bypassed: {e}")

    async def _persist_detection(self, result: DetectionResult):
        try:
            key = f"neurosentinel:detection:{result.request_id}"
            redis_client.set(key, json.dumps(result.dict()), ex=86400)
        except Exception as e:
            logger.warning(f"Persistent metrics collection bypassed: {e}")

# Instantiates Singleton Engines
engine = SecurityEngine()
gnn_detector = GNNPropagationDetector(model_path="models/gnn/production_model.pt")
logger.info("🧠 Level 4 Inductive GraphSAGE Detector Initialized.")

# --- REST ENDPOINTS ---
@app.get("/")
async def root_welcome():
    return {
        "status": "online",
        "message": "Welcome to the NeuroSentinel Enterprise Security Gateway Core API.",
        "documentation": "/docs"
    }

@app.post("/api/detect", response_model=DetectionResult)
async def detect_anomaly(request: DetectionRequest):
    logger.info(f"Incoming inspection query -> Agent: {request.agent_role} | Text size: {len(request.user_input)}")
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
        "note": "Analyst has the tightest structural threshold (0.000804) due to deterministic validation paths."
    }

@app.post("/api/models/reload")
async def reload_models():
    try:
        engine.pipeline = IndustrialPipeline(settings=settings)
        logger.info("🔄 Neural core model binaries hot-reloaded from disk space.")
        return {"status": "success", "message": "All models reloaded"}
    except Exception as e:
        logger.error(f"Model update deployment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state/checkpoint/{agent_role}")
async def get_checkpoint(agent_role: str):
    validate_agent_role(agent_role)
    try:
        checkpoint = engine.pipeline.checkpoints.retrieve_safe_checkpoint(agent_role)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"No safe snapshot recorded for {agent_role}")
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
    validate_agent_role(agent_role)
    if not redis_client:
        return {"message": "Redis database storage offline.", "anomalies": []}
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

# --- LEVEL 4 PROPAGATION GRAPH ENDPOINTS ---
@app.post("/api/propagation/detect")
async def detect_propagation(request: PropagationRequest):
    try:
        agents_dict = [agent.dict() for agent in request.agents]
        return gnn_detector.detect_propagation(agents_dict, request.connections)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/propagation/graph")
async def get_propagation_graph():
    try:
        return gnn_detector.get_graph_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/propagation/status")
async def get_propagation_status():
    return {
        "status": "ready",
        "model_path": "models/gnn/production_model.pt",
        "graph_nodes": gnn_detector.graph_builder.get_node_count(),
        "graph_edges": gnn_detector.graph_builder.get_edge_count()
    }

# --- SYSTEM EVENT LOOPS ---
@app.on_event("startup")
async def startup_event():
    logger.info("🛫 NeuroSentinel Microservice Router spinning up orchestration threads...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛬 Terminating proxy connections...")
    if redis_client:
        redis_client.close()

@app.on_event("startup")
async def list_routes():
    logger.info("📋 === REGISTERED ENDPOINT TOPOLOGY ===")
    for route in sorted(app.routes, key=lambda r: r.path):
        if hasattr(route, "path") and hasattr(route, "methods"):
            logger.info(f"   {list(route.methods)} -> {route.path}")
    logger.info("📋 =====================================")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")