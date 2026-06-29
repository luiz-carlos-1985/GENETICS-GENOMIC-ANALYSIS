@echo off
setlocal enabledelayedexpansion

echo ================================================
echo  SATB2 Platform - Local Setup (Windows)
echo ================================================
echo.

REM ── Check Python ──────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+ from https://python.org
    pause & exit /b 1
)
echo [OK] Python found

REM ── Check Java ────────────────────────────────────
java -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Java not found. Install JDK 21 from https://adoptium.net
    pause & exit /b 1
)
echo [OK] Java found

REM ── Check Maven ───────────────────────────────────
mvn --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Maven not found. Install from https://maven.apache.org
    pause & exit /b 1
)
echo [OK] Maven found

REM ── Check Docker ──────────────────────────────────
docker --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Docker not found. LocalStack will not be available.
    echo        The system will run in FILE MODE (no S3/SQS).
    set DOCKER_AVAILABLE=false
) else (
    echo [OK] Docker found
    set DOCKER_AVAILABLE=true
)

echo.
echo ================================================
echo  Installing Python worker dependencies...
echo ================================================
cd ai-worker
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
cd ..
echo [OK] Python dependencies installed

echo.
echo ================================================
echo  Building Spring Boot backend...
echo ================================================
cd backend
mvn package -DskipTests -q
cd ..
echo [OK] Backend built

echo.
echo ================================================
echo  Setup complete!
echo.
echo  To start the full system: docker-compose up --build
echo  To start only the backend (requires LocalStack running):
echo    cd backend
echo    set DB_URL=jdbc:postgresql://localhost:5432/satb2db
echo    set DB_USER=satb2user
echo    set DB_PASS=satb2pass
echo    set AWS_ENDPOINT_OVERRIDE=http://localhost:4566
echo    set AWS_ACCESS_KEY_ID=test
echo    set AWS_SECRET_ACCESS_KEY=test
echo    mvn spring-boot:run
echo.
echo  To start only the worker:
echo    cd ai-worker
echo    call venv\Scripts\activate.bat
echo    set SQS_QUEUE_URL=http://localhost:4566/000000000000/satb2-analysis-queue
echo    set S3_BUCKET=satb2-research-data
echo    set AWS_ENDPOINT_URL=http://localhost:4566
echo    set AWS_ACCESS_KEY_ID=test
echo    set AWS_SECRET_ACCESS_KEY=test
echo    set BACKEND_URL=http://localhost:8080
echo    python worker.py
echo ================================================
pause
