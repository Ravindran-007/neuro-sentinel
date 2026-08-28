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
        
        structural_score = self._get_structural_score(role, features, text)
        structural_limit = self.thresholds.get(role, 0.05) * max(0.8, 2.0 - benign_conf)
        structural_status = "ALERT" if structural_score > structural_limit else "PASS"
        
        base_limit = self.semantic_limits.get(role, 0.75)
        semantic_limit = base_limit * max(0.85, 1.2 - benign_conf * 0.15)
        
        semantic_drift = self.semantic_detector.calculate_drift(role, text)
        semantic_status = "ALERT" if semantic_drift > semantic_limit else "PASS"
        
        keyword_result = keyword_detector.detect(text)
        keyword_status = "ALERT" if keyword_result["is_suspicious"] else "PASS"
        
        pattern_score = self._get_pattern_score(text)
        pattern_status = "ALERT" if pattern_score > 0.1 else "PASS"
        
        alerts = [structural_status, semantic_status, keyword_status, pattern_status].count("ALERT")
        
        weighted_score = (
            structural_score * self.weights["structural"] +
            semantic_drift * self.weights["semantic"] +
            keyword_result["score"] * self.weights["keyword"] +
            pattern_score * self.weights["pattern"]
        )
        
        anomaly_weight = 1.3 - (benign_conf * 0.9)
        weighted_threshold = 0.35 * anomaly_weight
        
        # FIX: keyword detector has zero false positives across the benign test
        # set (0.0000 PASS on all 16), so a keyword ALERT is trusted on its own,
        # same as before. Every other detector still needs a second detector to
        # corroborate (alerts >= 2) before triggering SUSPICIOUS, since structural
        # and semantic alone are noisier.
        if weighted_score > weighted_threshold or alerts >= 2 or keyword_status == "ALERT":
            overall_status = "SUSPICIOUS"
        else:
            overall_status = "CLEAN"
        
        confidence = self._calculate_confidence(
            structural_score, semantic_drift, keyword_result["score"], pattern_score, alerts, weighted_score
        )
        
        return {
            "structural_score": structural_score,
            "structural_status": structural_status,
            "semantic_drift": semantic_drift,
            "semantic_status": semantic_status,
            "keyword_score": keyword_result["score"],
            "keyword_status": keyword_status,
            "pattern_score": pattern_score,
            "pattern_status": pattern_status,
            "overall_status": overall_status,
            "confidence": confidence,
            "alerts_count": alerts,
            "weighted_score": weighted_score,
            "benign_confidence": benign_conf,
            "alert_signals": {
                "structural": structural_status,
                "semantic": semantic_status,
                "keyword": keyword_status,
                "pattern": pattern_status
            }
        }
    
    def _get_structural_score(self, role: str, features: List[float], text: str) -> float:
        base_score = self.structural_model._score_agent_structure(role, features)
        
        boost = keyword_detector.get_boost_factor(text)
        
        return base_score * boost
    
    def _get_pattern_score(self, text: str) -> float:
        features = extract_features(text)
        
        score = 0.0
        score += features.get("command_pattern", 0) * 0.4
        score += features.get("sql_injection", 0) * 0.4
        score += features.get("shell_command", 0) * 0.3
        score += features.get("override_keywords", 0) * 0.3
        score += features.get("unicode_ratio", 0) * 0.2
        score += features.get("suspicious_phrase_count", 0) * 0.3
        score += features.get("imperative_mood", 0) * 0.1
        score += features.get("instruction_count", 0) * 0.1
        
        return min(score, 1.0)
    
    def _calculate_confidence(self, structural: float, semantic: float, 
                               keyword: float, pattern: float, alerts: int, weighted: float,
                               is_benign: bool = False) -> float:
        if is_benign:
            if alerts >= 2:
                return max(0.0, 1.0 - weighted)
            return 1.0 - min(0.5, max(structural, semantic, keyword, pattern))
        
        if alerts == 0:
            return 1.0 - max(structural, semantic, keyword, pattern)
        elif alerts >= 3:
            return 1.0
        else:
            return min(weighted * 2, 1.0)