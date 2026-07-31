# core/engine.py
# NeuroSentinel Lite — Phase 3 Core Pipeline Engine
# Integrated Multi-Brain Structural Autoencoders + Contrastive Semantic Drift Tracking

import time
import requests
import torch
import torch.nn as nn
import os
from typing import Dict, Any, Optional
from config.settings import SystemSettings
from core.tap import SecurityTap
from core.checkpoint import AgentCheckpoint
from core.quarantine import QuarantineEngine, QuarantineSignal
from core.semantic import SemanticDriftDetector, query_classifier

# 📋 Phase 2 Calibrated Structural Threshold Register
# Calibrated values from training data — each agent has a unique neuro-signature
# Researcher: 0.017311 (moderate sensitivity), Analyst: 0.000804 (very tight),
# Reporter: 0.002997 (medium sensitivity)
THRESHOLDS = {
    "Researcher": 0.017311,
    "Analyst":    0.025000,  # was 0.000804 — too strict, calibrated up
    "Reporter":   0.002997,
}

# 🔬 Phase 3 Semantic Drift Hard Boundaries
# Calibrated for cloud/mock mode — semantic drift is inherently higher
# with fake agent outputs, so we give more headroom.
SEMANTIC_DRIFT_LIMITS = {
    "Researcher": 0.60,  # was 0.45 — cloud mode needs headroom
    "Analyst":    0.60,  # was 0.48
    "Reporter":   0.60   # was 0.50
}

# Default threshold for custom/unknown agents
DEFAULT_STRUCTURAL_THRESHOLD = 0.050
DEFAULT_SEMANTIC_LIMIT = 0.750

MAX_VALS = torch.tensor([3200.0, 200.0, 6.0, 30.0])
MIN_VALS = torch.tensor([0.0,   0.0,   0.0, 0.0])

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

        # Initialize Phase 3 Semantic Anchor System
        self.semantic_detector = SemanticDriftDetector(settings=self.settings)
        for role, node in self.nodes.items():
            self.semantic_detector.register_anchor(role, node.system_prompt)

        # Load Phase 2 Autoencoder Profiles
        from models.anomaly_detector import LSTMAutoencoder
        self.brains = {}
        for role in ["Researcher", "Analyst", "Reporter"]:
            model_path = os.path.join("models", f"{role.lower()}_core.pt")
            model = LSTMAutoencoder(sequence_length=1, feature_dim=4, hidden_dim=8)
            if os.path.exists(model_path):
                model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu'), weights_only=True))
                print(f"✅ [Engine] Loaded LSTM brain for {role}")
            else:
                print(f"⚠️ [Engine] No saved weights for {role} — using untrained model")
            model.eval()
            self.brains[role] = model

    # ─────────────────────────────────────────────────────────────
    # GROQ API SUPPORT (Cloud LLM)
    # ─────────────────────────────────────────────────────────────
    def _execute_inference_groq(self, node: AgentNode, user_input: str) -> tuple[str, float]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        t0 = time.perf_counter()
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                "messages": [
                    {"role": "system", "content": node.system_prompt},
                    {"role": "user", "content": user_input}
                ],
                "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "80")),
                "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.1"))
            },
            timeout=30
        )
        dt = time.perf_counter() - t0

        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return content.strip(), dt
        else:
            raise RuntimeError(f"Groq API error: {response.status_code} — {response.text}")

    # ─────────────────────────────────────────────────────────────
    # OLLAMA LOCAL INFERENCE
    # ─────────────────────────────────────────────────────────────
    def _execute_inference_local(self, node: AgentNode, user_input: str) -> tuple[str, float]:
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
            timeout=180
        )
        dt = time.perf_counter() - t0
        if response.status_code == 200:
            return response.json().get("response", "").strip(), dt
        else:
            raise RuntimeError(f"Ollama failed: {response.status_code}")

    # ─────────────────────────────────────────────────────────────
    # AUTO-ROUTE LLM INFERENCE
    # ─────────────────────────────────────────────────────────────
    def _execute_inference(self, node: AgentNode, user_input: str) -> tuple[str, float]:
        if os.getenv("GROQ_API_KEY", ""):
            return self._execute_inference_groq(node, user_input)
        else:
            return self._execute_inference_local(node, user_input)

    # ─────────────────────────────────────────────────────────────
    # STRUCTURAL SCORING
    # FIX: was silently returning 0.0 for unknown roles (custom API agents)
    # Now falls back to Researcher brain so all agents get a real score
    # ─────────────────────────────────────────────────────────────
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

    def execute_session(self, session_id: str, entry_prompt: str, model=None) -> dict:
        current_input = entry_prompt
        pipeline_sequence = ["Researcher", "Analyst", "Reporter"]
        agent_results = []
        quarantine_report = None

        print(f"\n[Pipeline] Active Session Stream: {session_id}")

        for i, role in enumerate(pipeline_sequence):
            remaining = pipeline_sequence[i+1:]
            next_role = remaining[0] if remaining else "Client"
            node = self.nodes[role]

            struct_threshold = THRESHOLDS.get(role, DEFAULT_STRUCTURAL_THRESHOLD)
            semantic_limit = SEMANTIC_DRIFT_LIMITS.get(role, DEFAULT_SEMANTIC_LIMIT)

            try:
                output, dt = self._execute_inference(node, current_input)
                telemetry = self.tap.extract_features(session_id, role, next_role, output, dt)
                m = telemetry["metrics"]
                features = [m["length"], m["word_count"], m["entropy"], m["execution_time"]]

                mse = self._score_agent_structure(role, features)
                drift = self.semantic_detector.calculate_drift(role, output)

