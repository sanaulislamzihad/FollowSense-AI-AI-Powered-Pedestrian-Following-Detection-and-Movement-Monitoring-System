@echo off
REM Starts the FastAPI backend (port 8000) and the React dev server (port 5173).
start "FollowSense API" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "FollowSense Web" cmd /k "cd /d %~dp0frontend && npm run dev"
echo Dashboard: http://localhost:5173   API docs: http://localhost:8000/docs
