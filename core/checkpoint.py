# core/checkpoint.py
# NeuroSentinel Lite — Agent State Checkpoint Manager
# Fixed to match SystemSettings (RAW_DATA_DIR, no DATA_DIR)

import json
import copy
import time
import os
from config.settings import SystemSettings


class AgentCheckpoint:
    """
    Stores the last verified clean state per agent.
    Called ONLY when anomaly_score < THRESHOLD.

    Checkpoint stores:
      - input_text:  what was fed into the agent
      - output_text: what the agent produced (clean)
      - telemetry:   the 4D feature dict at that moment
      - mse:         reconstruction error at that moment
      - saved_at:    unix timestamp
    """

    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.checkpoints = {}   # agent_id -> checkpoint dict
        self.path = os.path.join(settings.RAW_DATA_DIR, "checkpoints.json")
        self._load()

    def _load(self):
        """Load existing checkpoints from disk on startup."""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.checkpoints = json.load(f)
            except Exception:
                self.checkpoints = {}
        else:
            self.checkpoints = {}

    def _save(self):
        """Persist checkpoints to disk immediately after every update."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.checkpoints, f, indent=2)

    def save(self, agent_id: str, input_text: str,
             output_text: str, telemetry: dict, mse: float):
        """
        Save a verified clean checkpoint for an agent.
        Only call this when mse < threshold (confirmed clean).
        """
        self.checkpoints[agent_id] = {
            "agent_id":    agent_id,
            "input_text":  input_text,
            "output_text": output_text,
            "telemetry":   copy.deepcopy(telemetry),
            "mse":         mse,
            "saved_at":    time.time()
        }
        self._save()

    def restore(self, agent_id: str) -> dict | None:
        """
        Retrieve last clean checkpoint for an agent.
        Returns None if no clean run has been saved yet.
        """
        return self.checkpoints.get(agent_id, None)

    def retrieve_safe_checkpoint(self, agent_id: str) -> dict | None:
        """
        Retrieve last clean checkpoint for an agent.
        Alias for restore() for API compatibility.
        Returns None if no clean run has been saved yet.
        """
        return self.checkpoints.get(agent_id, None)

    def has(self, agent_id: str) -> bool:
        """Check if a checkpoint exists for this agent."""
        return agent_id in self.checkpoints

    def get_all(self) -> dict:
        """Return a copy of all checkpoints."""
        return copy.deepcopy(self.checkpoints)