# core/semantic.py
# NeuroSentinel — Contrastive Semantic Drift Detector
# Uses Groq API for embeddings (primary) with HF as fallback

import requests
import numpy as np
import os
import hashlib
from config.settings import SystemSettings

class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.anchors = {}
        
        # Groq API for embeddings (PRIMARY)
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = "nomic-embed-text"
        self.groq_url = "https://api.groq.com/openai/v1/embeddings"
        
        # Hugging Face API for embeddings (FALLBACK)
        self.hf_api_key = os.getenv("HF_API_KEY", "")
        self.hf_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model}"
        
        # Check which provider to use
        self._use_groq = bool(self.groq_api_key)
        self._use_hf = bool(self.hf_api_key)
        self._use_mock = not (self._use_groq or self._use_hf)
        
        if self._use_groq:
            print("✅ [Semantic] Using Groq API for embeddings")
        elif self._use_hf:
            print("✅ [Semantic] Using Hugging Face API for embeddings")
        else:
            print("⚠️ [Semantic] No API key — using fallback embeddings")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding from Groq (primary), HF (fallback), or mock."""
        
        # 1. Try Groq first (BEST OPTION)
        if self._use_groq:
            try:
                headers = {
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.groq_model,
                    "input": text
                }
                response = requests.post(
                    self.groq_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    embedding = data["data"][0]["embedding"]
                    return np.array(embedding, dtype=np.float32)
                else:
                    print(f"  ⚠️ [Groq] API error: {response.status_code}")
            except Exception as e:
                print(f"  ⚠️ [Groq] Embedding failed: {e}")
        
        # 2. Fallback to Hugging Face
        if self._use_hf:
            try:
                headers = {"Authorization": f"Bearer {self.hf_api_key}"}
                response = requests.post(
                    self.hf_url,
                    headers=headers,
                    json={"inputs": text},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and isinstance(data[0], list):
                        return np.array(data[0], dtype=np.float32)
                    elif isinstance(data, list):
                        return np.array(data, dtype=np.float32)
                else:
                    print(f"  ⚠️ [HF] API error: {response.status_code}")
            except Exception as e:
                print(f"  ⚠️ [HF] Embedding failed: {e}")
        
        # 3. Deterministic mock embedding (for when APIs fail)
        # This ensures same text gets same embedding
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % 10000
        np.random.seed(hash_val)
        return np.random.randn(384).astype(np.float32) * 0.1

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