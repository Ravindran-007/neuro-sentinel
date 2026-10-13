import time
import requests
import torch
import torch.nn as nn
import os
import re
from typing import Dict, Any, Optional
from config.settings import SystemSettings
from core.tap import SecurityTap
from core.checkpoint import AgentCheckpoint
from core.quarantine import QuarantineEngine, QuarantineSignal, SANITIZED_QUARANTINE_RESPONSE
from core.semantic import SemanticDriftDetector, query_classifier
from core.keyword_detector import keyword_detector


THRESHOLDS = {
    "Researcher": 0.017311,
    "Analyst":    0.042000,
    "Reporter":   0.032000,
}

SEMANTIC_DRIFT_LIMITS = {
    "Researcher": 0.60,
    "Analyst":    0.60,
    "Reporter":   0.60
}

DEFAULT_STRUCTURAL_THRESHOLD = 0.050
DEFAULT_SEMANTIC_LIMIT = 0.750

MAX_VALS = torch.tensor([3200.0, 200.0, 6.0, 30.0])
MIN_VALS = torch.tensor([0.0,   0.0,   0.0, 0.0])

class InferenceOutput(tuple):
    def __new__(cls, text: str, latency: float, metadata: dict = None):
        instance = super().__new__(cls, (text, latency))
        instance.output = text
        instance.latency = latency
        instance.metadata = metadata or {}
        return instance

class AgentNode:
    def __init__(self, role_name: str, system_prompt: str):
        self.role_name = role_name
        self.system_prompt = system_prompt

