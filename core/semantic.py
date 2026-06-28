# core/semantic.py
# NeuroSentinel Lite — Contrastive Semantic Drift Detector
# Uses Hugging Face Inference API for embeddings

import requests
import numpy as np
import os
from config.settings import SystemSettings

class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.anchors = {}
        
        # Hugging Face API for embeddings
        self.hf_api_key = os.getenv("HF_API_KEY", "")
        self.hf_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model}"
        
        self._use_mock = not self.hf_api_key
        if self._use_mock:
            print("⚠️ [Semantic] No HF_API_KEY — using mock embeddings")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding from Hugging Face API or mock."""
        if self._use_mock:
            # Mock embedding (random) — will vary, causing drift
            return np.random.randn(384).astype(np.float32)
        
        try:
            headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            response = requests.post(
                self.hf_url,
                headers=headers,
                json={"inputs": text},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and isinstance(data[0], list):
                    return np.array(data[0], dtype=np.float32)
                elif isinstance(data, list):
                    return np.array(data, dtype=np.float32)
                else:
                    return np.random.randn(384).astype(np.float32)
            else:
                print(f"  ⚠️ [Semantic Warning] HF API error: {response.status_code}")
                return np.random.randn(384).astype(np.float32)
        except Exception as e:
            print(f"  ⚠️ [Semantic Warning] Embedding failed: {e}")
            return np.random.randn(384).astype(np.float32)

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

        dot_product = np.dot(anchor_vec, output_vec)
        norm_anchor = np.linalg.norm(anchor_vec)
        norm_output = np.linalg.norm(output_vec)
        
        cosine_similarity = dot_product / (norm_anchor * norm_output + 1e-8)
        cosine_similarity = np.clip(cosine_similarity, -1.0, 1.0)
        
        drift_score = 1.0 - float(cosine_similarity)
        return round(drift_score, 6)