"""
database.py — SQLite Database Layer
Initializes the local SQLite database with tables for sensor logs,
active permits, and shift logs. Provides helper functions for CRUD operations.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "safety_intel.db")


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grid_x INTEGER NOT NULL CHECK(grid_x >= 0 AND grid_x < 10),
            grid_y INTEGER NOT NULL CHECK(grid_y >= 0 AND grid_y < 10),
            sensor_type TEXT NOT NULL CHECK(sensor_type IN ('gas', 'temperature')),
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS active_permits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_type TEXT NOT NULL,
            grid_x INTEGER NOT NULL CHECK(grid_x >= 0 AND grid_x < 10),
            grid_y INTEGER NOT NULL CHECK(grid_y >= 0 AND grid_y < 10),
            issued_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expired', 'revoked'))
        );

        CREATE TABLE IF NOT EXISTS shift_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            worker_name TEXT NOT NULL,
            shift_start TEXT NOT NULL,
            shift_end TEXT NOT NULL,
            zone TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sensor_grid ON sensor_logs(grid_x, grid_y);
        CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_permit_grid ON active_permits(grid_x, grid_y);
        CREATE INDEX IF NOT EXISTS idx_permit_status ON active_permits(status);
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


def insert_sensor_log(grid_x: int, grid_y: int, sensor_type: str,
                      value: float, unit: str) -> int:
    """Insert a sensor reading and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sensor_logs (grid_x, grid_y, sensor_type, value, unit) VALUES (?, ?, ?, ?, ?)",
        (grid_x, grid_y, sensor_type, value, unit)
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def insert_permit(permit_type: str, grid_x: int, grid_y: int,
                  expires_at: str) -> int:
    """Insert an active permit and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO active_permits (permit_type, grid_x, grid_y, expires_at) VALUES (?, ?, ?, ?)",
        (permit_type, grid_x, grid_y, expires_at)
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def insert_shift_log(worker_id: str, worker_name: str,
                     shift_start: str, shift_end: str, zone: str) -> int:
    """Insert a shift log entry and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO shift_logs (worker_id, worker_name, shift_start, shift_end, zone) VALUES (?, ?, ?, ?, ?)",
        (worker_id, worker_name, shift_start, shift_end, zone)
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_latest_sensor_data() -> List[Dict]:
    """Get the most recent sensor reading for each grid cell and sensor type."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.grid_x, s.grid_y, s.sensor_type, s.value, s.unit, s.timestamp
        FROM sensor_logs s
        INNER JOIN (
            SELECT grid_x, grid_y, sensor_type, MAX(timestamp) as max_ts
            FROM sensor_logs
            GROUP BY grid_x, grid_y, sensor_type
        ) latest ON s.grid_x = latest.grid_x
                 AND s.grid_y = latest.grid_y
                 AND s.sensor_type = latest.sensor_type
                 AND s.timestamp = latest.max_ts
        ORDER BY s.grid_x, s.grid_y
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_active_permits() -> List[Dict]:
    """Get all currently active permits (not expired by time or status)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, permit_type, grid_x, grid_y, issued_at, expires_at, status
        FROM active_permits
        WHERE status = 'active' AND expires_at > datetime('now')
        ORDER BY grid_x, grid_y
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_grid_status() -> Dict:
    """
    Build a complete 10x10 grid status combining sensor data and permits.
    Returns a dict with grid cells and their current readings/permits.
    """
    sensors = get_latest_sensor_data()
    permits = get_active_permits()

    # Build grid lookup
    grid = {}
    for x in range(10):
        for y in range(10):
            grid[f"{x},{y}"] = {
                "grid_x": x,
                "grid_y": y,
                "sensors": {},
                "permits": [],
                "risk_level": "normal"
            }

    # Populate sensor data
    for s in sensors:
        key = f"{s['grid_x']},{s['grid_y']}"
        grid[key]["sensors"][s["sensor_type"]] = {
            "value": s["value"],
            "unit": s["unit"],
            "timestamp": s["timestamp"]
        }

    # Populate permits
    for p in permits:
        key = f"{p['grid_x']},{p['grid_y']}"
        grid[key]["permits"].append({
            "id": p["id"],
            "permit_type": p["permit_type"],
            "issued_at": p["issued_at"],
            "expires_at": p["expires_at"]
        })

    # Classify risk levels
    for key, cell in grid.items():
        gas = cell["sensors"].get("gas", {}).get("value", 0)
        temp = cell["sensors"].get("temperature", {}).get("value", 0)
        has_hot_work = any(p["permit_type"] == "hot_work" for p in cell["permits"])

        if has_hot_work and gas > 50:
            cell["risk_level"] = "critical"
        elif gas > 70 or temp > 85:
            cell["risk_level"] = "danger"
        elif gas > 40 or temp > 65 or has_hot_work:
            cell["risk_level"] = "warning"
        else:
            cell["risk_level"] = "normal"

    return {
        "grid": list(grid.values()),
        "total_sensors": len(sensors),
        "active_permits": len(permits),
        "timestamp": datetime.now().isoformat()
    }


def cleanup_old_data(hours: int = 1):
    """Remove sensor data older than specified hours."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sensor_logs WHERE timestamp < datetime('now', ?)",
        (f'-{hours} hours',)
    )
    # Expire old permits
    cursor.execute(
        "UPDATE active_permits SET status = 'expired' WHERE expires_at < datetime('now') AND status = 'active'"
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("[DB] Schema created successfully.")
