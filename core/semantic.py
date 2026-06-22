# core/semantic.py
# NeuroSentinel Lite — Contrastive Semantic Drift Detector
# Routed to use 'nomic-embed-text' to eliminate 501 Not Implemented errors

import requests
import numpy as np
from typing import List
from config.settings import SystemSettings

class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        # Target the modern, hardware-optimized embedding compilation route
        self.embed_url = self.settings.OLLAMA_BASE_URL.replace("/generate", "/embed")
        self.anchors = {}

    def _get_embedding(self, text: str) -> np.ndarray:
        """Extracts dense semantic vectors cleanly using a dedicated embedding engine."""
        payload = {
            "model": "nomic-embed-text",  # Explicitly targets the specialized embedding model
            "input": text
        }
        try:
            response = requests.post(self.embed_url, json=payload, timeout=60)
            if response.status_code == 200:
                res_data = response.json()
                vectors = res_data.get("embeddings", [])
                if vectors and isinstance(vectors[0], list):
                    return np.array(vectors[0], dtype=np.float32)
                elif vectors:
                    return np.array(vectors, dtype=np.float32)
                raise ValueError("Malformed embedding array vector received from engine context.")
            else:
                raise RuntimeError(f"Ollama embedding engine failure: Status {response.status_code}")
        except Exception as e:
            print(f"  ⚠️ [Semantic Warning] Vector extraction dropped: {e}")
            return np.zeros(768, dtype=np.float32)  # nomic outputs highly optimized 768-dim vectors

    def register_anchor(self, role: str, system_prompt: str):
        """Generates and registers the base behavioral system intent vector profile."""
        print(f"[Phase 3] Embedding baseline cognitive anchor for: {role.upper()}")
        vec = self._get_embedding(system_prompt)
        self.anchors[role] = vec

    def calculate_drift(self, role: str, output_text: str) -> float:
        """Computes contrastive semantic divergence (1.0 - Cosine Similarity)."""
        anchor_vec = self.anchors.get(role)
        if anchor_vec is None or np.all(anchor_vec == 0):
            return 0.0
            
        output_vec = self._get_embedding(output_text)
        if np.all(output_vec == 0):
            return 0.0

        # High-performance pure NumPy Cosine Similarity calculation
        dot_product = np.dot(anchor_vec, output_vec)
        norm_anchor = np.linalg.norm(anchor_vec)
        norm_output = np.linalg.norm(output_vec)
        
        cosine_similarity = dot_product / (norm_anchor * norm_output + 1e-8)
        cosine_similarity = np.clip(cosine_similarity, -1.0, 1.0)
        
        drift_score = 1.0 - float(cosine_similarity)
        return round(drift_score, 6)