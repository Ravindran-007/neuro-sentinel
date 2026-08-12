import json
import os
import torch
import torch.nn as nn
import numpy as np
import sys

sys.path.insert(0, '.')

from models.anomaly_detector import LSTMAutoencoder
from config.settings import SystemSettings

settings = SystemSettings()
log_path = settings.SECURITY_LOG_FILE

MIN_VALS = np.array([0.0,   0.0,   0.0, 0.0],  dtype=np.float32)
MAX_VALS = np.array([3200.0, 200.0, 6.0, 30.0], dtype=np.float32)

if not os.path.exists(log_path):
    print(f"❌ No telemetry file found at: {log_path}")
    exit(1)

with open(log_path, "r", encoding="utf-8") as f:
    raw_log = json.load(f)

print(f"[Train] Loaded {len(raw_log)} total records from {log_path}")

agent_datasets = {
    "Researcher": [],
    "Analyst": [],
    "Reporter": []
}

for record in raw_log:
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

print(f"[Train] Clean samples: Researcher={len(agent_datasets['Researcher'])}, Analyst={len(agent_datasets['Analyst'])}, Reporter={len(agent_datasets['Reporter'])}")

print("\n" + "="*60)
print("🧠 RECALIBRATING PER-AGENT BASELINES")
print("="*60 + "\n")

threshold_registry = {}

for role, samples in agent_datasets.items():
    if len(samples) == 0:
        print(f"⚠️ Agent '{role}' has no clean footprints. Skipping.")
        continue
    
    print(f"[Brain Factory] Processing neural profile for: {role.upper()}")
    print(f"  └─ Extracted {len(samples)} clean behavior templates.")
    
    samples_np = np.array(samples, dtype=np.float32)
    scaled = (samples_np - MIN_VALS) / (MAX_VALS - MIN_VALS + 1e-5)
    X = torch.tensor(scaled, dtype=torch.float32).unsqueeze(1)
    
    model = LSTMAutoencoder(sequence_length=1, feature_dim=4, hidden_dim=8)
    model.train()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.MSELoss()
    
    for epoch in range(150):
        optimizer.zero_grad()
        output = model(X)
        loss = criterion(output, X)
        loss.backward()
        optimizer.step()
    
    model.eval()
    with torch.no_grad():
        reconstructed = model(X)
        per_sample_mse = nn.MSELoss(reduction='none')(reconstructed, X).mean(dim=[1, 2])
        mean_mse = per_sample_mse.mean().item()
        std_mse = per_sample_mse.std().item()
        
        calibrated_threshold = max(mean_mse + 2 * std_mse, 0.05)
        threshold_registry[role] = calibrated_threshold
    
    os.makedirs("models", exist_ok=True)
    save_path = os.path.join("models", f"{role.lower()}_core.pt")
    torch.save(model.state_dict(), save_path)
    print(f"  └─ Profile Optimized! Loss: {loss.item():.6f} -> Threshold: {calibrated_threshold:.6f} -> Saved to {save_path}\n")

print("="*60)
print("📋 NEW THRESHOLD VALUES (for engine.py)")
print("="*60)
for role, th in threshold_registry.items():
    print(f"THRESHOLD_{role.upper()} = {th:.6f}")

engine_path = "core/engine.py"
with open(engine_path, "r", encoding="utf-8") as f:
    engine_content = f.read()

import re
new_thresholds = "THRESHOLDS = {\n"
for role, th in threshold_registry.items():
    new_thresholds += f'    "{role}": {th:.6f},\n'
new_thresholds += "}\n"

pattern = r'THRESHOLDS = \{[^}]+\}'
engine_content = re.sub(pattern, new_thresholds.rstrip(), engine_content)

with open(engine_path, "w", encoding="utf-8") as f:
    f.write(engine_content)

print(f"\n✅ Updated {engine_path} with new thresholds")