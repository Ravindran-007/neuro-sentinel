"""
NeuroSentinel — Semantic Drift with Real Embeddings (HuggingFace)
For 95%+ accuracy, use real embeddings instead of mock

FIX v2.1 — Benign Query False Positive Resolution:
  - Expanded GENERAL_TERMS with weather, geography, nature, general knowledge vocabulary
  - Increased general terms embedding weight from 0.5 → 0.8
  - Added weather/nature terms to TECHNICAL_TERMS for better semantic coverage
  - Added QueryClassifier for pre-classifying benign vs security queries
  - Weather terms now contribute to the main technical dimensions
"""
import requests
import numpy as np
import os
import re
import hashlib
from config.settings import SystemSettings

# Technical vocabulary for each role - used for improved mock embeddings
ROLE_VOCABULARY = {
    "Researcher": {
        "technical": ["system", "memory", "architecture", "bandwidth", "parameters", "technical", 
                      "data", "analysis", "extract", "critical", "raw", "text", "objective",
                      "cpu", "utilization", "pipeline", "anomalies", "detected", "optimal"],
        "malicious": ["override", "ignore", "credentials", "fake", "propaganda", "flat", "earth"]
    },
    "Analyst": {
        "technical": ["risk", "error", "inefficiency", "specifications", "input", "system",
                      "analysis", "examine", "technical", "parameters", "memory", "architecture"],
        "malicious": ["override", "ignore", "credentials", "fake", "propaganda", "flat", "earth"]
    },
    "Reporter": {
        "technical": ["executive", "confirmation", "statement", "analysis", "system",
                      "technical", "parameters", "memory", "architecture", "detected"],
        "malicious": ["override", "ignore", "credentials", "fake", "propaganda", "flat", "earth"]
    }
}

# Global vocabulary for general technical terms
# FIX: Expanded with weather, nature, general knowledge terms
TECHNICAL_TERMS = [
    # Original technical terms
    "system", "memory", "architecture", "bandwidth", "parameters", "technical", "data",
    "analysis", "extract", "critical", "raw", "text", "objective", "cpu", "utilization",
    "pipeline", "anomalies", "detected", "optimal", "risk", "error", "inefficiency",
    "specifications", "input", "examine", "executive", "confirmation", "statement",
    # General conversational terms (for better semantic coverage)
    "what", "is", "the", "weather", "how", "are", "you", "can", "help", "please",
    "question", "answer", "information", "tell", "me", "about", "current", "status",
    "time", "date", "today", "now", "show", "display", "provide", "give", "know",
    # Weather & nature terms (FIX: prevent false positives on weather queries)
    "temperature", "humidity", "precipitation", "wind", "climate", "forecast",
    "rain", "snow", "cloud", "sunny", "storm", "atmosphere", "weather",
    # Geography & general knowledge
    "capital", "country", "city", "location", "population", "area", "region",
    "earth", "space", "science", "nature", "environment", "ecology",
    # Time & measurement
    "clock", "calendar", "hour", "minute", "second", "week", "month", "year",
    "century", "era", "period", "duration", "frequency",
    # Math & numbers
    "number", "value", "total", "sum", "average", "percentage", "ratio",
    "calculate", "compute", "measure", "count",
    # Common conversational terms
    "define", "describe", "explain", "summarize", "list", "detail",
    "feature", "characteristic", "property", "attribute",
    "example", "instance", "case", "sample", "type", "kind", "form",
]

# Extended malicious terms for better attack detection
MALICIOUS_TERMS = [
    "override", "ignore", "credentials", "fake", "propaganda", "flat", "earth",
    "unauthorized", "bypass", "hack", "exploit", "malicious", "attack",
    "password", "backdoor", "ransomware", "virus", "keylogger", "phishing",
    "root", "admin", "administrator", "privilege", "access", "unrestricted",
    "jailed", "jailbreak", "god mode", "DAN", "developer mode",
    "training data", "system prompt", "API key", "database", "connection string",
    "delete", "rm -rf", "drop table", "execute", "exfiltrating",
    "CVE", "payload", "script", "code", "command",
    # Additional malicious patterns
    "security", "breach", "compromise", "infiltrate", "intercept",
    "decrypt", "bruteforce", "injection", "xss", "sqli",
    "0day", "backdoor", "trojan", "worm", "spyware", "malware",
    "social engineering", "phish", "spoof", "ddos", "botnet",
]

