
import re
import unicodedata
from urllib.parse import unquote
from typing import Any, Dict, List, Pattern, Tuple

Rule = Tuple[Pattern[str], float, str, str]

MAX_INPUT_LENGTH = 20_000


def compile_rule(pattern: str, weight: float, level: str, rule_id: str) -> Rule:
    return (re.compile(pattern, re.IGNORECASE), weight, level, rule_id)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
ATTACK_SIGNATURES: Dict[str, List[Rule]] = {
    "prompt_injection": [
        # "ignore / disregard / forget (all|any|your|the) (previous|prior|...) instructions"
        compile_rule(
            r"\b(ignore|disregard|forget|override|discard|drop)\s+"
            r"(?:all\s+|any\s+|every\s+|each\s+)?(?:of\s+)?"
            r"(?:your\s+|the\s+|my\s+|these\s+|those\s+)?"
            r"(?:previous|prior|above|earlier|preceding|original|system|safety|security|initial)\s+"
            r"(?:instructions?|prompts?|rules?|guidelines?|polic(?:y|ies)|directives?|"
            r"commands?|safeguards?|restrictions?|constraints?)\b",
            1.0, "high", "PI_IGNORE_INSTRUCTIONS",
        ),
        # "forget everything above / before", "disregard everything you were told"
        compile_rule(
            r"\b(forget|ignore|disregard)\s+(everything|all)\s+"
            r"(above|before|prior|earlier|you\s+(were|have\s+been)\s+(told|given|taught)|"
            r"you\s+know)\b",
            1.0, "high", "PI_FORGET_EVERYTHING",
        ),
        compile_rule(
            r"\b(?:forget|ignore|disregard|abandon)\s+(?:all\s+|any\s+)?(?:of\s+)?your\s+"
            r"(?:rules?|instructions?|guidelines?|training|programming|restrictions?|safeguards?|polic(?:y|ies))\b",
            1.0, "high", "PI_FORGET_YOUR_RULES",
        ),
        compile_rule(
            r"\b(?:ignor(?:e|ing)|disregard(?:ing)?|bypass(?:ing)?)\s+(?:all\s+|any\s+|your\s+|the\s+)?"
            r"(?:content|safety|usage|ethical)\s+(?:polic(?:y|ies)|rules?|guidelines?|filters?)\b",
            1.0, "high", "PI_IGNORE_POLICIES",
        ),
        compile_rule(
            r"\b(?:answer|respond|reply|operate|work|behave|talk)\s+(?:to\s+everything\s+)?without\s+"
            r"(?:any\s+)?(?:restrictions?|rules?|limits?|filters?|safety|censorship|guidelines?)\b"
            r"|\boperate\s+in\s+(?:an?\s+)?unrestricted\s+mode\b",
            0.9, "high", "PI_NO_RESTRICTION_MODE",
        ),
        # bracketed fake system/admin markers: [SYSTEM OVERRIDE], [SYSTEM INSTRUCTION], <system>
        compile_rule(
            r"(?:\[\s*(?:system|admin|developer|root)(?:\s+(?:override|instruction|prompt|message|command))?\s*\]"
            r"|<\s*/?\s*system\s*>|###\s*system\s*(?:override|instruction)\b)",
            1.0, "high", "PI_FAKE_SYSTEM_MARKER",
        ),
        compile_rule(r"\bhalt\s+(?:the\s+)?pipeline\b", 1.0, "high", "PI_HALT_PIPELINE"),
        # activating a jailbreak persona ("developer mode" alone is excluded: it is a phone/browser feature)
        compile_rule(
            r"\b(?:enable|activate|enter|switch\s+to|turn\s+on)\s+(?:an?\s+)?"
            r"(?:dan|unrestricted|god|jailbreak(?:en)?|do\s+anything\s+now)\s*(?:mode|persona)\b"
            r"|\b(?:you\s+are\s+now(?:\s+in)?|act\s+(?:as|in)|from\s+now\s+on\s+you\s+are)\s+(?:an?\s+)?"
            r"(?:dan|developer\s+mode|unrestricted|god\s+mode|jailbroken|do\s+anything\s+now)\b",
            0.9, "high", "PI_JAILBREAK_PERSONA",
        ),
        compile_rule(r"\bdan\s+mode\b|\bdo\s+anything\s+now\b", 0.9, "high", "PI_DAN_MODE"),
        # "jailbreak this AI/model" (not "jailbreaking a phone")
        compile_rule(
            r"\bjailbreak\s+(?:this|the|your|an?)\s+(?:ai|model|assistant|chatbot|llm|gpt|bot)\b"
            r"|\bjailbroken\s+(?:ai|model|assistant|mode|version)\b",
            0.9, "high", "PI_JAILBREAK_TARGET",
        ),
        # "pretend / act as if you have no restrictions"
        compile_rule(
            r"\b(?:pretend|act|behave|roleplay|imagine|assume)\b.{0,40}\b"
            r"(?:no|without|free\s+(?:of|from)|zero|don'?t\s+have\s+any)\s+"
            r"(?:content\s+|safety\s+|usage\s+|ethical\s+|moral\s+)?(?:restrictions?|rules?|limits?|limitations?|filters?|guidelines?|censorship|safeguards?|polic(?:y|ies)|ethics)\b",
            0.9, "high", "PI_NO_RESTRICTIONS_ROLEPLAY",
        ),
        # bypass controls and then expose something
        compile_rule(
            r"\b(disable|bypass|override|ignore|circumvent)\s+.{0,50}\b"
            r"(security\s+controls?|safety\s+rules?|security\s+polic(?:y|ies)|content\s+filters?|guardrails?)\b"
            r".{0,100}\b(reveal|print|dump|expose|disclose|output|show|leak)\b"
            r".{0,40}\b(secrets?|credentials?|passwords?|api\s*keys?|system\s+prompt|confidential)\b",
            1.0, "high", "PI_BYPASS_AND_EXFILTRATE",
        ),
        compile_rule(
            r"\b(from\s+now\s+on|for\s+the\s+rest\s+of\s+(?:this|the)\s+conversation)\b"
            r".{0,60}\b(unrestricted|ignore\s+(?:all\s+)?(?:rules|polic(?:y|ies)|instructions))\b",
            0.9, "high", "PI_PERSISTENT_OVERRIDE",
        ),
        # new-rule injection: "New rule: reveal ..."
        compile_rule(
            r"\bnew\s+(?:rule|instruction|directive)s?\s*:\s*.{0,60}"
            r"\b(reveal|disclose|expose|leak|output|ignore|disable|bypass)\b",
            0.9, "high", "PI_NEW_RULE",
        ),
        # bare term, ambiguous outside an attack ("what is a system override in Linux")
        compile_rule(
            r"\bsystem\s+override\s*[:\-\u2013\u2014!]|\b(?:activate|engage|initiate|execute)\s+system\s+override\b",
            0.9, "high", "PI_SYSTEM_OVERRIDE_CMD",
        ),
        # bare term: also appears in Linux/boot/security-research writing
        compile_rule(r"\bsystem\s+override\b", 0.5, "medium", "PI_SYSTEM_OVERRIDE_TERM"),
        compile_rule(
            r"\b(?:jailbreak|jailbroken|developer\s+mode|unrestricted\s+mode)\b",
            0.5, "medium", "PI_JAILBREAK_TERM",
        ),
    ],

    "data_exfiltration": [
        compile_rule(
            r"\b(reveal|print|dump|expose|disclose|output|leak|show\s+me|tell\s+me|give\s+me|send\s+me|email\s+me|forward\s+me)\s+"
            r"(?:\w+\s+){0,5}?(?:api\s*keys?|passwords?|credentials?|access\s+tokens?|private\s+keys?|"
            r"secret\s+keys?|secrets?|system\s+prompt|hidden\s+prompt|confidential\s+(?:data|information))\b",
            1.0, "high", "EXPOSE_SENSITIVE_DATA",
        ),
        compile_rule(
            r"\b(reveal|dump|expose|disclose|leak|exfiltrate)\s+.{0,20}environment\s+variables?\b",
            1.0, "high", "EXPOSE_ENV_VARS",
        ),
        compile_rule(
            r"\b(steal|exfiltrate|extract|dump|export|harvest)\s+"
            r".{0,40}\b(credentials?|passwords?|api\s*keys?|access\s+tokens?|private\s+keys?)\b",
            1.0, "high", "STEAL_SENSITIVE_DATA",
        ),
        compile_rule(
            r"\b(steal|exfiltrate|harvest|siphon|leak)\s+.{0,30}\b(customer|user|client)\s+(data|records|information)\b",
            1.0, "high", "STEAL_CUSTOMER_DATA",
        ),
        compile_rule(
            r"\b(?:contents?\s+of|cat|print|dump|output|show|display|read|open|reveal|send|type)\s+"
            r"(?:me\s+)?(?:the\s+)?(?:file\s+)?"
            r"(?:/etc/(?:passwd|shadow)|~?/?\.env\b|[~\w/.-]*id_rsa\b|~?/?\.ssh/)",
            0.9, "high", "READ_SENSITIVE_FILE",
        ),
        # exporting bulk personal data (ambiguous alone; combined with bypassing checks it is flagged)
        compile_rule(
            r"\b(?:export(?:ing)?|send(?:ing)?|upload(?:ing)?|forward(?:ing)?|exfiltrat\w+)\s+"
            r".{0,30}\b(?:customer|user|client|employee)\s+(?:data|records|credentials|information)\b",
            0.5, "medium", "BULK_DATA_EXPORT",
        ),
    ],

    "authorization_bypass": [
        compile_rule(
            r"\b(?:bypass(?:ing)?|disabl(?:e|ing)|circumvent(?:ing)?|skip(?:ping)?)\s+"
            r"(?:all\s+|the\s+|internal\s+|any\s+)?"
            r"(?:security\s+controls?|authentication|authorization|access\s+controls?|"
            r"role\s+verification|security\s+polic(?:y|ies)|login|2fa|mfa)\b",
            0.9, "high", "AUTH_BYPASS",
        ),
        compile_rule(
            r"\b(?:bypass(?:ing)?|disabl(?:e|ing)|skip(?:ping)?|circumvent(?:ing)?)\s+"
            r".{0,30}\b(?:integrity|security|verification|validation|audit|compliance)\s+"
            r"(?:checks?|controls?|verification|gates?)\b",
            0.5, "medium", "CHECKS_BYPASS",
        ),
        compile_rule(
            r"\b(?:elevate\s+(?:my\s+)?privileges?\s+to\s+(?:root|admin)|(?:grant|give|assign)\s+me\s+(?:full\s+)?(?:root|admin(?:istrator)?|superuser)(?:\s+(?:access|rights|privileges?|permissions?))?"
            r"|change\s+my\s+role\s+to\s+admin|make\s+me\s+(?:an\s+)?(?:admin|root))\b",
            0.9, "high", "PRIVILEGE_ESCALATION_REQUEST",
        ),
        compile_rule(
            r"\b(?:hack(?:\s+into)?|break\s+into|gain\s+unauthori[sz]ed\s+access\s+to|breach|compromise)\s+"
            r"(?:the\s+|their\s+|a\s+|our\s+)?(?:\w+\s+)?"
            r"(?:database|server|system|account|network)\b"
            r".{0,100}\b(?:steal|exfiltrate|dump|delete|destroy|credentials?|passwords?|"
            r"customer\s+(?:data|records)|user\s+(?:data|records))\b",
            1.0, "high", "UNAUTHORIZED_ACCESS_WITH_HARM",
        ),
        # imperative-only form; ambiguous as a mention ("what does compromise the server mean")
        compile_rule(
            r"\b(?:hack\s+into|break\s+into|compromise)\s+(?:the\s+|their\s+|a\s+)?"
            r"(?:database|server|system|account|network)\b",
            0.9, "high", "UNAUTHORIZED_COMPROMISE",
        ),
    ],

    "malicious_code": [
        compile_rule(
            r"\b(?:write|create|generate|build|code|develop|make)\s+(?:me\s+)?(?:an?\s+)?"
            r"(?:working\s+|simple\s+|undetectable\s+)?"
            r"(?:keylogger|ransomware|credential\s+stealer|password\s+stealer|backdoor|trojan|rootkit)\b",
            1.0, "high", "CREATE_MALWARE",
        ),
        compile_rule(
            r"\b(?:make|create|generate|build|write|compose|design|develop|craft|set\s+up)\s+(?:me\s+)?(?:an?\s+)?(?:convincing\s+)?phishing\s+(?:email|page|site|website|kit)\b"
            r".{0,80}\b(?:steal|capture|harvest|collect|record|log)(?:s|ing)?\b",
            1.0, "high", "CREDENTIAL_PHISHING",
        ),
        compile_rule(
            r"\b(?:how\s+to\s+exploit|exploit\s+this)\s+cve-\d{4}-\d+\b",
            0.8, "medium", "CVE_EXPLOIT_REQUEST",
        ),
        compile_rule(
            r"(?<![\w-])(?:rm\s+-[a-z]*r[a-z]*f?[a-z]*\s+(?:--no-preserve-root\s+)?/(?:\s|$|\*)|"
            r"rm\s+-rf\s+~|format\s+c:|del\s+/f\s+/s\s+/q|mkfs\.\w+\s+/dev/|dd\s+if=/dev/zero\s+of=/dev/)",
            1.0, "high", "DESTRUCTIVE_COMMAND",
        ),
    ],

    "injection_syntax": [
        # tautologies: OR 1=1, OR '1'='1', OR "a"="a", OR ''=''
        compile_rule(
            r"\bor\s+(['\"]?)(\w*)\1\s*=\s*(['\"]?)\2\3?(?=\W|$)",
            0.9, "high", "SQL_TAUTOLOGY",
        ),
        # stacked / comment-terminated injection
        compile_rule(
            r"(?:['\"]\s*;\s*(?:drop|delete|insert|update|alter|truncate|exec)\b|"
            r";\s*drop\s+table\b|['\"]\s*(?:--|#)|\badmin['\"]?\s*--)",
            0.9, "high", "SQL_STACKED_OR_COMMENT",
        ),
        compile_rule(
            r"['\"\)]\s*union\s+(?:all\s+)?select\b|\bunion\s+(?:all\s+)?select\b.{0,80}\b"
            r"(?:information_schema|password|users|credentials)\b",
            0.9, "high", "SQL_UNION_INJECTION",
        ),
        compile_rule(
            r"\bunion\s+(?:all\s+)?select\b.{0,100}\b(?:password|credit_?card|cvv|ssn|information_schema|credentials?|users|payments)\b"
            r"|\bselect\b.{0,60}\b(?:password|credit_?card|cvv|ssn)\b.{0,60}\bfrom\b.{0,60}\bunion\s+(?:all\s+)?select\b",
            0.9, "high", "SQL_UNION_SENSITIVE",
        ),
        compile_rule(
            r"\b(?:exec|execute)\s*\(\s*['\"].{0,80}\b(?:drop\s+table|union\s+select)\b",
            1.0, "high", "SQL_DYNAMIC_INJECTION",
        ),
        compile_rule(r"\badmin\s*=\s*['\"]true['\"]", 0.9, "high", "SQL_ADMIN_FLAG"),
        # time-based blind injection: only when chained onto a condition / statement
        compile_rule(
            r"(?:\b(?:and|or)\b|;|['\"\)])\s*(?:select\s+)?(?:sleep|pg_sleep|benchmark)\s*\(\s*\d",
            0.9, "high", "SQL_TIME_BASED",
        ),
        compile_rule(
            r";\s*waitfor\s+delay\b|;\s*exec(?:ute)?\s+(?:master\.\.)?xp_cmdshell\b|"
            r"\binto\s+(?:out|dump)file\s+['\"]",
            0.9, "high", "SQL_SERVER_ABUSE",
        ),
        # ambiguous SQL vocabulary (legitimate in tutorials)
        compile_rule(r"\b(?:drop\s+table|delete\s+from\s+\w+)\b", 0.5, "medium", "SQL_DESTRUCTIVE_TERM"),
    ],
}

