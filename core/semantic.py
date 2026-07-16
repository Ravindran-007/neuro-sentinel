# core/semantic.py
# NeuroSentinel — Contrastive Semantic Drift Detector
# Uses Hugging Face Inference API (primary) with TF-IDF mock fallback

import requests
import numpy as np
import os
import hashlib
from config.settings import SystemSettings

class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.anchors = {}

        # Hugging Face Inference API (PRIMARY — actually works)
        # NOTE: Groq does NOT support an embeddings API — nomic-embed-text is Ollama-only
        self.hf_api_key = os.getenv("HF_API_KEY", "")
        self.hf_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model}"
        self._use_hf = bool(self.hf_api_key)

        if self._use_hf:
            print("✅ [Semantic] Using Hugging Face API for embeddings")
        else:
            print("⚠️ [Semantic] No HF_API_KEY — using TF-IDF mock embeddings")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding from HF Inference API, or TF-IDF mock fallback."""

        if self._use_hf:
            try:
                response = requests.post(
                    self.hf_url,
                    headers={"Authorization": f"Bearer {self.hf_api_key}"},
                    json={"inputs": text},
                    timeout=15
                )
                if response.status_code == 200:
                    data = response.json()
                    # HF returns [[token_vecs...]] — mean-pool to sentence vector
                    arr = np.array(data, dtype=np.float32)
                    if arr.ndim == 2:
                        return arr.mean(axis=0)
                    return arr.flatten()
                print(f"  ⚠️ [HF] API error {response.status_code}: {response.text[:120]}")
            except Exception as e:
                print(f"  ⚠️ [HF] Embedding failed: {e}")

        # TF-IDF-style mock: token frequency vector (deterministic, content-sensitive)
        # Different texts produce meaningfully different vectors unlike the old hash seed approach
        tokens = text.lower().split()
        vec = np.zeros(384, dtype=np.float32)
        for i, token in enumerate(tokens):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % 384
            vec[idx] += 1.0 / (i + 1)  # positional weighting
        norm = np.linalg.norm(vec)
        return vec / (norm + 1e-8)

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