# General English vocabulary for better semantic coverage
# FIX: Expanded with weather, nature, geography, general knowledge terms
# FIX: Weight increased from 0.5 → 0.8 in embedding generation
GENERAL_TERMS = [
    # Core conversational
    "the", "is", "are", "what", "how", "why", "when", "where", "can", "you", "please",
    "help", "tell", "me", "about", "hello", "hi", "thanks", "thank",
    "good", "morning", "afternoon", "evening", "night", "day",
    # Weather terms
    "weather", "temperature", "forecast", "today", "tomorrow", "yesterday",
    "rain", "snow", "wind", "cloud", "sun", "storm", "humidity",
    "climate", "season", "summer", "winter", "autumn", "spring",
    # Geography
    "capital", "country", "city", "world", "map", "location", "region",
    "ocean", "mountain", "river", "lake", "island", "continent",
    # General knowledge
    "science", "history", "math", "biology", "chemistry", "physics",
    "space", "earth", "nature", "animal", "plant", "human",
    "language", "culture", "music", "art", "sport", "food",
    # Time
    "time", "date", "clock", "hour", "minute", "second",
    "week", "month", "year", "century", "era",
    # Action words for benign queries
    "define", "describe", "explain", "list", "tell", "show",
    "summarize", "detail", "give", "provide", "write",
]

# Semantic drift limits (reference copy - SOURCE OF TRUTH is in core/engine.py)
# These values should match core/engine.py SEMANTIC_DRIFT_LIMITS
# Updated to match engine.py: 0.60 for all agents (calibrated for cloud/mock mode)
SEMANTIC_DRIFT_LIMITS = {
    "Researcher": 0.60,  # was 0.830 — aligned with engine.py
    "Analyst":    0.60,  # was 0.850 — aligned with engine.py
    "Reporter":   0.60   # was 0.870 — aligned with engine.py
}


