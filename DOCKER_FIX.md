# 🐳 Docker Desktop Not Running — Quick Fix

## The Problem
```
unable to get image 'neuro_sentinel-security_service': error during connect:
Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.51/images/...": 
The system cannot find the file specified.
```

**Translation:** Docker daemon is not running. You need to start Docker Desktop.

---

## Quick Fix (2 minutes)

### Step 1: Start Docker Desktop
```
Windows Start → Search "Docker Desktop" → Click
```

Wait 60 seconds while it starts up. You should see the Docker whale icon 🐋 in your system tray (bottom right).

### Step 2: Verify It's Running
```bash
docker ps
```

**Expected output:**
```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

(Empty is fine - just means no containers running yet)

### Step 3: Run Level 2 Stack
```bash
cd e:\neuro_sentinel
docker-compose up --build
```

**Expected output:**
```
✅ Redis connected: redis:6379
✅ Ollama health check passed
🚀 Application startup complete
```

---

## Troubleshooting

### Error: "Cannot connect to Docker daemon"
**Fix:** Docker Desktop is still not running. Check system tray or restart it.

### Error: "docker-compose version is obsolete"
**Fix:** This is just a warning. It's OK - docker-compose will still work.

### Docker Desktop Won't Start
**Fix:** Restart your computer, then try again.

---

## Next: Verify Level 2

Once Docker is running, test in new terminal:

```bash
curl http://localhost:8000/api/health
```

**Expected response:**
```json
{"status": "healthy", "service": "NeuroSentinel Security Service v2.0"}
```

---

**Status:** Level 2 files ready. Just need Docker running to verify.
