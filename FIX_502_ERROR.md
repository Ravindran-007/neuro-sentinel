# 🔧 Docker Daemon 502 Error Recovery

## The Problem

```
request returned 502 Bad Gateway for API route
Container neurosentimel_security_service failed
```

**Meaning:** Docker daemon crashed/became unresponsive after 221 seconds

---

## Quick Fix Steps

### Step 1: Stop docker-compose
```bash
# Press Ctrl+C in the terminal where docker-compose is running
# Wait for graceful shutdown (or force with another Ctrl+C)
```

### Step 2: Check if daemon is alive
```bash
docker ps
```

**If this command:**
- ✅ Shows containers → daemon is OK, skip to Step 4
- ⏳ Hangs (doesn't respond) → daemon is down, go to Step 3
- ❌ Shows error → daemon is down, go to Step 3

### Step 3: Restart Docker Desktop (if needed)
```bash
# Close Docker Desktop completely
# Wait 30 seconds
# Reopen Docker Desktop (Start → Docker Desktop)
# Wait 60 seconds for startup
```

### Step 4: Verify daemon is responsive
```bash
docker ps
```

Should show container list (even if empty).

### Step 5: Clean up and retry
```bash
# Remove failed containers
docker-compose down

# Wait 5 seconds

# Try again with background mode (uses less resources)
docker-compose up -d
```

### Step 6: Monitor startup
```bash
# Watch container logs
docker-compose logs -f

# Check if security_service started
docker ps
```

---

## What to Watch For

### Success (Run these):
```bash
# All 3 containers running
docker ps

# Should show:
# neurosentimel_redis       Up
# neurosentimel_ollama      Up
# neurosentimel_security_service  Up
```

### Then test:
```bash
# Health check
curl http://localhost:8000/api/health

# Should return JSON: {"status": "healthy", ...}
```

---

## If 502 Error Happens Again

### Option A: Use background mode (recommended)
```bash
docker-compose down
docker-compose up -d
```

Background mode (`-d`) uses less memory and is more stable.

### Option B: Restart Docker completely
```bash
# Stop everything
docker-compose down

# Close Docker Desktop

# Wait 60 seconds

# Reopen Docker Desktop

# Wait 60 seconds

# Restart containers
docker-compose up -d
```

### Option C: Check system resources
```powershell
# Check free RAM
$mem = (Get-CimInstance -ClassName Win32_OperatingSystem).FreePhysicalMemory / 1MB
Write-Host "Free RAM: $(($mem / 1024).ToString('F1')) GB"

# If < 2GB → close other apps and try again
```

---

## Detailed Timeline

| Step | Action | Time |
|------|--------|------|
| 1 | Stop docker-compose (Ctrl+C) | 30 sec |
| 2 | Check daemon (docker ps) | 5 sec |
| 3 | Restart Docker (if needed) | 90 sec |
| 4 | Verify daemon (docker ps) | 5 sec |
| 5 | Cleanup (docker-compose down) | 10 sec |
| 6 | Retry (docker-compose up -d) | 3 min |
| **Total** | | **~4-5 min** |

---

## Success Indicators

Once services are running, you should see:

```bash
$ docker ps

CONTAINER ID   IMAGE                               STATUS
abc123...      neurosentimel_redis                 Up 2 min
def456...      neurosentimel_ollama                Up 1 min
ghi789...      neurosentimel_security_service      Up 30 sec
```

**And:**
```bash
$ curl http://localhost:8000/api/health

{"status": "healthy", "service": "NeuroSentinel Security Service v2.0"}
```

---

## If Still Failing

1. **Check Docker daemon logs:**
   ```bash
   docker system events --filter type=container
   ```

2. **Check free RAM:**
   ```powershell
   Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory
   ```

3. **Check Docker resources:**
   - Open Docker Desktop Settings
   - Go to Resources
   - Check memory allocation (should be 4-6GB)

4. **Contact support with:**
   - Output of `docker ps`
   - Output of `docker-compose logs security_service`
   - System RAM status

---

## What Works Best

✅ **Recommended approach:**
```bash
docker-compose down
docker-compose up -d
```

This runs services in background (more stable, less resource intensive).

Then monitor with:
```bash
docker-compose logs -f
```

---

**Status:** Docker daemon temporarily unresponsive. Follow steps above to recover.
