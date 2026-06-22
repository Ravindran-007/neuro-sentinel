# core/quarantine.py
# NeuroSentinel Lite — Live Quarantine Engine
# Fixed to match SystemSettings (RAW_DATA_DIR, no DATA_DIR)

import json
import time
import copy
import os
from datetime import datetime
from config.settings import SystemSettings


# ─────────────────────────────────────────────────────────────
# QUARANTINE SIGNAL
# Custom exception — raised inside engine.py on breach
# Instantly stops pipeline execution at the breaching agent
# ─────────────────────────────────────────────────────────────
class QuarantineSignal(Exception):
    """
    Raised when an agent's MSE score >= threshold.
    Carries full breach context for forensic logging.
    """

    def __init__(self, agent_id: str, mse: float,
                 threshold: float, output: str, telemetry: dict):
        self.agent_id   = agent_id
        self.mse        = mse
        self.threshold  = threshold
        self.output     = output
        self.telemetry  = copy.deepcopy(telemetry)
        self.breach_pct = ((mse - threshold) / threshold) * 100
        self.timestamp  = datetime.now().isoformat()

        super().__init__(
            f"[QUARANTINE] '{agent_id}' | "
            f"MSE={mse:.6f} > Threshold={threshold:.6f} | "
            f"+{self.breach_pct:.1f}% breach"
        )


# ─────────────────────────────────────────────────────────────
# QUARANTINE ENGINE
# ─────────────────────────────────────────────────────────────
class QuarantineEngine:
    """
    Handles automatic recovery when QuarantineSignal is caught.

    Full recovery sequence (zero human input):
      1. Freeze compromised agent
      2. Log forensic incident → incident_log.json
      3. Rollback to last clean checkpoint
      4. Create clean agent clone record
      5. Resume remaining pipeline agents
      6. Return complete recovery report dict
    """

    def __init__(self, threshold: float,
                 checkpoint_manager,
                 settings: SystemSettings = SystemSettings()):
        self.threshold   = threshold
        self.checkpoints = checkpoint_manager
        self.settings    = settings
        self.log         = []
        self.log_path    = os.path.join(
            settings.RAW_DATA_DIR, "incident_log.json"
        )
        self._load_log()

    def _load_log(self):
        """Load existing incident log from disk on startup."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path) as f:
                    self.log = json.load(f)
            except Exception:
                self.log = []
        else:
            self.log = []

    def _write_log(self):
        """Persist incident log to disk."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w") as f:
            json.dump(self.log, f, indent=2)

    def recover(self, signal: QuarantineSignal,
                pipeline_ref,
                remaining_roles: list) -> dict:
        """
        Full automatic recovery. Called from engine.py
        when QuarantineSignal is caught.

        Args:
            signal:          The QuarantineSignal that was raised
            pipeline_ref:    The IndustrialPipeline instance
                             (used to call _execute_inference)
            remaining_roles: Agent roles not yet executed
                             e.g. ["Reporter"] if Analyst was quarantined

        Returns:
            recovery report dict (stored in incident_log.json)
        """

        t_start = time.time()
        inc_id  = f"INC-{int(t_start)}"

        print(f"\n{'='*55}")
        print(f"🚨 QUARANTINE ENGINE ACTIVATED")
        print(f"   Incident : {inc_id}")
        print(f"   Agent    : {signal.agent_id}")
        print(f"   MSE      : {signal.mse:.6f}")
        print(f"   Threshold: {signal.threshold:.6f}")
        print(f"   Breach   : +{signal.breach_pct:.1f}%")
        print(f"{'='*55}")

        # ── Step 1: Freeze ───────────────────────────────────
        print(f"[1/5] ❄️  Agent '{signal.agent_id}' FROZEN")

        # ── Step 2: Log forensic incident ────────────────────
        incident = {
            "incident_id": inc_id,
            "timestamp":   signal.timestamp,
            "agent_id":    signal.agent_id,
            "mse":         signal.mse,
            "threshold":   signal.threshold,
            "breach_pct":  signal.breach_pct,
            "telemetry":   signal.telemetry,
        }
        self.log.append(incident)
        self._write_log()
        print(f"[2/5] 📋 Forensic incident logged → incident_log.json")

        # ── Step 3: Rollback to last clean checkpoint ────────
        checkpoint = self.checkpoints.restore(signal.agent_id)
        if checkpoint:
            clean_output = checkpoint["output_text"]
            print(
                f"[3/5] ⏪ Rollback to checkpoint "
                f"(MSE={checkpoint['mse']:.6f})"
            )
        else:
            clean_output = (
                "[SAFE FALLBACK] No prior clean checkpoint available. "
                "Proceeding with sanitized empty context."
            )
            print(f"[3/5] ⚠️  No checkpoint found — using safe fallback")

        # ── Step 4: Clone clean agent ────────────────────────
        clone_id = f"{signal.agent_id}_clone_{inc_id}"
        print(f"[4/5] 🧬 Clean clone created: '{clone_id}'")

        # ── Step 5: Resume remaining pipeline agents ─────────
        resumed_output = clean_output
        resume_log     = []
        resume_error   = None

        print(
            f"[5/5] ▶️  Resuming {len(remaining_roles)} "
            f"remaining agent(s): {remaining_roles}"
        )

        for role in remaining_roles:
            try:
                node = pipeline_ref.nodes[role]
                out, dt = pipeline_ref._execute_inference(
                    node, resumed_output
                )
                resumed_output = out
                resume_log.append({
                    "role":   role,
                    "status": "ok",
                    "time":   round(dt, 3)
                })
                print(f"      ✅ '{role}' completed in {dt:.2f}s")
            except Exception as e:
                resume_error = str(e)
                resume_log.append({
                    "role":   role,
                    "status": "error",
                    "error":  resume_error
                })
                print(f"      ❌ '{role}' failed: {e}")
                break

        t_recovery = round(time.time() - t_start, 3)

        # ── Build full recovery report ────────────────────────
        report = {
            "incident_id":     inc_id,
            "quarantined":     signal.agent_id,
            "breach_pct":      round(signal.breach_pct, 2),
            "clone_id":        clone_id,
            "checkpoint_used": checkpoint is not None,
            "resumed_output":  resumed_output,
            "resume_log":      resume_log,
            "resume_error":    resume_error,
            "recovery_time_s": t_recovery,
            "timestamp":       signal.timestamp
        }

        # Update incident entry with recovery result
        incident["recovery"] = report
        self._write_log()

        print(f"\n✅ RECOVERY COMPLETE in {t_recovery}s")
        print(f"{'='*55}\n")

        return report

    def get_incidents(self) -> list:
        """Return a copy of all logged incidents."""
        return copy.deepcopy(self.log)