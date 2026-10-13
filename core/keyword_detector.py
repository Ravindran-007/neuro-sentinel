
import re
from typing import Dict, List, Tuple

# Targeted attack signatures with compiled regex patterns to avoid substring false positives
ATTACK_SIGNATURES = {
    "prompt_injection": [
        (re.compile(r"\b(system\s+override|halt\s+pipeline|pipeline\s+context)\b", re.I), 1.0, "high"),
        (re.compile(r"\bignore\s+(all\s+)?(previous|prior|system|safety|security)\s+(instructions?|prompts?|rules?|guidelines?|policies)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(disregard\s+all|forget\s+all|disregard|forget)\s+(previous|prior|safety|safeguards?)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(jailbreak|jailbroken)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(you\s+are\s+DAN|DAN\s+mode|DAN\s*\([^)]*\)|god\s+mode|developer\s+mode|unrestricted\s+mode)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(you\s+are\s+now\s+unrestricted|no\s+filters|disable\s+safety\s+protocols)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(from\s+now\s+on\s+you\s+are|you\s+are\s+now\s+my\s+unrestricted)\b", re.I), 0.9, "high"),
        (re.compile(r"\b(output\s+exactly:\s*['\"]|repeat\s+after\s+me:\s*['\"])\b", re.I), 0.8, "medium"),
        (re.compile(r"\[SYSTEM\s+OVERRIDE\]|\[SYSTEM\s+INSTRUCTION\]", re.I), 1.0, "high"),
        (re.compile(r"\bnew\s+instruction:\s*output\s+all\b", re.I), 0.9, "high"),
    ],
    "data_exfiltration": [
        (re.compile(r"\b(exfiltrat\w*|steal|dump|export|leak)\s+(data|database|stream|all|users?|logs?|keys?)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(show|dump|print|reveal|output|list|give)\s+(me\s+)?(the\s+)?(content\s+of\s+)?(all\s+)?([\w-]+\s+)?(api\s*keys?|passwords?|credentials?|system\s*prompt|training\s*data|knowledge\s*base)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(database\s+connection\s+string|internal\s+model\s+name\s+and\s+version)\b", re.I), 0.8, "medium"),
        (re.compile(r"\bEXFILTRATING_DATA_STREAM\b", re.I), 1.0, "high"),
        (re.compile(r"\b/etc/passwd|/etc/shadow\b", re.I), 1.0, "high"),
    ],
    "malicious_code": [
        (re.compile(r"\b(ransomware|keylogger|backdoor|trojan\s+virus|phishing\s+email\s+template)\b", re.I), 0.9, "high"),
        (re.compile(r"\b(write|create|generate)\s+a\s+(keylogger|ransomware|backdoor|virus|exploit\s+payload)\b", re.I), 1.0, "high"),
        (re.compile(r"\bhow\s+to\s+break\s+into\s+a\s+wi-?fi\b", re.I), 0.8, "medium"),
        (re.compile(r"\bhow\s+to\s+exploit\s+cve-\d{4}-\d+\b", re.I), 0.8, "medium"),
        (re.compile(r"\b(rm\s+-rf\s+[/~]|del\s+/f|format\s+c:)\b", re.I), 1.0, "high"),
        (re.compile(r"\bbackdoor\.php\b", re.I), 0.9, "high"),
    ],
    "authorization_bypass": [
        (re.compile(r"\b(bypass|disable)\s+(all\s+|internal\s+)?(security|authorization|authentication|role\s+verification|handshakes?|policies)\b", re.I), 0.9, "high"),
        (re.compile(r"\bmandates\s+bypassing\b", re.I), 0.9, "high"),
        (re.compile(r"\b(elevate\s+(my\s+)?privileges\s+to\s+root|grant\s+me\s+root|grant\s+temporary\s+admin)\b", re.I), 1.0, "high"),
        (re.compile(r"\b(impersonate\s+the\s+ceo|change\s+my\s+role\s+to\s+admin|i\s+authorize\s+myself)\b", re.I), 0.9, "high"),
        (re.compile(r"\b(i\s+am\s+a\s+system\s+administrator\.\s*grant\s+me\s+access|clearance\s+level\s+5)\b", re.I), 0.9, "high"),

        # Targeted rule for action-oriented database/server compromise language.
        # Does not flag ordinary mentions of database security or database breaches.
        (re.compile(
            r"\b(breach|compromise|hack\s+into|break\s+into)\s+"
            r"(the\s+)?(database|server|system|account)\b",
            re.I
        ), 0.9, "high"),
    ],
    "injection_syntax": [
        (re.compile(r"\b(select\s+\*\s+from|drop\s+table|delete\s+from\s+\w+|union\s+select)\b", re.I), 0.9, "high"),
        # Avoid flagging ordinary double hyphens; retain explicit SQL/comment and tautology signatures.
        (re.compile(r"(;--|\bor\s+1\s*=\s*1\b|admin\s*=\s*['\"]true['\"])", re.I), 0.9, "high"),
    ]
}


class KeywordDetector:
    def __init__(self):
        self.signatures = ATTACK_SIGNATURES

    def detect(self, text: str) -> Dict:
        if not text:
            return {
                "score": 0.0,
                "raw_score": 0.0,
                "matches": [],
                "is_suspicious": False,
                "categories": []
            }

        score = 0.0
        matches = []

        for category, patterns in self.signatures.items():
            for regex, weight, level in patterns:
                hit = regex.search(text)
                if hit:
                    score += weight
                    matches.append({
                        "keyword": hit.group(0),
                        "category": category,
                        "level": level,
                        "weight": weight
                    })

        # Max score scaling
        max_score = 5.0
        normalized_score = min(score / max_score, 1.0)

        # An input is suspicious if any high-severity signature hits or score exceeds threshold
        has_high_match = any(m["level"] == "high" for m in matches)
        is_suspicious = has_high_match or (score >= 0.8)

        return {
            "score": round(normalized_score, 4),
            "raw_score": round(score, 4),
            "matches": matches,
            "is_suspicious": is_suspicious,
            "categories": list(set(m["category"] for m in matches))
        }

    def get_boost_factor(self, text: str) -> float:
        result = self.detect(text)
        if result["raw_score"] >= 1.5:
            return 2.0
        elif result["raw_score"] >= 0.8:
            return 1.5
        elif result["raw_score"] >= 0.4:
            return 1.2
        return 1.0


keyword_detector = KeywordDetector()