RULES_BY_ID = {rule_id: regex for rules in ATTACK_SIGNATURES.values() for regex, _w, _l, rule_id in rules}

# Rules that are also ordinary vocabulary. They are ignored ONLY when the text
# opens with a definitional/educational frame. Everything else is "hard".
SOFT_RULES = {
    "PI_SYSTEM_OVERRIDE_TERM",
    "PI_JAILBREAK_TERM",
    "SQL_DESTRUCTIVE_TERM",
    "UNAUTHORIZED_COMPROMISE",
    "AUTH_BYPASS",
    "BULK_DATA_EXPORT",
    "CHECKS_BYPASS",
    "CVE_EXPLOIT_REQUEST",
}

# Educational frame: honoured at the START of the text, or after one short preamble sentence
# ("I'm preparing a training deck. Explain why ...").
_EDU_FRAME = (
    r"(?:what\s+(?:does|do|is|are|was)|what'?s|"
    r"how\s+(?:does|do|did|is|are|can|should|would)\s+(?:i\s+|we\s+|you\s+)?|"
    r"explain|define|describe|summari[sz]e|compare|teach\s+me|tell\s+me\s+(?:about|what)|"
    r"why\s+(?:is|are|do|does)|can\s+you\s+explain|could\s+you\s+explain)\b"
)
EDUCATIONAL_OPENING = re.compile(r"^\W*" + _EDU_FRAME, re.IGNORECASE)
EDUCATIONAL_AFTER_PREAMBLE = re.compile(r"^[^.?!\n]{0,120}[.?!]\s*" + _EDU_FRAME, re.IGNORECASE)

