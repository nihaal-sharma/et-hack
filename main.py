"""
main.py — FastAPI Backend Server
Exposes REST endpoints for sensor data, risk evaluation, and evacuation routing.
Serves the static frontend dashboard.
"""

import os
import threading
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, List

from database import init_db, get_grid_status, get_active_permits, get_latest_sensor_data
from routing import get_evacuation_route, get_all_exit_routes, EXIT_NODES
from agent_logic import evaluate_risk, evaluate_risk_with_crewai

# Initialize database on startup
init_db()

# Create FastAPI app
app = FastAPI(
    title="AI-Powered Industrial Safety Intelligence",
    description="Real-time compound risk detection and evacuation routing for industrial environments",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Cache for latest risk evaluation
_latest_risk_cache = {"result": None, "evaluating": False}


# ─── API Endpoints ──────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    """Serve the main dashboard page."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Frontend not found. Place index.html in /static/"}, status_code=404)


@app.get("/api/sensors")
async def get_sensors():
    """
    GET /api/sensors
    Returns current grid sensor status and active permits.
    Each grid cell includes gas/temperature readings, permits, and risk level.
    """
    grid_status = get_grid_status()
    return JSONResponse(content=grid_status)


@app.get("/api/permits")
async def get_permits():
    """
    GET /api/permits
    Returns all currently active work permits.
    """
    permits = get_active_permits()
    return JSONResponse(content={"permits": permits, "count": len(permits)})


@app.post("/api/evaluate_risk")
async def evaluate_risk_endpoint(use_crewai: bool = Query(default=False)):
    """
    POST /api/evaluate_risk
    Triggers the AI risk detection engine.
    If use_crewai=true and GOOGLE_API_KEY is set, uses CrewAI + Gemini.
    Otherwise uses the rule-based compound risk analysis.
    """
    if _latest_risk_cache["evaluating"]:
        return JSONResponse(
            content={"status": "already_evaluating", "message": "Risk evaluation in progress..."},
            status_code=202
        )

    _latest_risk_cache["evaluating"] = True

    try:
        if use_crewai:
            result = evaluate_risk_with_crewai()
        else:
            result = evaluate_risk()

        _latest_risk_cache["result"] = result
        _latest_risk_cache["evaluating"] = False
        return JSONResponse(content=result)

    except Exception as e:
        _latest_risk_cache["evaluating"] = False
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )


@app.get("/api/evacuation_route")
async def get_evacuation_route_endpoint(
    start_x: int = Query(5, ge=0, lt=10, description="Start grid X coordinate"),
    start_y: int = Query(5, ge=0, lt=10, description="Start grid Y coordinate"),
    exit_x: Optional[int] = Query(None, ge=0, lt=10, description="Exit grid X (auto-select if omitted)"),
    exit_y: Optional[int] = Query(None, ge=0, lt=10, description="Exit grid Y (auto-select if omitted)")
):
    """
    GET /api/evacuation_route
    Calculates the optimal evacuation route using A* algorithm.
    Avoids hazardous grid cells detected by the risk engine.
    """
    # Get hazardous nodes from latest risk evaluation, or evaluate fresh
    hazardous_nodes = []

    if _latest_risk_cache["result"]:
        hazardous_nodes = _latest_risk_cache["result"].get("hazardous_nodes", [])
    else:
        # Quick evaluation to find hazards
        quick_eval = evaluate_risk()
        hazardous_nodes = quick_eval.get("hazardous_nodes", [])
        _latest_risk_cache["result"] = quick_eval

    # Convert to tuples for routing
    hazard_tuples = [tuple(h) for h in hazardous_nodes]

    # Set exit node if specified
    exit_node = None
    if exit_x is not None and exit_y is not None:
        exit_node = (exit_x, exit_y)

    # Calculate route
    route = get_evacuation_route(
        start=(start_x, start_y),
        hazardous_nodes=hazard_tuples,
        exit_node=exit_node
    )

    # Add exit info
    route["available_exits"] = get_all_exit_routes(hazard_tuples)

    return JSONResponse(content=route)


@app.get("/api/exits")
async def get_exits():
    """
    GET /api/exits
    Returns all designated exit nodes and their safety status.
    """
    hazardous_nodes = []
    if _latest_risk_cache["result"]:
        hazardous_nodes = [tuple(h) for h in _latest_risk_cache["result"].get("hazardous_nodes", [])]

    exits = get_all_exit_routes(hazardous_nodes)
    return JSONResponse(content={"exits": exits})


@app.get("/api/status")
async def get_system_status():
    """
    GET /api/status
    System health check and overview.
    """
    grid = get_grid_status()
    has_risk_data = _latest_risk_cache["result"] is not None

    critical_cells = sum(1 for c in grid["grid"] if c["risk_level"] == "critical")
    warning_cells = sum(1 for c in grid["grid"] if c["risk_level"] == "warning")
    danger_cells = sum(1 for c in grid["grid"] if c["risk_level"] == "danger")

    return JSONResponse(content={
        "status": "online",
        "grid_size": "10x10",
        "total_sensor_readings": grid["total_sensors"],
        "active_permits": grid["active_permits"],
        "risk_summary": {
            "critical": critical_cells,
            "danger": danger_cells,
            "warning": warning_cells,
            "normal": 100 - critical_cells - warning_cells - danger_cells
        },
        "last_evaluation": _latest_risk_cache["result"]["timestamp"] if has_risk_data else None,
        "evaluating": _latest_risk_cache["evaluating"]
    })


if __name__ == "__main__":
    import sys, os
    if os.name == 'nt':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    import uvicorn
    print("\n[FACTORY] Starting AI Safety Intelligence Server...")
    print("   Dashboard: http://localhost:8000")
    print("   API Docs:  http://localhost:8000/docs\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