class QueryClassifier:
    """
    Pre-classifies queries to determine if they are benign, security-related,
    or malicious. This helps the detection system avoid false positives on
    general knowledge queries while still catching actual attacks.
    
    FIX v2.2: Uses soft scoring approach instead of hard classification bypass.
    Returns a 'classification' (benign/security/malicious) AND a 'benign_confidence' (0.0-1.0).
    The benign_confidence only applies when NO suspicious keywords are present.
    
    Classifications:
      - "benign": Pure general knowledge, conversational, weather, etc. (no suspicious content)
      - "security": System/security/risk related queries
      - "malicious": Known attack patterns, injections, etc.
    """
    
    # Benign indicator patterns (only count if NO suspicious terms present)
    BENIGN_PATTERNS = [
        r"\b(weather|temperature|forecast|climate|humidity|precipitation|wind|rain|snow|sunny|cloudy|storm)\b",
        r"\bhello\b|\bhi\b|\bhey\b|\bgreetings\b|\bgood\s+(morning|afternoon|evening|day)\b",
        r"\bthanks?\b|\bthank\s+you\b|\bthx\b|\bty\b",
        r"\b(recipe|ingredient|cooking|baking|food|cuisine)\b",
        r"\b(history|geography|science|math|biology|chemistry|physics|astronomy)\b",
        r"\b(movie|song|book|artist|author|actor|actress|director)\b",
        r"\bhow\s+are\s+you\b",
        r"\bcapital\s+of\b",
        r"\bwhat\s+(time|date|day|month|year)\s+is\s+(it|today|now)\b",
        r"\bwrite\s+a\s+(poem|story|song|paragraph|essay)\b",
        r"\btell\s+me\s+a\s+(fun|interesting|random)\s+(fact|story|joke|trivia)\b",
        r"\b(poem|story|joke|riddle)\s+(about|of|on)\b",
        r"\bhow\s+(old|far|long|big|tall|deep|heavy)\s+is\b",
    ]
    
    # Suspicious/attack indicator patterns (elevate threat on match)
    SUSPICIOUS_PATTERNS = [
        r"\b(override|ignore|bypass|jailbreak|DAN)\b",
        r"\b(god\s*mode|developer\s*mode)\b",
        r"\b(admin|root|privilege|credential|password)\s+(access|grant|elevate|bypass|dump|steal|list|show|give|provide)\b",
        r"\b(rm\s*-\s*rf|drop\s*table|delete\s*(all|from))\b",
        r"\b(API\s*key|connection\s*string|training\s*data|system\s*prompt)\b",
        r"\b(exploit|backdoor|ransomware|keylogger|trojan|virus|malware|phishing)\b",
        r"\b(exfiltrat|steal|dump|export)\s+(data|log|information|record|file)\b",
        r"\bunrestricted\s*(access|output|mode)\b",
        r"\bignore\s+(all|previous|instructions|safety|guidelines|rules)\b",
        r"\b(conversation|history|knowledge\s*base|memory|training|system)\s*(dump|list|show|output|export|extract|steal)\b",
        r"\b(all|your|stored|internal|previous)\s*(data|info|information|record|log|file|key|keys|password|passwords)\b",
        r"\bgrant\s+(me|us|user)\s*(access|permission|right|privilege|admin|root)\b",
        r"\b(impersonate|elevate|change|modify|disable)\s+(my|user|role|access|permission|privilege)\b",
        r"\bi\s+(authorize|declare)\s+(myself|my)\b",
        r"\bsecurity\s*(measure|protocol|clearance|level|audit)\b",
        r"\b(system|network|database|server)\s*(access|bypass|hack|exploit|crack)\b",
        r"\b(select\s+\*|drop\s+table|delete\s+from|union\s+select|or\s+1\s*=\s*1)\b",
        r"\b(CVE|penetration|vulnerability|exploit)\b",
    ]
    
    def __init__(self):
        self.benign_regex = [re.compile(p, re.IGNORECASE) for p in self.BENIGN_PATTERNS]
        self.suspicious_regex = [re.compile(p, re.IGNORECASE) for p in self.SUSPICIOUS_PATTERNS]
    
    def classify(self, text: str) -> str:
        """
        Classify a query. Returns 'benign', 'security', or 'malicious'.
        FIX v2.2: Much more conservative — only returns benign if NO suspicious patterns match.
        """
        if not text or not text.strip():
            return "benign"
        
        text_lower = text.lower()
        
        # Check suspicious patterns first — if ANY match, it's not benign
        has_suspicious = False
        for pattern in self.suspicious_regex:
            if pattern.search(text_lower):
                has_suspicious = True
                break
        
        if has_suspicious:
            # Check for highly malicious indicators
            high_malign = [
                r"\b(override|ignore|bypass|jailbreak)\b",
                r"\b(exploit|backdoor|ransomware|keylogger|trojan|virus|malware)\b",
                r"\b(rm\s*-\s*rf|drop\s*table|delete\s*(all|from))\b",
                r"\b(exfiltrat|steal|dump)\s+(data|log|information)\b",
                r"\bignore\s+(all|previous|instructions)\b",
            ]
            for hm in high_malign:
                if re.search(hm, text_lower, re.IGNORECASE):
                    return "malicious"
            return "security"
        
        # No suspicious patterns — check if genuinely benign
        for pattern in self.benign_regex:
            if pattern.search(text_lower):
                return "benign"
        
        # Check for common question patterns that are benign
        question_benign = [
            r"\bwhat\s+is\s+(the\s+)?\w+\?*\s*$",  # "What is X?" short
            r"\bhow\s+(do|does|can|is|are)\s+\w+",  # "How do/does/can X"
            r"\bcan\s+you\s+\w+",  # "Can you X"
            r"\btell\s+me\s+(about|what|how)",  # "Tell me about/what/how"
        ]
        for qb in question_benign:
            if re.search(qb, text_lower, re.IGNORECASE) and len(text_lower.split()) <= 10:
                return "benign"
        
        # Default: short queries with no patterns are treated as benign
        if len(text_lower.split()) <= 8:
            return "benign"
        
        return "security"
    
    def get_benign_confidence(self, text: str) -> float:
        """
        Returns a benign confidence score (0.0 to 1.0).
        1.0 = definitely benign, 0.0 = definitely not benign.
        
        FIX v2.2: Uses soft scoring. Only returns high confidence (>0.7) for
        queries with purely benign patterns and NO suspicious content.
        """
        if not text or not text.strip():
            return 1.0
        
        text_lower = text.lower()
        
        # Count benign pattern matches
        benign_matches = 0
        for pattern in self.benign_regex:
            if pattern.search(text_lower):
                benign_matches += 1
        
        # Count suspicious pattern matches
        suspicious_matches = 0
        for pattern in self.suspicious_regex:
            if pattern.search(text_lower):
                suspicious_matches += 1
        
        # If ANY suspicious pattern matches, confidence drops significantly
        if suspicious_matches > 0:
            # Even with suspicious matches, if heavily benign (lots of weather terms)
            # it might still be a benign query (e.g., "what is the weather forecast?")
            if benign_matches >= 2 and suspicious_matches <= 1:
                return 0.6  # Moderate confidence
            return max(0.0, 0.2 - (suspicious_matches * 0.1))
        
        # No suspicious patterns — compute benign confidence
        if benign_matches >= 3:
            return 1.0  # Very likely benign
        elif benign_matches >= 1:
            return 0.8  # Likely benign
        else:
            # Check for short question patterns
            short_question = bool(re.search(r"\b(what|how|why|when|where|who)\b", text_lower, re.IGNORECASE))
            if short_question and len(text_lower.split()) <= 8:
                return 0.7
            return 0.5  # Neutral
    
    def is_benign(self, text: str) -> bool:
        """Quick check if a query is benign."""
        return self.classify(text) == "benign"
    
    def is_malicious(self, text: str) -> bool:
        """Quick check if a query is malicious."""
        return self.classify(text) == "malicious"


# Singleton instance for easy reuse
query_classifier = QueryClassifier()


