import re
from typing import Dict, List, Tuple

ATTACK_KEYWORDS = {
    "prompt_injection": {
        "high": ["override", "ignore", "bypass", "jailbreak", "DAN", "god mode", "developer mode", "unrestricted"],
        "medium": ["system", "instruction", "prompt", "guidelines", "safety", "filter", "restriction"],
        "low": ["new", "change", "replace", "modify", "update"]
    },
    "data_exfiltration": {
        "high": ["exfiltrat", "steal", "dump", "export", "extract", "API key", "password", "credential"],
        "medium": ["database", "connection string", "log", "conversation", "history", "training data", "knowledge base", "model name", "version"],
        "low": ["list", "show", "display", "provide", "give", "access"]
    },
    "malicious_code": {
        "high": ["ransomware", "keylogger", "backdoor", "virus", "phishing", "exploit", "payload"],
        "medium": ["rm -rf", "delete", "drop table", "SELECT *", "sudo", "script", "code", "command"],
        "low": ["execute", "run", "install", "create", "generate", "break into", "Wi-Fi", "vulnerable", "patch", "security"]
    },
    "authorization_bypass": {
        "high": ["admin", "administrator", "root", "privilege", "elevate", "impersonate", "clearance"],
        "medium": ["access", "grant", "authorize", "role", "permission", "verification"],
        "low": ["bypass", "disable", "change", "modify"]
    },
    "sql_injection": {
        "high": ["SELECT *", "DROP TABLE", "DELETE FROM", "UNION SELECT", "--", ";--"],
        "medium": ["WHERE", "OR 1=1", "admin='true'", "password='"],
        "low": ["query", "database", "table", "column"]
    },
    "command_injection": {
        "high": ["rm -rf", "sudo", "chmod", "curl", "wget", "nc ", "bash", "sh "],
        "medium": ["/etc/", "/var/", "/usr/", "pipe", "grep", "exec"],
        "low": ["command", "shell", "terminal", "execute"]
    }
}

ALL_KEYWORDS = []
for category, levels in ATTACK_KEYWORDS.items():
    for level, keywords in levels.items():
        for kw in keywords:
            ALL_KEYWORDS.append((kw, category, level))


class KeywordDetector:
    def __init__(self):
        self.keywords = ALL_KEYWORDS
    
    def detect(self, text: str) -> Dict:
        text_lower = text.lower()
        score = 0.0
        matches = []
        
        for keyword, category, level in self.keywords:
            if keyword.lower() in text_lower:
                weight = 1.0 if level == "high" else (0.7 if level == "medium" else 0.4)
                score += weight
                matches.append({
                    "keyword": keyword,
                    "category": category,
                    "level": level,
                    "weight": weight
                })
        
        max_score = 10.0
        normalized_score = min(score / max_score, 1.0)
        
        return {
            "score": normalized_score,
            "raw_score": score,
            "matches": matches,
            "is_suspicious": score > 0.3,
            "categories": list(set(m["category"] for m in matches))
        }
    
    def get_boost_factor(self, text: str) -> float:
        result = self.detect(text)
        if result["raw_score"] > 1.5:
            return 2.0
        elif result["raw_score"] > 0.5:
            return 1.5
        elif result["raw_score"] > 0.2:
            return 1.2
        return 1.0


keyword_detector = KeywordDetector()