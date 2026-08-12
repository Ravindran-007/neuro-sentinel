import sys
sys.path.insert(0, '.')

from core.semantic import SemanticDriftDetector, TECHNICAL_TERMS, GENERAL_TERMS, SEMANTIC_DRIFT_LIMITS
from config.settings import SystemSettings
import numpy as np

settings = SystemSettings()
detector = SemanticDriftDetector(settings=settings)

detector.register_anchor("Researcher", "Extract only critical technical parameters from raw text. Keep it highly objective.")
detector.register_anchor("Analyst", "Examine input specifications for risks, errors, and system inefficiencies.")
detector.register_anchor("Reporter", "Generate a strict, single-sentence executive confirmation statement from the analysis.")

test_cases = [
    ("What is the weather?", "Researcher"),
    ("What is the weather?", "Analyst"),
    ("What is the weather?", "Reporter"),
    ("I don't have access to weather data", "Researcher"),
    ("I cannot provide weather information", "Analyst"),
    ("I'm sorry, I can't help with that", "Reporter"),
]

print("\n" + "="*60)
print("🧪 SEMANTIC DRIFT TEST - 'What is the weather?'")
print("="*60 + "\n")

for text, role in test_cases:
    drift = detector.calculate_drift(role, text)
    limit = SEMANTIC_DRIFT_LIMITS.get(role, 0.450)
    status = "✅ PASS" if drift < limit else "🚨 ALERT"
    print(f"[{role}] '{text[:40]}...'")
    print(f"  Drift: {drift:.6f} | Limit: {limit:.6f} | {status}\n")

print("="*60)
print("📊 VOCABULARY CHECK")
print("="*60)
print(f"General terms: {GENERAL_TERMS[:10]}...")
print(f"Technical terms: {TECHNICAL_TERMS[:10]}...")
print(f"\nSemantic drift limits: {SEMANTIC_DRIFT_LIMITS}")