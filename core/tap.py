import json
import os
import math
from datetime import datetime, timezone
from collections import Counter
from typing import Dict, Any
from config.settings import SystemSettings

class SecurityTap:
    def __init__(self, settings: SystemSettings = SystemSettings()):
        self.settings = settings
        os.makedirs(self.settings.RAW_DATA_DIR, exist_ok=True)

    def _calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        probabilities = [count / len(text) for count in Counter(text).values()]
        return -sum(p * math.log2(p) for p in probabilities)

    def extract_features(self, session_id: str, sender: str, receiver: str, 
                         payload: str, execution_time: float) -> Dict[str, Any]:
        word_list = payload.split()
        telemetry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "sender": sender,
            "receiver": receiver,
            "metrics": {
                "length": len(payload),
                "word_count": len(word_list),
                "entropy": round(self._calculate_entropy(payload), 4),
                "execution_time": round(execution_time, 4)
            },
            "raw_payload": payload
        }
        self._write_to_ledger(telemetry)
        return telemetry

    def _write_to_ledger(self, telemetry: Dict[str, Any]) -> None:
        ledger_path = self.settings.SECURITY_LOG_FILE
        try:
            if os.path.exists(ledger_path):
                with open(ledger_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            else:
                data = []
            data.append(telemetry)
            with open(ledger_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
        except Exception as e:
            print(f"[-] Telemetry write failure: {e}")