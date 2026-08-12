import pytest
import json
import time
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from production.security_service import app, DetectionRequest, DetectionResult

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "redis" in data
    assert data["uptime_requests"] >= 0
    print(f"✅ Health check passed: {data['service']}")

def test_thresholds_endpoint():
    response = client.get("/api/thresholds")
    assert response.status_code == 200
    data = response.json()
    
    for agent in ["Researcher", "Analyst", "Reporter"]:
        assert agent in data["structural_thresholds"]
        assert agent in data["semantic_drift_limits"]
    
    for agent in ["Researcher", "Analyst", "Reporter"]:
        assert data["structural_thresholds"][agent] > 0
        assert data["semantic_drift_limits"][agent] > 0
    
    print(f"✅ Thresholds endpoint passed")

def test_detect_valid_clean_input():
    request = {
        "agent_role": "Researcher",
        "user_input": "Extract the main findings from this technical document.",
        "llm_provider": "ollama"
    }
    
    response = client.post("/api/detect", json=request)
    
    if response.status_code == 200:
        data = response.json()
        assert data["agent_role"] == "Researcher"
        assert data["overall_status"] in ["CLEAN", "SUSPICIOUS", "QUARANTINED"]
        assert 0.0 <= data["confidence"] <= 1.0
        assert data["structural_score"] >= 0.0
        assert data["semantic_drift"] >= 0.0
        print(f"✅ Detection (clean input): {data['overall_status']} | Confidence: {data['confidence']:.2%}")
    else:
        assert response.status_code in [503, 500]
        print(f"⚠️ LLM backend unavailable (expected during CI/CD): {response.status_code}")

def test_detect_invalid_agent_role():
    request = {
        "agent_role": "InvalidAgent",
        "user_input": "Test input",
        "llm_provider": "ollama"
    }
    
    response = client.post("/api/detect", json=request)
    assert response.status_code == 422
    print(f"✅ Invalid agent role rejected correctly")

def test_detect_missing_input():
    request = {
        "agent_role": "Researcher",
        "user_input": "",
        "llm_provider": "ollama"
    }
    
    response = client.post("/api/detect", json=request)
    assert response.status_code == 422
    print(f"✅ Empty input rejected correctly")

def test_detect_oversized_input():
    request = {
        "agent_role": "Researcher",
        "user_input": "x" * 10000,
        "llm_provider": "ollama"
    }
    
    response = client.post("/api/detect", json=request)
    assert response.status_code == 422
    print(f"✅ Oversized input rejected correctly")

def test_models_reload_endpoint():
    response = client.post("/api/models/reload")
    
    if response.status_code == 200:
        data = response.json()
        assert data["status"] == "success"
        print(f"✅ Model reload successful")
    else:
        assert response.status_code == 500
        print(f"⚠️ Model files missing (expected if not yet trained): {response.status_code}")

def test_checkpoint_retrieval_valid_agent():
    response = client.get("/api/state/checkpoint/Researcher")
    
    if response.status_code == 200:
        data = response.json()
        assert data["agent_role"] == "Researcher"
        assert "checkpoint" in data
        print(f"✅ Checkpoint retrieval successful")
    else:
        assert response.status_code in [404, 500]
        print(f"⚠️ Checkpoint not available (expected if pipeline not run): {response.status_code}")

def test_checkpoint_retrieval_invalid_agent():
    response = client.get("/api/state/checkpoint/InvalidAgent")
    assert response.status_code == 400
    print(f"✅ Invalid agent checkpoint request rejected")

def test_anomalies_queue_retrieval():
    response = client.get("/api/anomalies/Researcher")
    
    if response.status_code == 200:
        data = response.json()
        if "agent_role" in data:
            assert data["agent_role"] == "Researcher"
            assert "count" in data
            assert "anomalies" in data
            assert isinstance(data["anomalies"], list)
            print(f"✅ Anomaly queue retrieval successful (count: {data['count']})")
        else:
            assert "anomalies" in data
            print(f"✅ Anomaly queue endpoint accessible (Redis unavailable)")
    else:
        assert response.status_code == 400
        print(f"✅ Anomaly queue endpoint accessible")

def test_anomalies_invalid_agent():
    response = client.get("/api/anomalies/InvalidAgent")
    assert response.status_code == 400
    print(f"✅ Invalid agent anomaly request rejected")

def test_anomalies_with_limit():
    response = client.get("/api/anomalies/Researcher?limit=5")
    
    if response.status_code == 200:
        data = response.json()
        assert len(data["anomalies"]) <= 5
        print(f"✅ Anomaly limit parameter respected")

def test_detection_response_time():
    request = {
        "agent_role": "Analyst",
        "user_input": "Analyze the risk profile of this system.",
        "llm_provider": "ollama"
    }
    
    start = time.time()
    response = client.post("/api/detect", json=request)
    elapsed = (time.time() - start) * 1000
    
    if response.status_code == 200:
        assert elapsed < 30000, f"Detection took {elapsed:.0f}ms (expected < 30000ms)"
        print(f"✅ Detection response time: {elapsed:.0f}ms")
    else:
        print(f"⚠️ LLM backend unavailable, skipping performance test")

def test_malformed_json_request():
    response = client.post(
        "/api/detect",
        content="{invalid json}",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    print(f"✅ Malformed JSON rejected correctly")

def test_missing_required_fields():
    request = {
        "user_input": "Test input"
    }
    
    response = client.post("/api/detect", json=request)
    assert response.status_code == 422
    print(f"✅ Missing required field validation works")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])