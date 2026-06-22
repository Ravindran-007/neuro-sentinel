# 🔧 Docker Virtualization Error — Complete Fix Guide

## The Problem

```
Virtualization support not detected

Docker Desktop requires virtualization support to run. 
Contact your IT admin to enable virtualization or check system requirements.
```

**What this means:** Your CPU has virtualization capabilities, but they're currently **disabled in BIOS**.

---

## Solution 1: Enable Virtualization in BIOS (Fastest)

### If you have an Intel CPU:

1. **Shut down** your computer completely
2. **Restart** and immediately start pressing **F2** or **DEL** key repeatedly (before Windows loads)
   - Different laptops use different keys: F2, F12, DEL, ESC
   - Keep pressing until you see the BIOS setup screen (blue or black menu)

3. **Find the virtualization setting:**
   - Look for tabs: `Advanced`, `Processor`, `CPU Features`, or `System`
   - Search for: `Virtualization`, `VT-x`, `Intel VT`, or `Intel Virtualization`

4. **Change setting:**
   - Current value: `Disabled` 
   - Change to: `Enabled`

5. **Save and Exit:**
   - Press **F10** (or look for "Save & Exit")
   - Confirm "Yes" when prompted

6. **Restart computer** and try Docker Desktop again

### If you have an AMD CPU:

Same steps above, but look for:
- `SVM` (Secure Virtual Machine)
- `AMD-V`
- `AMD Virtualization`

---

## Solution 2: Enable WSL2 (Alternative if you can't access BIOS)

### Step-by-step:

1. **Open PowerShell as Administrator:**
   - Right-click Start → Windows PowerShell (Admin)

2. **Run this command:**
   ```powershell
   wsl --install -d Ubuntu
   ```

3. **Wait for installation** (5-10 minutes)

4. **Restart your computer**

5. **Open Docker Desktop** → Settings → Resources → WSL Integration → Enable Ubuntu

6. **Restart Docker Desktop**

---

## Solution 3: Docker Toolbox (Fallback)

If BIOS virtualization can't be enabled and WSL2 doesn't work:

1. **Uninstall Docker Desktop**
2. **Download Docker Toolbox:** https://github.com/docker-toolbox/docker-toolbox/releases
3. **Install and run** — uses VirtualBox instead

---

## Quick Troubleshooting Checklist

- [ ] Did you restart the computer after enabling BIOS virtualization?
- [ ] Are you using the correct BIOS key for your laptop model?
- [ ] Is Docker Desktop closed before restarting?
- [ ] Did you wait 30 seconds after restarting before opening Docker Desktop?
- [ ] Does `docker ps` work in PowerShell now?

---

## Verify It's Working

Once fixed, run this command in PowerShell:

```bash
docker ps
```

**Success looks like:**
```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

(Empty list is fine — just means no containers running yet)

---

## Next Steps

Once Docker works:

```bash
cd e:\neuro_sentinel
docker-compose up --build
```

Then verify Level 2:

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status": "healthy", "service": "NeuroSentinel Security Service v2.0"}
```

---

## Still Having Issues?

**Error:** "Cannot find BIOS virtualization option"
- **Fix:** Contact your laptop manufacturer support with model number
- **Alternative:** Use Solution 2 (WSL2) instead

**Error:** "Permission denied" when running WSL install
- **Fix:** Right-click PowerShell → "Run as Administrator"

**Error:** "Docker still won't start"
- **Fix:** Restart computer completely (not sleep)
- Then wait 60 seconds before opening Docker Desktop

---

**Status:** Level 2 code ready. Just waiting for Docker to work.
