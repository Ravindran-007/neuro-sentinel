import os
from dataclasses import dataclass

@dataclass(frozen=True)
class SystemSettings:
    OLLAMA_BASE_URL: str = "http://localhost:11434/api/generate"
    TARGET_MODEL: str = "phi3:mini"
    RAW_DATA_DIR: str = "data"
    SECURITY_LOG_FILE: str = os.path.join("data", "telemetry_stream.json")
    SLIDING_WINDOW_SIZE: int = 5
    FEATURE_DIMENSION: int = 4