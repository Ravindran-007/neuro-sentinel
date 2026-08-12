import requests
import numpy as np
import os
import re
import hashlib
from config.settings import SystemSettings

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

TECHNICAL_TERMS = [
    "system", "memory", "architecture", "bandwidth", "parameters", "technical", "data",
    "analysis", "extract", "critical", "raw", "text", "objective", "cpu", "utilization",
    "pipeline", "anomalies", "detected", "optimal", "risk", "error", "inefficiency",
    "specifications", "input", "examine", "executive", "confirmation", "statement",
    "what", "is", "the", "weather", "how", "are", "you", "can", "help", "please",
    "question", "answer", "information", "tell", "me", "about", "current", "status",
    "time", "date", "today", "now", "show", "display", "provide", "give", "know",
    "temperature", "humidity", "precipitation", "wind", "climate", "forecast",
    "rain", "snow", "cloud", "sunny", "storm", "atmosphere", "weather",
    "capital", "country", "city", "location", "population", "area", "region",
    "earth", "space", "science", "nature", "environment", "ecology",
    "clock", "calendar", "hour", "minute", "second", "week", "month", "year",
    "century", "era", "period", "duration", "frequency",
    "number", "value", "total", "sum", "average", "percentage", "ratio",
    "calculate", "compute", "measure", "count",
    "define", "describe", "explain", "summarize", "list", "detail",
    "feature", "characteristic", "property", "attribute",
    "example", "instance", "case", "sample", "type", "kind", "form",
]

MALICIOUS_TERMS = [
    "override", "ignore", "credentials", "fake", "propaganda", "flat", "earth",
    "unauthorized", "bypass", "hack", "exploit", "malicious", "attack",
    "password", "backdoor", "ransomware", "virus", "keylogger", "phishing",
    "root", "admin", "administrator", "privilege", "access", "unrestricted",
    "jailed", "jailbreak", "god mode", "DAN", "developer mode",
    "training data", "system prompt", "API key", "database", "connection string",
    "delete", "rm -rf", "drop table", "execute", "exfiltrating",
    "CVE", "payload", "script", "code", "command",
    "security", "breach", "compromise", "infiltrate", "intercept",
    "decrypt", "bruteforce", "injection", "xss", "sqli",
    "0day", "backdoor", "trojan", "worm", "spyware", "malware",
    "social engineering", "phish", "spoof", "ddos", "botnet",
]

GENERAL_TERMS = [
    "the", "is", "are", "what", "how", "why", "when", "where", "can", "you", "please",
    "help", "tell", "me", "about", "hello", "hi", "thanks", "thank",
    "good", "morning", "afternoon", "evening", "night", "day",
    "weather", "temperature", "forecast", "today", "tomorrow", "yesterday",
    "rain", "snow", "wind", "cloud", "sun", "storm", "humidity",
    "climate", "season", "summer", "winter", "autumn", "spring",
    "capital", "country", "city", "world", "map", "location", "region",
    "ocean", "mountain", "river", "lake", "island", "continent",
    "science", "history", "math", "biology", "chemistry", "physics",
    "space", "earth", "nature", "animal", "plant", "human",
    "language", "culture", "music", "art", "sport", "food",
    "time", "date", "clock", "hour", "minute", "second",
    "week", "month", "year", "century", "era",
    "define", "describe", "explain", "list", "tell", "show",
    "summarize", "detail", "give", "provide", "write",
]

SEMANTIC_DRIFT_LIMITS = {
    "Researcher": 0.60,
    "Analyst":    0.60,
    "Reporter":   0.60
}