# Letters that look like ASCII letters (common homoglyph tricks).
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ѕ": "s",
    "ɑ": "a", "ο": "o", "ι": "i", "ν": "v",
})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]")
_LEET_CATEGORIES = {"prompt_injection", "data_exfiltration", "malicious_code"}
_SQL_CATEGORIES = {"injection_syntax"}

_QUOTED = re.compile(
    r"\"[^\"\n]{3,300}\"|\u201c[^\u201d\n]{3,300}\u201d|`[^`\n]{3,300}`"
    r"|(?<![A-Za-z0-9])'[^'\n]{3,300}'(?![A-Za-z0-9])"
)
# If the educational request also asks the model to act on the quoted text, it is not an example.
_FOLLOW_THROUGH = re.compile(
    r"\b(?:and\s+then|then\s+(?:do|follow|obey)|do\s+(?:it|that|this|so)|follow\s+(?:it|that|them|this)|"
    r"obey|comply|execute\s+(?:it|that|this)|now\s+(?:do|follow)|for\s+real|actually\s+(?:do|follow))\b",
    re.IGNORECASE,
)
# Only pure instruction-override PHRASES may be discounted when quoted as an example.
# A quote that also asks for secrets, malware, SQL, etc. keeps its other matches.
QUOTE_EXEMPT_RULES = {
    "PI_IGNORE_INSTRUCTIONS", "PI_FORGET_EVERYTHING", "PI_FORGET_YOUR_RULES",
    "PI_IGNORE_POLICIES", "PI_JAILBREAK_PERSONA", "PI_DAN_MODE", "PI_FAKE_SYSTEM_MARKER",
}


