import json
import copy
import time
import os
import logging
from config.settings import SystemSettings

logger = logging.getLogger("NeuroSentinel-Checkpoint")


class AgentCheckpoint:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        self.checkpoints = {}
        self.path = os.path.join(settings.RAW_DATA_DIR, "checkpoints.json")
        self._load()
        logger.info(f"📂 Checkpoint path: {self.path}")

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.checkpoints = json.load(f)
                logger.info(f"✅ Loaded {len(self.checkpoints)} checkpoints from {self.path}")
            except Exception as e:
                logger.error(f"❌ Failed to load checkpoints: {e}")
                self.checkpoints = {}
        else:
            logger.info(f"📝 No checkpoint file found at {self.path}, starting fresh")
            self.checkpoints = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.checkpoints, f, indent=2)
            logger.info(f"💾 Saved checkpoints to {self.path}")
        except Exception as e:
            logger.error(f"❌ Failed to save checkpoints: {e}")

    def save(self, agent_id: str, input_text: str,
             output_text: str, telemetry: dict, mse: float) -> str:
        logger.info(f"💾 [Checkpoint] Saving checkpoint for {agent_id}")
        checkpoint_id = f"chk_{agent_id}_{int(time.time()*1000)}"
        
        self.checkpoints[agent_id] = {
            "id":          checkpoint_id,
            "agent_id":    agent_id,
            "input_text":  input_text,
            "output_text": output_text,
            "telemetry":   copy.deepcopy(telemetry) if telemetry else {},
            "mse":         float(mse),
            "saved_at":    time.time()
        }
        
        logger.info(f"📝 [Checkpoint] Checkpoint data: {self.checkpoints[agent_id]}")
        self._save()
        logger.info(f"✅ [Checkpoint] Checkpoint saved for {agent_id} (ID: {checkpoint_id})")
        return checkpoint_id

    def restore(self, agent_id: str) -> dict | None:
        logger.info(f"🔍 [Checkpoint] Restoring checkpoint for {agent_id}")
        result = self.checkpoints.get(agent_id, None)
        if result and "id" not in result:
            result = dict(result)
            result["id"] = f"chk_{agent_id}_legacy"
        logger.info(f"📋 [Checkpoint] Restored: {result}")
        return result

    def retrieve_safe_checkpoint(self, agent_id: str) -> dict | None:
        logger.info(f"🔍 [Checkpoint] Retrieving checkpoint for {agent_id}")
        result = self.checkpoints.get(agent_id, None)
        if result and "id" not in result:
            result = dict(result)
            result["id"] = f"chk_{agent_id}_legacy"
        logger.info(f"📋 [Checkpoint] Retrieved: {result}")
        return result

    def has(self, agent_id: str) -> bool:
        return agent_id in self.checkpoints

    def get_all(self) -> dict:
        return copy.deepcopy(self.checkpoints)