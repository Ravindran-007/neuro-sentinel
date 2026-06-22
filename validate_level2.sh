#!/bin/bash
# Quick validation script for Level 2 deployment

echo "🔍 NeuroSentinel Level 2 Validation Script"
echo "=========================================="
echo ""

# Check Python
echo "1️⃣  Checking Python installation..."
python --version || { echo "❌ Python not found"; exit 1; }

# Check Docker
echo "2️⃣  Checking Docker installation..."
docker --version || { echo "⚠️  Docker not found (required for docker-compose)"; }

# Check Docker Compose
echo "3️⃣  Checking Docker Compose..."
docker-compose --version || { echo "⚠️  Docker Compose not found"; }

# Check requirements
echo "4️⃣  Checking required Python packages..."
pip list | grep -q "fastapi" || echo "⚠️  fastapi not installed"
pip list | grep -q "redis" || echo "⚠️  redis not installed"
pip list | grep -q "torch" || echo "⚠️  torch not installed"

# Check project structure
echo "5️⃣  Checking project structure..."
test -f "production/security_service.py" && echo "✅ FastAPI service found" || echo "❌ FastAPI service missing"
test -f "Dockerfile" && echo "✅ Dockerfile found" || echo "❌ Dockerfile missing"
test -f "docker-compose.yml" && echo "✅ docker-compose.yml found" || echo "❌ docker-compose.yml missing"
test -f "tests/test_security_service.py" && echo "✅ Test suite found" || echo "❌ Test suite missing"
test -f "LEVEL_2_GUIDE.md" && echo "✅ Deployment guide found" || echo "❌ Deployment guide missing"

# Check models
echo "6️⃣  Checking trained models..."
test -d "models" && echo "✅ Models directory found" || echo "⚠️  Models directory not found (run train_detector.py)"
test -f "models/researcher_core.pt" && echo "✅ Researcher model found" || echo "⚠️  Researcher model missing"
test -f "models/analyst_core.pt" && echo "✅ Analyst model found" || echo "⚠️  Analyst model missing"
test -f "models/reporter_core.pt" && echo "✅ Reporter model found" || echo "⚠️  Reporter model missing"

echo ""
echo "✅ Validation complete!"
echo ""
echo "📌 Next steps:"
echo "1. Review LEVEL_2_GUIDE.md for deployment instructions"
echo "2. Run: docker-compose up --build"
echo "3. Test: curl http://localhost:8000/api/health"
echo "4. Run tests: pytest tests/test_security_service.py -v"
echo ""