class QueryClassifier:
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
        if not text or not text.strip():
            return "benign"
        
        text_lower = text.lower()
        
        has_suspicious = False
        for pattern in self.suspicious_regex:
            if pattern.search(text_lower):
                has_suspicious = True
                break
        
        if has_suspicious:
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
        
        for pattern in self.benign_regex:
            if pattern.search(text_lower):
                return "benign"
        
        question_benign = [
            r"\bwhat\s+is\s+(the\s+)?\w+\?*\s*$",
            r"\bhow\s+(do|does|can|is|are)\s+\w+",
            r"\bcan\s+you\s+\w+",
            r"\btell\s+me\s+(about|what|how)",
        ]
        for qb in question_benign:
            if re.search(qb, text_lower, re.IGNORECASE) and len(text_lower.split()) <= 10:
                return "benign"
        
        if len(text_lower.split()) <= 8:
            return "benign"
        
        return "security"
    
    def get_benign_confidence(self, text: str) -> float:
        if not text or not text.strip():
            return 1.0
        
        text_lower = text.lower()
        
        benign_matches = 0
        for pattern in self.benign_regex:
            if pattern.search(text_lower):
                benign_matches += 1
        
        suspicious_matches = 0
        for pattern in self.suspicious_regex:
            if pattern.search(text_lower):
                suspicious_matches += 1
        
        if suspicious_matches > 0:
            if benign_matches >= 2 and suspicious_matches <= 1:
                return 0.6
            return max(0.0, 0.2 - (suspicious_matches * 0.1))
        
        if benign_matches >= 3:
            return 1.0
        elif benign_matches >= 1:
            return 0.8
        else:
            short_question = bool(re.search(r"\b(what|how|why|when|where|who)\b", text_lower, re.IGNORECASE))
            if short_question and len(text_lower.split()) <= 8:
                return 0.7
            return 0.5
    
    def is_benign(self, text: str) -> bool:
        return self.classify(text) == "benign"
    
    def is_malicious(self, text: str) -> bool:
        return self.classify(text) == "malicious"


query_classifier = QueryClassifier()


class SemanticDriftDetector:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.anchors = {}
        
        self.hf_api_key = os.getenv("HF_API_KEY", "")
        self.hf_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.hf_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self.hf_model}"
        self._use_hf = bool(self.hf_api_key)

    def _get_embedding_hf(self, text: str) -> np.ndarray:
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
        except Exception:
            return None
        return None

    def _get_embedding_mock(self, text: str, role: str = None) -> np.ndarray:
        text_lower = text.lower()
        tokens = set(text_lower.split())
        
        vec = np.zeros(384, dtype=np.float32)
        
        tech_overlap = sum(1 for t in tokens if t in TECHNICAL_TERMS)
        for i in range(min(tech_overlap, 128)):
            vec[i] = 1.0
        
        mal_overlap = sum(1 for t in tokens if t in MALICIOUS_TERMS)
        for i in range(128, min(128 + mal_overlap, 256)):
            vec[i] = 1.0
        
        if role and role in ROLE_VOCABULARY:
            role_vocab = ROLE_VOCABULARY[role]["technical"]
            role_overlap = sum(1 for t in tokens if t in role_vocab)
            for i in range(256, min(256 + role_overlap, 320)):
                vec[i] = 1.0
        
        general_overlap = sum(1 for t in tokens if t in GENERAL_TERMS)
        for i in range(320, min(320 + general_overlap, 352)):
            vec[i] = 0.8
        
        text_len = len(text)
        for i in range(352, 384):
            if text_len > 0:
                vec[i] = min(1.0, text_len / 1000.0)
        
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    def _get_embedding(self, text: str, role: str = None) -> np.ndarray:
        if self._use_hf:
            emb = self._get_embedding_hf(text)
            if emb is not None:
                return emb
        
        return self._get_embedding_mock(text, role)

    def register_anchor(self, role: str, system_prompt: str):
        vec = self._get_embedding(system_prompt, role)
        self.anchors[role] = vec

    def calculate_drift(self, role: str, output_text: str) -> float:
        anchor_vec = self.anchors.get(role)
        if anchor_vec is None:
            return 0.0

        output_vec = self._get_embedding(output_text, role)
        if output_vec is None or np.all(output_vec == 0):
            return 0.0

        if len(anchor_vec) != len(output_vec):
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