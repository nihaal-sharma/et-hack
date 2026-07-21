"""
mock_data.py — IoT Sensor Data Simulator
Continuously generates realistic mock sensor data (gas PPM, temperature)
and work permits across a 10x10 factory grid and inserts into SQLite.
"""

import random
import time
import signal
import sys
import os

# Fix Windows console encoding for Unicode
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from datetime import datetime, timedelta
from database import init_db, insert_sensor_log, insert_permit, cleanup_old_data

# --- Configuration ---
GRID_SIZE = 10
GENERATION_INTERVAL = 2  # seconds between data batches
SENSORS_PER_BATCH = 15   # number of sensor readings per batch
PERMIT_CHANCE = 0.08     # chance of generating a new permit per cycle

# --- Realistic Sensor Profiles ---
# Different zones of the factory have different baseline readings
ZONE_PROFILES = {
    "welding_bay":    {"gas_base": 35, "gas_var": 30, "temp_base": 55, "temp_var": 25, "cells": [(0,0),(0,1),(1,0),(1,1)]},
    "chemical_store": {"gas_base": 45, "gas_var": 40, "temp_base": 30, "temp_var": 10, "cells": [(8,8),(8,9),(9,8),(9,9)]},
    "assembly_line":  {"gas_base": 10, "gas_var": 15, "temp_base": 40, "temp_var": 15, "cells": [(4,0),(5,0),(6,0),(4,1),(5,1),(6,1)]},
    "furnace_area":   {"gas_base": 20, "gas_var": 20, "temp_base": 70, "temp_var": 20, "cells": [(0,8),(0,9),(1,8),(1,9)]},
    "loading_dock":   {"gas_base": 15, "gas_var": 10, "temp_base": 35, "temp_var": 10, "cells": [(7,4),(8,4),(9,4),(7,5),(8,5),(9,5)]},
}

PERMIT_TYPES = ["hot_work", "confined_space", "electrical", "excavation", "chemical_handling"]

# Track running state for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global running
    print("\n[SIM] Shutting down simulator...")
    running = False


signal.signal(signal.SIGINT, signal_handler)


def get_zone_for_cell(x: int, y: int) -> dict:
    """Get the zone profile for a given grid cell, or a default profile."""
    for zone_name, profile in ZONE_PROFILES.items():
        if (x, y) in profile["cells"]:
            return profile
    # Default factory floor
    return {"gas_base": 8, "gas_var": 12, "temp_base": 35, "temp_var": 10}


def generate_sensor_reading(x: int, y: int, sensor_type: str) -> float:
    """Generate a realistic sensor value with occasional spikes."""
    profile = get_zone_for_cell(x, y)

    if sensor_type == "gas":
        base = profile["gas_base"]
        variance = profile["gas_var"]
    else:
        base = profile["temp_base"]
        variance = profile["temp_var"]

    # Normal reading with gaussian distribution
    value = random.gauss(base, variance * 0.3)

    # 8% chance of a dangerous spike
    if random.random() < 0.08:
        spike = random.uniform(1.5, 3.0)
        value *= spike
        print(f"  [!] SPIKE on ({x},{y}) {sensor_type}: {value:.1f}")

    # Clamp to realistic ranges
    if sensor_type == "gas":
        value = max(0, min(value, 200))  # 0-200 ppm
    else:
        value = max(15, min(value, 120))  # 15-120 °C

    return round(value, 1)


def generate_batch():
    """Generate a batch of sensor readings across the grid."""
    readings = []
    cells_to_read = set()

    # Pick random cells to read this cycle
    while len(cells_to_read) < SENSORS_PER_BATCH:
        x = random.randint(0, GRID_SIZE - 1)
        y = random.randint(0, GRID_SIZE - 1)
        cells_to_read.add((x, y))

    for (x, y) in cells_to_read:
        # Each cell gets both gas and temperature readings
        for sensor_type, unit in [("gas", "ppm"), ("temperature", "°C")]:
            value = generate_sensor_reading(x, y, sensor_type)
            row_id = insert_sensor_log(x, y, sensor_type, value, unit)
            readings.append({
                "id": row_id, "grid": f"({x},{y})",
                "type": sensor_type, "value": value, "unit": unit
            })

    return readings


def maybe_generate_permit():
    """Possibly generate a new work permit."""
    if random.random() < PERMIT_CHANCE:
        permit_type = random.choice(PERMIT_TYPES)
        x = random.randint(0, GRID_SIZE - 1)
        y = random.randint(0, GRID_SIZE - 1)
        # Permit lasts 5-30 minutes
        duration = random.randint(5, 30)
        expires_at = (datetime.now() + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")

        permit_id = insert_permit(permit_type, x, y, expires_at)
        print(f"  [PERMIT] NEW: {permit_type} at ({x},{y}) -- expires in {duration}min [ID:{permit_id}]")
        return True
    return False


def run_simulator():
    """Main simulation loop."""
    global running

    print("=" * 60)
    print("  [FACTORY] Industrial IoT Sensor Simulator")
    print("=" * 60)
    print(f"  Grid Size:   {GRID_SIZE}x{GRID_SIZE}")
    print(f"  Interval:    {GENERATION_INTERVAL}s")
    print(f"  Sensors/Batch: {SENSORS_PER_BATCH}")
    print("=" * 60)
    print("  Press Ctrl+C to stop\n")

    # Initialize database
    init_db()

    # Seed some initial permits
    for _ in range(3):
        permit_type = random.choice(PERMIT_TYPES)
        x = random.randint(0, GRID_SIZE - 1)
        y = random.randint(0, GRID_SIZE - 1)
        duration = random.randint(10, 45)
        expires_at = (datetime.now() + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
        insert_permit(permit_type, x, y, expires_at)
        print(f"  [SEED] {permit_type} permit at ({x},{y})")

    print()
    cycle = 0

    while running:
        cycle += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[Cycle {cycle:04d}] {timestamp} — Generating sensor data...")

        # Generate sensor readings
        readings = generate_batch()

        # Summarize
        gas_readings = [r for r in readings if r["type"] == "gas"]
        temp_readings = [r for r in readings if r["type"] == "temperature"]
        max_gas = max((r["value"] for r in gas_readings), default=0)
        max_temp = max((r["value"] for r in temp_readings), default=0)

        print(f"  [DATA] {len(readings)} readings | Max Gas: {max_gas} ppm | Max Temp: {max_temp} C")

        # Maybe create a new permit
        maybe_generate_permit()

        # Periodic cleanup (every 50 cycles)
        if cycle % 50 == 0:
            cleanup_old_data(hours=1)
            print("  [CLEAN] Cleaned up old data")

        print()

        # Wait for next cycle
        try:
            time.sleep(GENERATION_INTERVAL)
        except KeyboardInterrupt:
            running = False

    print("[SIM] Simulator stopped.")


if __name__ == "__main__":
    run_simulator()
