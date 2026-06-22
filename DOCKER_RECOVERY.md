# 🔧 Docker Build Recovery Guide

## The Problem

Build failed at Step 14/15 during image export with error:
```
failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF
```

**WSL Error:** `docker_data.vhdx: exit status 0xffffffff`

**Translation:** Docker daemon lost connection while saving the built image.

---

## Quick Fix (3 steps, 5 minutes)

### Step 1: Close the WSL Error Dialog
1. Look for the error popup on screen
2. Click **"Quit"** to dismiss it

### Step 2: Restart Docker Desktop
```bash
# Close Docker Desktop completely
# (Right-click Docker icon in taskbar → Exit)

# Wait 30 seconds

# Reopen Docker Desktop
# (Start menu → Docker Desktop)

# Wait 60 seconds for startup
```

### Step 3: Verify Docker is Working
```bash
docker ps
```

**Expected:** Container list (even if empty, that's fine)

---

## Full Recovery (if Step 1-3 doesn't work)

### Step 4: Clean Docker Cache

```bash
# This removes all dangling images and volumes
docker system prune -a --volumes

# When prompted: type 'y' and press Enter
```

**What this does:**
- Frees up 1-2GB of disk space
- Removes incomplete builds
- Resets Docker state

### Step 5: Rebuild

```bash
cd e:\neuro_sentinel
docker-compose up --build
```

---

## Advanced Recovery (if build fails again)

### Issue 1: Disk Space

Check available space:
```bash
wmic logicaldisk get name,size,freespace
```

Look at C:\ drive - **need at least 5GB free**.

If low on space:
1. Open Windows Explorer
2. Go to `C:\Users\[YourUsername]\AppData\Local\Docker\wsl\data`
3. Delete old volumes: `docker volume ls` then `docker volume rm [name]`

### Issue 2: Memory/CPU

Docker Desktop needs resources:
1. Open **Docker Desktop Settings**
2. Go to **Resources**
3. Set:
   - **CPUs:** 4 (or more)
   - **Memory:** 4GB or 6GB
   - **Swap:** 1GB
4. Click **Apply & Restart**

### Issue 3: WSL Corruption

If the vhdx file is corrupted:

```bash
# Stop all Docker processes
docker system prune -a --volumes

# Reset Docker Desktop
# (Settings → Troubleshoot → Clean/Purge Data)

# Restart Docker Desktop
```

---

## Timeline: What to Expect

1. **Now:** Close WSL error dialog
2. **+1 min:** Restart Docker Desktop
3. **+2 min:** Docker should be responsive (docker ps works)
4. **+3 min:** Run docker system prune to free space
5. **+5 min:** Retry `docker-compose up --build`
6. **+5-8 min:** Build should complete successfully ✅

---

## Monitoring the Rebuild

Once you retry `docker-compose up --build`:

Watch for:
```
✓ redis Pulled
✓ ollama Pulled
[+] Building 
 => Step 14/15 COMPLETE ✓
 => Exporting to image ✓
[+] Running containers
✓ redis started
✓ ollama started
✓ security_service started
✓ Uvicorn running on 0.0.0.0:8000
```

**Success:** All services running with no errors ✅

---

## If Build STILL Fails

Run this for detailed logs:

```bash
docker-compose logs -f security_service
```

Send the error output - it will tell us exactly what went wrong.

---

## Success Criteria

Once Docker is running:

1. ✅ `docker ps` shows containers
2. ✅ `curl http://localhost:8000/api/health` returns JSON
3. ✅ `docker-compose logs` shows no errors
4. ✅ All 3 services (redis, ollama, security_service) are running

---

**Action:** Follow the 3 steps above, then try building again!