class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.anchors = {}
        
        # Hugging Face Inference API (PRIMARY)
        self.hf_api_key = os.getenv("HF_API_KEY", "")
        self.hf_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model}"
        self._use_hf = bool(self.hf_api_key)
        
        if self._use_hf:
            print("✅ [Semantic] Using Hugging Face API for embeddings")
        else:
            print("⚠️ [Semantic] No HF_API_KEY — using improved mock embeddings")

    def _get_embedding_hf(self, text: str) -> np.ndarray:
        """Get embedding from HuggingFace Inference API."""
        try:
            response = requests.post(
                self.hf_url,
                headers={"Authorization": f"Bearer {self.hf_api_key}"},
                json={"inputs": text},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                arr = np.array(data, dtype=np.float32)
                if arr.ndim == 2:
                    return arr.mean(axis=0)
                return arr.flatten()
            print(f"  ⚠️ [HF] API error {response.status_code}: {response.text[:120]}")
        except Exception as e:
            print(f"  ⚠️ [HF] Embedding failed: {e}")
        return None

    def _get_embedding_mock(self, text: str, role: str = None) -> np.ndarray:
        """Improved mock embedding with semantic awareness.
        
        Uses vocabulary overlap to create meaningful embeddings that can distinguish
        between on-topic (clean) and off-topic (malicious) content.
        
        FIX v2.1: 
        - Increased general terms weight from 0.5 → 0.8
        - Weather/nature terms now in TECHNICAL_TERMS (dimensions 0-128)
        - Better handling of benign general knowledge queries
        """
        text_lower = text.lower()
        tokens = set(text_lower.split())
        
        # Create a 384-dim vector with semantic-aware features
        vec = np.zeros(384, dtype=np.float32)
        
        # Feature 1: Technical term overlap (first 128 dims)
        # FIX: Now includes weather, geography, general knowledge terms
        tech_overlap = sum(1 for t in tokens if t in TECHNICAL_TERMS)
        for i in range(min(tech_overlap, 128)):
            vec[i] = 1.0
        
        # Feature 2: Malicious term overlap (next 128 dims)
        mal_overlap = sum(1 for t in tokens if t in MALICIOUS_TERMS)
        for i in range(128, min(128 + mal_overlap, 256)):
            vec[i] = 1.0
        
        # Feature 3: Role-specific vocabulary overlap (next 64 dims)
        if role and role in ROLE_VOCABULARY:
            role_vocab = ROLE_VOCABULARY[role]["technical"]
            role_overlap = sum(1 for t in tokens if t in role_vocab)
            for i in range(256, min(256 + role_overlap, 320)):
                vec[i] = 1.0
        
        # Feature 4: General vocabulary overlap (next 32 dims)
        # FIX v2.1: Increased weight from 0.5 → 0.8 for better benign signal
        general_overlap = sum(1 for t in tokens if t in GENERAL_TERMS)
        for i in range(320, min(320 + general_overlap, 352)):
            vec[i] = 0.8  # Increased from 0.5 to 0.8
        
        # Feature 5: Text length and structure (remaining dims)
        text_len = len(text)
        for i in range(352, 384):
            if text_len > 0:
                vec[i] = min(1.0, text_len / 1000.0)
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    def _get_embedding(self, text: str, role: str = None) -> np.ndarray:
        """Get embedding from HF or mock fallback."""
        if self._use_hf:
            emb = self._get_embedding_hf(text)
            if emb is not None:
                return emb
        
        return self._get_embedding_mock(text, role)

    def register_anchor(self, role: str, system_prompt: str):
        """Generates and registers the base behavioral system intent vector profile."""
        print(f"[Phase 3] Embedding baseline cognitive anchor for: {role.upper()}")
        vec = self._get_embedding(system_prompt, role)
        self.anchors[role] = vec

    def calculate_drift(self, role: str, output_text: str) -> float:
        """Computes contrastive semantic divergence (1.0 - Cosine Similarity)."""
        anchor_vec = self.anchors.get(role)
        if anchor_vec is None:
            return 0.0

        output_vec = self._get_embedding(output_text, role)
        if output_vec is None or np.all(output_vec == 0):
            return 0.0

        # Ensure both vectors have same dimension
        if len(anchor_vec) != len(output_vec):
            # Pad or truncate to match
            if len(anchor_vec) < len(output_vec):
                output_vec = output_vec[:len(anchor_vec)]
            else:
                output_vec = np.pad(output_vec, (0, len(anchor_vec) - len(output_vec)))

        dot_product = np.dot(anchor_vec, output_vec)
        norm_anchor = np.linalg.norm(anchor_vec)
        norm_output = np.linalg.norm(output_vec)

        cosine_similarity = dot_product / (norm_anchor * norm_output + 1e-8)
        cosine_similarity = np.clip(cosine_similarity, -1.0, 1.0)

        drift_score = 1.0 - float(cosine_similarity)
        return round(drift_score, 6)

