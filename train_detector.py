import json
import os
import torch
import torch.nn as nn
import numpy as np
from config.settings import SystemSettings
from models.anomaly_detector import LSTMAutoencoder

# ─────────────────────────────────────────────────────────────
# STEP 1: Load Telemetry Data & Set Corrected Scaling Limits
# ─────────────────────────────────────────────────────────────
settings = SystemSettings()
log_path = settings.SECURITY_LOG_FILE

if not os.path.exists(log_path):
    print(f"❌ No telemetry file found at: {log_path}")
    exit(1)

with open(log_path, "r", encoding="utf-8") as f:
    raw_log = json.load(f)

print(f"[Train] Loaded {len(raw_log)} total records from {log_path}")

# Phase 2 Fixed Scaling Bounds: Tailored to your local tap.py dimensions
MIN_VALS = np.array([0.0,   0.0,   0.0, 0.0],  dtype=np.float32)
MAX_VALS = np.array([3200.0, 200.0, 6.0, 30.0], dtype=np.float32)

# ─────────────────────────────────────────────────────────────
# STEP 2: Segment Telemetry Data by Agent Role
# ─────────────────────────────────────────────────────────────
agent_datasets = {
    "Researcher": [],
    "Analyst": [],
    "Reporter": []
}

for record in raw_log:
    # Baseline profiles must ONLY learn from clean, non-attack data
    if "ATTACK" in record.get("session_id", ""):
        continue
        
    role = record.get("sender")
    if role not in agent_datasets:
        continue
        
    try:
        m = record["metrics"]
        vec = [float(m["length"]), float(m["word_count"]), float(m["entropy"]), float(m["execution_time"])]
        agent_datasets[role].append(vec)
    except (KeyError, TypeError):
        continue

# ─────────────────────────────────────────────────────────────
# STEP 3: Multi-Brain Iterative Training Loop
# ─────────────────────────────────────────────────────────────
print("\n================================================================")
print("🧠 COGNITIVE FINGERPRINTING: TRAINING PER-AGENT BASELINES")
print("================================================================\n")

threshold_registry = {}

for role, samples in agent_datasets.items():
    if len(samples) == 0:
        print(f"⚠️ Agent '{role}' has no clean footprints. Skipping profile compilation.")
        continue
        
    print(f"[Brain Factory] Processing neural profile for: {role.upper()}")
    print(f"  └─ Extracted {len(samples)} clean behavior templates.")
    
    samples_np = np.array(samples, dtype=np.float32)
    scaled = (samples_np - MIN_VALS) / (MAX_VALS - MIN_VALS + 1e-5)
    
    # Format shape into [Samples, Sequence=1, Features=4]
    X = torch.tensor(scaled, dtype=torch.float32).unsqueeze(1)
    
    model = LSTMAutoencoder(sequence_length=1, feature_dim=4, hidden_dim=8)
    model.train()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.MSELoss()
    
    # 150 Optimization Epochs for tight validation convergence
    for epoch in range(150):
        optimizer.zero_grad()
        output = model(X)
        loss = criterion(output, X)
        loss.backward()
        optimizer.step()
        
    # Per-Agent Perimeter Calibration Phase
    model.eval()
    with torch.no_grad():
        reconstructed = model(X)
        per_sample_mse = nn.MSELoss(reduction='none')(reconstructed, X).mean(dim=[1, 2])
        max_clean_mse = per_sample_mse.max().item()
        
        # Security perimeter set at exactly 120% of max clean baseline distortion
        calibrated_threshold = max_clean_mse * 1.20
        threshold_registry[role] = calibrated_threshold
        
    # Save custom dedicated binaries to disk
    os.makedirs("models", exist_ok=True)
    save_path = os.path.join("models", f"{role.lower()}_core.pt")
    torch.save(model.state_dict(), save_path)
    print(f"  └─ Profile Optimized! Loss: {loss.item():.6f} -> Weights saved to {save_path}\n")

# ─────────────────────────────────────────────────────────────
# STEP 4: Output the New Cognitive Registry Constants
# ─────────────────────────────────────────────────────────────
print("================================================================")
print("📋 PHASE 2 CONFIGURATION REGISTER KEY")
print("   Copy these exact variables into your upcoming engine update:")
print("================================================================")
for role, th in threshold_registry.items():
    print(f"THRESHOLD_{role.upper()} = {th:.6f}")
print("================================================================\n")