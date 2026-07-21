"""
agent_logic.py — AI Risk Detection Engine (CrewAI + Google Gemini)
Multi-agent system with a Sensor Analyst and Safety Auditor that
cross-reference sensor data with active permits to detect compound risks.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Fix Windows console encoding
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from database import get_latest_sensor_data, get_active_permits, get_grid_status

# --- Thresholds for risk classification ---
GAS_WARNING_THRESHOLD = 40     # ppm
GAS_DANGER_THRESHOLD = 70      # ppm
GAS_CRITICAL_THRESHOLD = 50    # ppm (when combined with hot work)
TEMP_WARNING_THRESHOLD = 65    # °C
TEMP_DANGER_THRESHOLD = 85     # °C


def analyze_sensors() -> Dict:
    """
    Sensor Analyst logic: Analyze latest sensor data for anomalies.
    Returns categorized readings by risk level.
    """
    sensors = get_latest_sensor_data()

    anomalies = []
    warnings = []
    normal_count = 0

    # Group readings by cell
    cell_data = {}
    for s in sensors:
        key = (s["grid_x"], s["grid_y"])
        if key not in cell_data:
            cell_data[key] = {}
        cell_data[key][s["sensor_type"]] = s["value"]

    for (x, y), readings in cell_data.items():
        gas_val = readings.get("gas", 0)
        temp_val = readings.get("temperature", 0)

        cell_status = {
            "grid_x": x,
            "grid_y": y,
            "gas_ppm": gas_val,
            "temperature_c": temp_val,
            "flags": []
        }

        if gas_val > GAS_DANGER_THRESHOLD:
            cell_status["flags"].append(f"DANGEROUS gas level: {gas_val} ppm")
            anomalies.append(cell_status)
        elif gas_val > GAS_WARNING_THRESHOLD:
            cell_status["flags"].append(f"Elevated gas level: {gas_val} ppm")
            warnings.append(cell_status)

        if temp_val > TEMP_DANGER_THRESHOLD:
            cell_status["flags"].append(f"DANGEROUS temperature: {temp_val}°C")
            if cell_status not in anomalies:
                anomalies.append(cell_status)
        elif temp_val > TEMP_WARNING_THRESHOLD:
            cell_status["flags"].append(f"Elevated temperature: {temp_val}°C")
            if cell_status not in warnings and cell_status not in anomalies:
                warnings.append(cell_status)

        if not cell_status["flags"]:
            normal_count += 1

    return {
        "anomalies": anomalies,
        "warnings": warnings,
        "normal_cells": normal_count,
        "total_cells_analyzed": len(cell_data),
        "timestamp": datetime.now().isoformat()
    }


def audit_compound_risks(sensor_analysis: Dict) -> Dict:
    """
    Safety Auditor logic: Cross-reference sensor anomalies with active permits
    to detect compound risks (e.g., hot work + gas spike = explosion risk).
    """
    permits = get_active_permits()
    compound_risks = []
    hazardous_nodes = []

    # Build permit lookup by grid cell
    permit_map = {}
    for p in permits:
        key = (p["grid_x"], p["grid_y"])
        if key not in permit_map:
            permit_map[key] = []
        permit_map[key].append(p)

    # Check each anomaly and warning against permits
    all_flagged = sensor_analysis["anomalies"] + sensor_analysis["warnings"]

    for cell in all_flagged:
        cell_key = (cell["grid_x"], cell["grid_y"])
        cell_permits = permit_map.get(cell_key, [])

        for permit in cell_permits:
            risk_entry = {
                "grid_x": cell["grid_x"],
                "grid_y": cell["grid_y"],
                "risk_level": "CRITICAL",
                "compound_type": "",
                "description": "",
                "sensor_data": {
                    "gas_ppm": cell["gas_ppm"],
                    "temperature_c": cell["temperature_c"]
                },
                "permit": {
                    "type": permit["permit_type"],
                    "id": permit["id"],
                    "expires_at": permit["expires_at"]
                },
                "recommended_action": ""
            }

            # HOT WORK + GAS SPIKE = EXPLOSION RISK (MOST CRITICAL)
            if permit["permit_type"] == "hot_work" and cell["gas_ppm"] > GAS_CRITICAL_THRESHOLD:
                risk_entry["compound_type"] = "EXPLOSION_RISK"
                risk_entry["description"] = (
                    f"CRITICAL COMPOUND RISK: Hot work permit active at ({cell['grid_x']},{cell['grid_y']}) "
                    f"with gas reading of {cell['gas_ppm']} ppm. "
                    f"Open flame/spark source combined with combustible gas creates immediate explosion hazard."
                )
                risk_entry["recommended_action"] = (
                    "IMMEDIATE: Evacuate zone. Suspend hot work permit. "
                    "Deploy gas suppression. Alert fire response team."
                )
                compound_risks.append(risk_entry)
                hazardous_nodes.append([cell["grid_x"], cell["grid_y"]])

            # HOT WORK + HIGH TEMP = FIRE RISK
            elif permit["permit_type"] == "hot_work" and cell["temperature_c"] > TEMP_WARNING_THRESHOLD:
                risk_entry["risk_level"] = "HIGH"
                risk_entry["compound_type"] = "FIRE_RISK"
                risk_entry["description"] = (
                    f"HIGH RISK: Hot work at ({cell['grid_x']},{cell['grid_y']}) "
                    f"with elevated temperature of {cell['temperature_c']}°C. "
                    f"Combined heat sources increase fire probability."
                )
                risk_entry["recommended_action"] = (
                    "Monitor closely. Ensure fire watch is posted. "
                    "Pre-position extinguishers. Consider permit suspension."
                )
                compound_risks.append(risk_entry)
                hazardous_nodes.append([cell["grid_x"], cell["grid_y"]])

            # CONFINED SPACE + GAS = ASPHYXIATION RISK
            elif permit["permit_type"] == "confined_space" and cell["gas_ppm"] > GAS_WARNING_THRESHOLD:
                risk_entry["risk_level"] = "CRITICAL"
                risk_entry["compound_type"] = "ASPHYXIATION_RISK"
                risk_entry["description"] = (
                    f"CRITICAL: Confined space entry at ({cell['grid_x']},{cell['grid_y']}) "
                    f"with gas reading of {cell['gas_ppm']} ppm. "
                    f"Toxic/combustible gas in enclosed space is immediately dangerous to life."
                )
                risk_entry["recommended_action"] = (
                    "IMMEDIATE: Evacuate confined space. Ventilate area. "
                    "Do not re-enter without air monitoring confirmation."
                )
                compound_risks.append(risk_entry)
                hazardous_nodes.append([cell["grid_x"], cell["grid_y"]])

            # CHEMICAL HANDLING + HIGH TEMP = REACTION RISK
            elif permit["permit_type"] == "chemical_handling" and cell["temperature_c"] > TEMP_WARNING_THRESHOLD:
                risk_entry["risk_level"] = "HIGH"
                risk_entry["compound_type"] = "CHEMICAL_REACTION_RISK"
                risk_entry["description"] = (
                    f"HIGH RISK: Chemical handling at ({cell['grid_x']},{cell['grid_y']}) "
                    f"with temperature at {cell['temperature_c']}°C. "
                    f"Elevated heat may accelerate chemical reactions or cause container failure."
                )
                risk_entry["recommended_action"] = (
                    "Reduce ambient temperature. Verify chemical storage conditions. "
                    "Check for incompatible material proximity."
                )
                compound_risks.append(risk_entry)
                hazardous_nodes.append([cell["grid_x"], cell["grid_y"]])

    # Also flag standalone danger zones (no permit but extreme readings)
    for cell in sensor_analysis["anomalies"]:
        cell_key = (cell["grid_x"], cell["grid_y"])
        node = [cell["grid_x"], cell["grid_y"]]
        if node not in hazardous_nodes and (cell["gas_ppm"] > GAS_DANGER_THRESHOLD or cell["temperature_c"] > TEMP_DANGER_THRESHOLD):
            hazardous_nodes.append(node)

    # Deduplicate hazardous nodes
    unique_hazards = []
    for h in hazardous_nodes:
        if h not in unique_hazards:
            unique_hazards.append(h)

    return {
        "compound_risks": compound_risks,
        "hazardous_nodes": unique_hazards,
        "total_risks_detected": len(compound_risks),
        "critical_count": sum(1 for r in compound_risks if r["risk_level"] == "CRITICAL"),
        "high_count": sum(1 for r in compound_risks if r["risk_level"] == "HIGH"),
        "permits_analyzed": len(permits),
        "timestamp": datetime.now().isoformat()
    }


def evaluate_risk() -> Dict:
    """
    Main entry point: Run the full risk evaluation pipeline.
    1. Sensor Analyst scans for anomalies
    2. Safety Auditor cross-references with permits for compound risks
    3. Returns complete risk assessment with hazardous nodes for routing
    """
    print("[AGENT] Sensor Analyst scanning grid...")
    sensor_analysis = analyze_sensors()
    print(f"[AGENT]   Found {len(sensor_analysis['anomalies'])} anomalies, "
          f"{len(sensor_analysis['warnings'])} warnings")

    print("[AGENT] Safety Auditor cross-referencing permits...")
    risk_assessment = audit_compound_risks(sensor_analysis)
    print(f"[AGENT]   Detected {risk_assessment['total_risks_detected']} compound risks "
          f"({risk_assessment['critical_count']} CRITICAL, {risk_assessment['high_count']} HIGH)")

    # Build final response
    result = {
        "status": "evaluation_complete",
        "sensor_analysis": {
            "anomalies": len(sensor_analysis["anomalies"]),
            "warnings": len(sensor_analysis["warnings"]),
            "normal_cells": sensor_analysis["normal_cells"],
            "details": sensor_analysis["anomalies"] + sensor_analysis["warnings"]
        },
        "risk_assessment": risk_assessment,
        "hazardous_nodes": risk_assessment["hazardous_nodes"],
        "summary": _generate_summary(risk_assessment),
        "timestamp": datetime.now().isoformat()
    }

    return result


def _generate_summary(risk_assessment: Dict) -> str:
    """Generate a human-readable summary of the risk assessment."""
    total = risk_assessment["total_risks_detected"]
    critical = risk_assessment["critical_count"]
    high = risk_assessment["high_count"]

    if critical > 0:
        return (
            f"[CRITICAL ALERT] {critical} critical compound risk(s) detected! "
            f"{high} additional high-risk situations. "
            f"Immediate evacuation may be required in affected zones. "
            f"{len(risk_assessment['hazardous_nodes'])} grid cells marked hazardous."
        )
    elif high > 0:
        return (
            f"[WARNING] {high} high-risk compound situation(s) detected. "
            f"Enhanced monitoring and precautions required. "
            f"{len(risk_assessment['hazardous_nodes'])} grid cells require attention."
        )
    elif total > 0:
        return (
            f"[NOTICE] {total} elevated risk situation(s) noted. "
            f"Conditions being monitored."
        )
    else:
        return "[OK] ALL CLEAR: No compound risks detected. Factory operations normal."


# Optional: CrewAI integration (if crewai is installed)
def evaluate_risk_with_crewai() -> Dict:
    """
    Enhanced risk evaluation using CrewAI agents with Google Gemini.
    Falls back to rule-based analysis if CrewAI/Gemini are not available.
    """
    try:
        from crewai import Agent, Task, Crew
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("[AGENT] No GOOGLE_API_KEY found. Using rule-based analysis.")
            return evaluate_risk()

        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=api_key,
            temperature=0.1
        )

        # Get current data
        grid_status = get_grid_status()
        sensor_data_str = json.dumps(grid_status["grid"][:20], indent=2)  # Limit for context
        permits_str = json.dumps(get_active_permits(), indent=2)

        # Define agents
        sensor_analyst = Agent(
            role="Industrial Sensor Analyst",
            goal="Analyze IoT sensor data to identify dangerous readings and anomalies on the factory floor",
            backstory=(
                "You are an expert industrial safety sensor analyst with 20 years of experience "
                "monitoring gas levels, temperatures, and environmental conditions in manufacturing plants. "
                "You can quickly identify dangerous patterns in sensor data."
            ),
            llm=llm,
            verbose=True
        )

        safety_auditor = Agent(
            role="Compound Risk Safety Auditor",
            goal="Cross-reference sensor anomalies with active work permits to identify compound risks that could cause fatal accidents",
            backstory=(
                "You are a senior safety auditor specializing in compound risk analysis. "
                "You understand that the most dangerous industrial accidents occur when multiple "
                "risk factors coincide — like a gas leak near active welding (hot work). "
                "Your job is to find these deadly combinations before they cause harm."
            ),
            llm=llm,
            verbose=True
        )

        # Define tasks
        analysis_task = Task(
            description=(
                f"Analyze the following sensor data from the factory floor grid and identify any dangerous readings.\n"
                f"Sensor Data:\n{sensor_data_str}\n\n"
                f"Flag any gas readings above {GAS_WARNING_THRESHOLD} ppm or temperatures above {TEMP_WARNING_THRESHOLD}°C.\n"
                f"Output a JSON list of anomalous cells with their readings and risk flags."
            ),
            expected_output="JSON list of anomalous grid cells with sensor readings and risk flags",
            agent=sensor_analyst
        )

        audit_task = Task(
            description=(
                f"Cross-reference the sensor anomalies found by the Sensor Analyst with these active work permits:\n"
                f"Active Permits:\n{permits_str}\n\n"
                f"Identify COMPOUND RISKS where a dangerous sensor reading coincides with an active permit "
                f"at the same grid location. The most critical compound risk is: "
                f"hot_work permit + gas spike > {GAS_CRITICAL_THRESHOLD} ppm = EXPLOSION RISK.\n\n"
                f"Output a JSON object with: risk_level, compound_risks array, hazardous_nodes array, and summary."
            ),
            expected_output='JSON with risk_level, compound_risks, hazardous_nodes, and summary',
            agent=safety_auditor,
            context=[analysis_task]
        )

        # Execute crew
        crew = Crew(
            agents=[sensor_analyst, safety_auditor],
            tasks=[analysis_task, audit_task],
            verbose=True
        )

        crew_result = crew.kickoff()

        # Parse CrewAI result and merge with rule-based analysis
        rule_based = evaluate_risk()

        # Use CrewAI summary but keep structured data from rule-based
        rule_based["crewai_analysis"] = str(crew_result)
        rule_based["analysis_method"] = "crewai_enhanced"

        return rule_based

    except ImportError as e:
        print(f"[AGENT] CrewAI/LangChain not available ({e}). Using rule-based analysis.")
        return evaluate_risk()
    except Exception as e:
        print(f"[AGENT] CrewAI error: {e}. Falling back to rule-based analysis.")
        return evaluate_risk()


if __name__ == "__main__":
    print("=" * 60)
    print("  [AI] Risk Detection Engine -- Manual Test")
    print("=" * 60)

    result = evaluate_risk()
    print(json.dumps(result, indent=2))