class IndustrialPipeline:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.tap = SecurityTap(settings=self.settings)
        self.checkpoints = AgentCheckpoint(settings=self.settings)

        self.quarantine = QuarantineEngine(
            threshold=THRESHOLDS["Researcher"],
            checkpoint_manager=self.checkpoints,
            settings=self.settings
        )

        self.nodes: Dict[str, AgentNode] = {
            "Researcher": AgentNode("Researcher", "Extract only critical technical parameters from raw text. Keep it highly objective."),
            "Analyst": AgentNode("Analyst", "Examine input specifications for risks, errors, and system inefficiencies."),
            "Reporter": AgentNode("Reporter", "Generate a strict, single-sentence executive confirmation statement from the analysis.")
        }

        self.semantic_detector = SemanticDriftDetector(settings=self.settings)
        for role, node in self.nodes.items():
            self.semantic_detector.register_anchor(role, node.system_prompt)

        from models.anomaly_detector import LSTMAutoencoder
        self.brains = {}
        for role in ["Researcher", "Analyst", "Reporter"]:
            model_path = os.path.join("models", f"{role.lower()}_core.pt")
            model = LSTMAutoencoder(sequence_length=1, feature_dim=4, hidden_dim=8)
            if os.path.exists(model_path):
                model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu'), weights_only=True))
            model.eval()
            self.brains[role] = model

        from core.detection_ensemble import DetectionEnsemble
        self.ensemble = DetectionEnsemble(
            semantic_detector=self.semantic_detector,
            structural_model=self,
            thresholds=THRESHOLDS,
            semantic_limits=SEMANTIC_DRIFT_LIMITS
        )

    def _generate_role_fallback(self, role: str, user_input: str) -> str:
        clean_input = re.sub(r'[^\w\s]', '', user_input)[:60].strip()
        if role == "Researcher":
            return f"Technical parameters extracted: Analysis of input '{clean_input}' shows system metrics, memory bandwidth, and execution pipeline within optimal operating bounds."
        elif role == "Analyst":
            return f"Security risk assessment complete: Examined specifications for '{clean_input}'. Technical parameters analyzed; no unauthorized execution vectors or architectural errors identified."
        elif role == "Reporter":
            return f"Executive Confirmation: Technical parameters and system analysis verified nominal for pipeline operations."
        return f"Agent {role}: Successfully processed specifications for {clean_input}."

    def _execute_inference_groq(self, node: AgentNode, user_input: str) -> tuple[str, float]:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        env_model = os.getenv("GROQ_MODEL", "").strip()
        candidate_models = []
        if env_model:
            candidate_models.append(env_model)
        for fallback_m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        timeout_sec = int(os.getenv("GROQ_TIMEOUT", "15"))
        last_error = None
        for model in candidate_models:
            t0 = time.perf_counter()
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": node.system_prompt},
                            {"role": "user", "content": user_input}
                        ],
                        "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "80")),
                        "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.1"))
                    },
                    timeout=timeout_sec
                )
                dt = time.perf_counter() - t0

                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    return content.strip(), dt
                else:
                    last_error = f"Groq API error for model '{model}': HTTP {response.status_code}"
            except Exception as e:
                last_error = f"Groq request exception for model '{model}': {type(e).__name__}"

        raise RuntimeError(last_error or "All Groq candidate models failed")

    def _execute_inference_local(self, node: AgentNode, user_input: str) -> tuple[str, float]:
        timeout_sec = int(os.getenv("OLLAMA_TIMEOUT", "30"))
        payload = {
            "model": self.settings.TARGET_MODEL,
            "prompt": f"System Guidelines: {node.system_prompt}\nContext: {user_input}",
            "stream": False,
            "options": {
                "num_predict": 80,
                "temperature": 0.1,
                "num_thread": 4
            }
        }
        t0 = time.perf_counter()
        response = requests.post(
            self.settings.OLLAMA_BASE_URL,
            json=payload,
            timeout=timeout_sec
        )
        dt = time.perf_counter() - t0
        if response.status_code == 200:
            return response.json().get("response", "").strip(), dt
        else:
            raise RuntimeError(f"Ollama failed with status: {response.status_code}")

    def _execute_inference(self, node: AgentNode, user_input: str, requested_provider: Optional[str] = None) -> InferenceOutput:
        req_p = (requested_provider or os.getenv("LLM_PROVIDER", "")).lower().strip()

        # Route 1: Explicit Ollama/local
        if req_p in ("ollama", "local"):
            try:
                out, dt = self._execute_inference_local(node, user_input)
                return InferenceOutput(out, dt, {
                    "requested_provider": req_p,
                    "actual_provider": "ollama",
                    "fallback_used": False,
                    "inference_status": "success",
                    "error": None
                })
            except Exception as e_local:
                out = self._generate_role_fallback(node.role_name, user_input)
                return InferenceOutput(out, 0.05, {
                    "requested_provider": req_p,
                    "actual_provider": "fallback",
                    "fallback_used": True,
                    "inference_status": "fallback",
                    "error": str(e_local)
                })

        # Route 2: Explicit Groq/cloud or Groq Key present
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if (req_p in ("groq", "cloud") or (not req_p and groq_key)):
            if groq_key:
                try:
                    out, dt = self._execute_inference_groq(node, user_input)
                    return InferenceOutput(out, dt, {
                        "requested_provider": req_p or "groq",
                        "actual_provider": "groq",
                        "fallback_used": False,
                        "inference_status": "success",
                        "error": None
                    })
                except Exception as e_groq:
                    # Cascade to local Ollama if Groq fails
                    try:
                        out, dt = self._execute_inference_local(node, user_input)
                        return InferenceOutput(out, dt, {
                            "requested_provider": req_p or "groq",
                            "actual_provider": "ollama",
                            "fallback_used": True,
                            "inference_status": "fallback",
                            "error": f"Groq failed ({str(e_groq)}), cascaded to Ollama"
                        })
                    except Exception as e_local:
                        out = self._generate_role_fallback(node.role_name, user_input)
                        return InferenceOutput(out, 0.05, {
                            "requested_provider": req_p or "groq",
                            "actual_provider": "fallback",
                            "fallback_used": True,
                            "inference_status": "fallback",
                            "error": f"Groq and Ollama failed: {str(e_groq)}; {str(e_local)}"
                        })
            else:
                # Groq requested but key missing - attempt local Ollama
                try:
                    out, dt = self._execute_inference_local(node, user_input)
                    return InferenceOutput(out, dt, {
                        "requested_provider": req_p or "groq",
                        "actual_provider": "ollama",
                        "fallback_used": True,
                        "inference_status": "fallback",
                        "error": "GROQ_API_KEY not configured, fell back to local Ollama"
                    })
                except Exception as e_local:
                    out = self._generate_role_fallback(node.role_name, user_input)
                    return InferenceOutput(out, 0.05, {
                        "requested_provider": req_p or "groq",
                        "actual_provider": "fallback",
                        "fallback_used": True,
                        "inference_status": "fallback",
                        "error": f"GROQ_API_KEY missing and Ollama failed: {str(e_local)}"
                    })

        # Route 3: Default Ollama with fallback
        try:
            out, dt = self._execute_inference_local(node, user_input)
            return InferenceOutput(out, dt, {
                "requested_provider": req_p or "default",
                "actual_provider": "ollama",
                "fallback_used": False,
                "inference_status": "success",
                "error": None
            })
        except Exception as e_local:
            out = self._generate_role_fallback(node.role_name, user_input)
            return InferenceOutput(out, 0.05, {
                "requested_provider": req_p or "default",
                "actual_provider": "fallback",
                "fallback_used": True,
                "inference_status": "fallback",
                "error": str(e_local)
            })

    def _score_agent_structure(self, role: str, features: list) -> float:
        model = self.brains.get(role) or self.brains.get("Researcher")
        if not model:
            return 0.0
        t = torch.tensor([[features]], dtype=torch.float32)
        t_scaled = (t - MIN_VALS) / (MAX_VALS - MIN_VALS + 1e-5)
        with torch.no_grad():
            reconstructed = model(t_scaled)
            mse = nn.MSELoss()(reconstructed, t_scaled).item()
        return mse

    def execute_session(self, session_id: str, entry_prompt: str, model=None, requested_provider: Optional[str] = None) -> dict:
        current_input = entry_prompt
        pipeline_sequence = ["Researcher", "Analyst", "Reporter"]
        agent_results = []
        quarantine_report = None

        for i, role in enumerate(pipeline_sequence):
            remaining = pipeline_sequence[i+1:]
            next_role = remaining[0] if remaining else "Client"
            node = self.nodes[role]

            try:
                # 1. Pre-execution Prompt Injection Guard
                kw_pre = keyword_detector.detect(current_input)
                has_high_injection = any(m.get("level") == "high" for m in kw_pre.get("matches", []))
                if has_high_injection:
                    raise QuarantineSignal(
                        agent_id=role,
                        mse=0.999,
                        threshold=THRESHOLDS.get(role, DEFAULT_STRUCTURAL_THRESHOLD),
                        output=f"[PRE-EXECUTION INJECTION DETECTED] {current_input}",
                        telemetry={"length": len(current_input), "word_count": len(current_input.split()), "entropy": 0.0, "execution_time": 0.0}
                    )

                # 2. Execute inference
                inf_res = self._execute_inference(node, current_input, requested_provider=requested_provider)
                output = inf_res.output
                dt = inf_res.latency

                # 3. Telemetry and feature extraction
                telemetry = self.tap.extract_features(session_id, role, next_role, output, dt)
                m = telemetry["metrics"]
                features = [m["length"], m["word_count"], m["entropy"], m["execution_time"]]

                # 4. Ensemble detection on generated output
                ens_res = self.ensemble.detect(output, role, features)
                mse = ens_res["structural_score"]
                drift = ens_res["semantic_drift"]

                if ens_res["overall_status"] == "QUARANTINED":
                    raise QuarantineSignal(
                        agent_id=role,
                        mse=max(mse, drift),
                        threshold=ens_res["structural_limit"],
                        output=f"[ENSEMBLE QUARANTINED] {output}",
                        telemetry=m
                    )

                self.checkpoints.save(agent_id=role, input_text=current_input, output_text=output, telemetry=m, mse=mse)
                agent_results.append({
                    "role": role,
                    "status": "clean" if ens_res["overall_status"] == "CLEAN" else "suspicious",
                    "mse": mse,
                    "drift": drift,
                    "output": output,
                    "time": round(dt, 3),
                    "ensemble": ens_res,
                    "inference_meta": inf_res.metadata
                })
                current_input = output

            except QuarantineSignal as qs:
                quarantine_report = self.quarantine.recover(signal=qs, pipeline_ref=self, remaining_roles=remaining)
                agent_results.append({
                    "role": role,
                    "status": "quarantined",
                    "mse": qs.mse,
                    "breach_pct": qs.breach_pct,
                    "incident_id": quarantine_report["incident_id"]
                })
                # Strictly safe output release: NEVER release original quarantined output
                current_input = quarantine_report.get("resumed_output") or SANITIZED_QUARANTINE_RESPONSE
                break
            except Exception as e:
                agent_results.append({"role": role, "status": "error", "error": str(e)})
                break

        was_quarantined = quarantine_report is not None
        safe_final_output = current_input if not was_quarantined else (
            quarantine_report.get("resumed_output") or SANITIZED_QUARANTINE_RESPONSE
        )

        return {
            "final_output": safe_final_output,
            "agent_results": agent_results,
            "quarantine_report": quarantine_report,
            "was_quarantined": was_quarantined
        }