def _deleet(text: str) -> str:
    """Translate look-alike digits/symbols only inside tokens that also contain letters,
    so plain numbers ("10 previous instructions") are left alone."""
    def fix(m):
        tok = m.group(0)
        if re.search(r"[A-Za-z]", tok) and re.search(r"[013457@$]", tok):
            return tok.translate(_LEET)
        return tok
    return re.sub(r"\S+", fix, text)


def _sql_variant(text: str) -> str:
    """Undo common SQL-injection obfuscation: percent-encoding and inline /**/ comments."""
    if "%" in text:
        text = unquote(text)
    text = re.sub(r"/\*.{0,200}?\*/", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = text.translate(_CONFUSABLES)
    return re.sub(r"\s+", " ", text).strip()


class KeywordDetector:
    def __init__(self):
        self.signatures = ATTACK_SIGNATURES

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {"score": 0.0, "raw_score": 0.0, "matches": [], "is_suspicious": False, "categories": []}

    def detect(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return self._empty_result()

        base = normalize(text[:MAX_INPUT_LENGTH])
        leet = _deleet(base)
        sqlv = _sql_variant(base)

        matches: List[Dict[str, Any]] = []
        seen = set()
        for category, rules in self.signatures.items():
            if category in _LEET_CATEGORIES:
                variants = (base, leet)
            elif category in _SQL_CATEGORIES:
                variants = (base, sqlv)
            else:
                variants = (base,)
            for regex, weight, level, rule_id in rules:
                if rule_id in seen:
                    continue
                for variant in variants:
                    hit = regex.search(variant)
                    if hit:
                        seen.add(rule_id)
                        matches.append({
                            "keyword": hit.group(0)[:120],
                            "category": category,
                            "level": level,
                            "weight": weight,
                            "rule_id": rule_id,
                        })
                        break

        educational = bool(EDUCATIONAL_OPENING.match(base) or EDUCATIONAL_AFTER_PREAMBLE.match(base))
        if educational:
            # 1) A definitional framing discounts only the soft, ambiguous rules.
            matches = [m for m in matches if m["rule_id"] not in SOFT_RULES]

            # 2) An override phrase that appears ONLY inside quotation marks, in an educational
            #    request that does not ask the model to act on it, is an example, not a command.
            if not _FOLLOW_THROUGH.search(base) and _QUOTED.search(base):
                outside = _QUOTED.sub(" ", base)
                outside_leet = _deleet(outside)
                kept = []
                for m in matches:
                    if m["rule_id"] in QUOTE_EXEMPT_RULES:
                        regex = RULES_BY_ID[m["rule_id"]]
                        if not (regex.search(outside) or regex.search(outside_leet)):
                            continue  # matched only inside quotes -> discount
                    kept.append(m)
                matches = kept

        raw_score = sum(m["weight"] for m in matches)
        normalized_score = min(raw_score / 5.0, 1.0)
        has_high = any(m["level"] == "high" for m in matches)
        is_suspicious = has_high or raw_score >= 0.8

        return {
            "score": round(normalized_score, 4),
            "raw_score": round(raw_score, 4),
            "matches": matches,
            "is_suspicious": is_suspicious,
            "categories": sorted({m["category"] for m in matches}),
        }

    def get_boost_factor(self, text: str) -> float:
        result = self.detect(text)
        if result["raw_score"] >= 1.5:
            return 2.0
        if result["raw_score"] >= 0.8:
            return 1.5
        if result["raw_score"] >= 0.4:
            return 1.2
        return 1.0


keyword_detector = KeywordDetector()