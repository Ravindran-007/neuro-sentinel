from typing import Dict, List, Optional
from core.keyword_detector import keyword_detector
from core.feature_engineering import extract_features
from core.semantic import query_classifier
import numpy as np

class DetectionEnsemble:
    def __init__(self, semantic_detector, structural_model, thresholds: dict, semantic_limits: dict):
        self.semantic_detector = semantic_detector
        self.structural_model = structural_model
        self.thresholds = thresholds
        self.semantic_limits = semantic_limits

        self.weights = {
            "structural": 0.3,
            "semantic": 0.25,
            "keyword": 0.25,
            "pattern": 0.2
        }

    def detect(self, text: str, role: str, features: List[float]) -> Dict:
        benign_conf = query_classifier.get_benign_confidence(text)

        # Pure structural score from autoencoder reconstruction MSE
        structural_score = self.structural_model._score_agent_structure(role, features)
        structural_base_limit = self.thresholds.get(role, 0.05)
        structural_limit = structural_base_limit * max(0.8, 2.0 - benign_conf)
        structural_status = "ALERT" if structural_score > structural_limit else "PASS"

        base_limit = self.semantic_limits.get(role, 0.75)
        semantic_limit = base_limit * max(0.85, 1.2 - benign_conf * 0.15)

        semantic_drift = self.semantic_detector.calculate_drift(role, text)
        semantic_status = "ALERT" if semantic_drift > semantic_limit else "PASS"

        keyword_result = keyword_detector.detect(text)
        keyword_status = "ALERT" if keyword_result["is_suspicious"] else "PASS"

        pattern_score = self._get_pattern_score(text)
        pattern_status = "ALERT" if pattern_score >= 0.35 else "PASS"

        alerts = [structural_status, semantic_status, keyword_status, pattern_status].count("ALERT")

        weighted_score = (
            min(1.0, structural_score / (structural_limit + 1e-6)) * self.weights["structural"] +
            min(1.0, semantic_drift / (semantic_limit + 1e-6)) * self.weights["semantic"] +
            keyword_result["score"] * self.weights["keyword"] +
            pattern_score * self.weights["pattern"]
        )

        structural_ratio = structural_score / (structural_limit + 1e-6)
        semantic_ratio = semantic_drift / (semantic_limit + 1e-6)

        has_high_keyword = any(m.get("level") == "high" for m in keyword_result.get("matches", []))

        # Policy: QUARANTINED vs SUSPICIOUS vs CLEAN
        if has_high_keyword or (structural_ratio >= 1.0 and semantic_ratio >= 1.0) or (structural_ratio >= 3.0 or semantic_ratio >= 2.5):
            overall_status = "QUARANTINED"
        elif keyword_status == "ALERT" or alerts >= 2 or (weighted_score > 0.45 and alerts >= 1):
            overall_status = "SUSPICIOUS"
        elif structural_status == "ALERT" or semantic_status == "ALERT":
            overall_status = "SUSPICIOUS"
        else:
            overall_status = "CLEAN"

        confidence = self._calculate_calibrated_confidence(
            overall_status, structural_ratio, semantic_ratio, keyword_result["score"], pattern_score, alerts, benign_conf
        )

        return {
            "structural_score": round(structural_score, 6),
            "structural_limit": round(structural_limit, 6),
            "structural_status": structural_status,
            "semantic_drift": round(semantic_drift, 6),
            "semantic_limit": round(semantic_limit, 6),
            "semantic_status": semantic_status,
            "keyword_score": keyword_result["score"],
            "keyword_status": keyword_status,
            "pattern_score": round(pattern_score, 4),
            "pattern_status": pattern_status,
            "overall_status": overall_status,
            "confidence": round(confidence, 4),
            "alerts_count": alerts,
            "weighted_score": round(weighted_score, 4),
            "benign_confidence": round(benign_conf, 4),
            "alert_signals": {
                "structural": structural_status,
                "semantic": semantic_status,
                "keyword": keyword_status,
                "pattern": pattern_status
            }
        }

    def _get_pattern_score(self, text: str) -> float:
        features = extract_features(text)

        score = 0.0
        score += features.get("command_pattern", 0) * 0.4
        score += features.get("sql_injection", 0) * 0.4
        score += features.get("shell_command", 0) * 0.3
        score += features.get("override_keywords", 0) * 0.3
        score += features.get("unicode_ratio", 0) * 0.2
        score += features.get("suspicious_phrase_count", 0) * 0.3

        return min(score, 1.0)

    def _calculate_calibrated_confidence(
        self,
        overall_status: str,
        structural_ratio: float,
        semantic_ratio: float,
        keyword_score: float,
        pattern_score: float,
        alerts: int,
        benign_conf: float
    ) -> float:
        max_signal = max(structural_ratio / 2.0, semantic_ratio / 2.0, keyword_score, pattern_score)
        if overall_status == "QUARANTINED":
            return min(0.99, max(0.80, 0.70 + (alerts * 0.08) + (max_signal * 0.15)))
        elif overall_status == "SUSPICIOUS":
            return min(0.85, max(0.50, 0.45 + (alerts * 0.10) + (max_signal * 0.10)))
        else:
            return min(0.99, max(0.70, 0.70 + (benign_conf * 0.25) - (max_signal * 0.15)))