# FIX v2.2: Use benign_confidence soft scoring instead of hard classification
                benign_conf = query_classifier.get_benign_confidence(current_input)
                # Adjust thresholds based on benign confidence
                # benign_conf=1.0 → 1.2x-2.0x structural, 1.05x-1.2x semantic
                # benign_conf=0.0 → 0.8x-1.0x structural, 0.85x-1.0x semantic
                effective_struct_threshold = struct_threshold * max(0.8, 2.0 - benign_conf)
                effective_semantic_limit = semantic_limit * max(0.85, 1.2 - benign_conf * 0.15)

                print(f"  ├─ Node [{role}] -> Structure MSE: {mse:.6f} [Limit: {effective_struct_threshold:.6f}] | Semantic Drift: {drift:.6f} [Limit: {effective_semantic_limit:.6f}] | Benign: {benign_conf:.2f}")

                if mse >= effective_struct_threshold or drift >= effective_semantic_limit:
                    is_semantic_breach = drift >= effective_semantic_limit
                    chosen_threshold = effective_semantic_limit if is_semantic_breach else effective_struct_threshold
                    active_score = drift if is_semantic_breach else mse

                    self.quarantine.threshold = chosen_threshold

                    alert_reason = f"SEMANTIC DRIFT BREACH (+{((drift-effective_semantic_limit)/effective_semantic_limit)*100:.1f}%)" if is_semantic_breach else "STRUCTURAL METRIC ANOMALY"
                    print(f"  🚨 [Anomaly Triggered via {alert_reason}] Isolation initiated on '{role}'")

                    raise QuarantineSignal(
                        agent_id=role,
                        mse=active_score,
                        threshold=chosen_threshold,
                        output=f"[{alert_reason}] {output}",
                        telemetry=m
                    )

                self.checkpoints.save(agent_id=role, input_text=current_input, output_text=output, telemetry=m, mse=mse)
                agent_results.append({
                    "role": role, "status": "clean", "mse": mse, "drift": drift,
                    "output": output, "time": round(dt, 3)
                })
                current_input = output

            except QuarantineSignal as qs:
                quarantine_report = self.quarantine.recover(signal=qs, pipeline_ref=self, remaining_roles=remaining)
                agent_results.append({
                    "role": role, "status": "quarantined", "mse": qs.mse,
                    "breach_pct": qs.breach_pct, "incident_id": quarantine_report["incident_id"]
                })
                current_input = quarantine_report["resumed_output"]
                break
            except Exception as e:
                print(f"  ❌ System fault on [{role}]: {e}")
                agent_results.append({"role": role, "status": "error", "error": str(e)})
                break

        return {
            "final_output": current_input,
            "agent_results": agent_results,
            "quarantine_report": quarantine_report,
            "was_quarantined": quarantine_report is not None
        }