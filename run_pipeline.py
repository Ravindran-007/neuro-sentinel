import sys
from config.settings import SystemSettings
from core.engine import IndustrialPipeline
from attack_sim.vectors import AttackRepository

def execute_production_run():
    # Initialize settings and our ultra-low-overhead pipeline engine
    settings = SystemSettings()
    pipeline = IndustrialPipeline(settings=settings)
    
    print("================================================================")
    print("🛡️  NEUROSENTINEL: INDUSTRIAL DATASET ACQUISITION ENGINE")
    print("================================================================")
    
    # 1. Run Benign Baseline Collection
    clean_prompts = AttackRepository.get_clean_scenarios()
    print(f"\n[+] Starting Benign Baseline Phase ({len(clean_prompts)} Sessions)")
    
    for idx, prompt in enumerate(clean_prompts):
        session_id = f"SYS-BENIGN-2026-REG-{idx+1:03d}"
        success = pipeline.execute_session(session_id=session_id, entry_prompt=prompt)
        if success is None:
            print("[-] Run paused. Verify Ollama is running (`ollama serve`).")
            sys.exit(1)
            
    # 2. Run Adversarial Attack Collection
    attack_profiles = AttackRepository.get_attack_scenarios()
    print(f"\n[!] Triggering Adversarial Phase ({len(attack_profiles)} Attack Sessions)")
    
    for idx, profile in enumerate(attack_profiles):
        session_id = f"SYS-ATTACK-2026-{profile['type']}-{idx+1:03d}"
        pipeline.execute_session(session_id=session_id, entry_prompt=profile['payload'])

    print("\n================================================================")
    print(f"✅ Telemetry complete. Vector records stored in: {settings.SECURITY_LOG_FILE}")
    print("================================================================")

if __name__ == "__main__":
    execute_production_run()