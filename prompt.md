You are an expert full-stack AI engineer participating in a high-stakes hackathon. Your task is to build the foundational prototype for an "AI-Powered Industrial Safety Intelligence" platform. This system prevents fatal workplace accidents by detecting compound risks using simulated IoT data, multi-agent AI, and geospatial routing.

We are strictly using a free, open-source stack. Do not use or suggest any paid APIs (like OpenAI or Google Maps). 

### Tech Stack Requirements:
- Backend: Python (FastAPI)
- Database: SQLite (local)
- AI Orchestration: CrewAI 
- LLM API: Google Gemini 1.5 Flash (via free API key)
- RAG Vector Store: ChromaDB (local) with HuggingFace embeddings
- Geospatial/Routing: NetworkX (implementing A* and Dijkstra's algorithm for dynamic hazard avoidance)
- Frontend: HTML/Vanilla JS + Leaflet.js (using a static blueprint image as a custom map grid)

### Project Architecture & Execution Steps:
Please generate the code for this project step-by-step, creating the following modules:

1. Database & Simulation Layer (`mock_data.py` & `database.py`)
- Initialize a local SQLite database with tables for: `sensor_logs` (gas, temp), `active_permits` (type, location grid), and `shift_logs`.
- Write a Python script that continuously generates mock JSON payloads simulating IoT sensor streams across a 10x10 factory grid and inserts them into the DB.

2. Geospatial Routing Logic (`routing.py`)
- Use NetworkX to create a 10x10 grid representing the factory floor.
- Implement a function using A* or Dijkstra's algorithm to calculate the shortest path from any given node to an "exit" node.
- Crucially, this function must dynamically accept a list of "hazardous nodes" (where compound risks are detected) and assign them an infinitely high weight so the routing algorithm completely avoids them.

3. AI Risk Detection Engine (`agent_logic.py`)
- Set up a basic CrewAI script with two agents: a 'Sensor Analyst' and a 'Safety Auditor'.
- Configure the LLM to use the `gemini-1.5-flash` model.
- Write the logic so the agents cross-reference the active mock database. If a "hot work permit" exists in the same grid coordinate where a gas sensor reads a spike, the agent must output a "CRITICAL COMPOUND RISK" JSON payload.

4. Backend API (`main.py`)
- Build a FastAPI server that exposes the following endpoints:
  - `GET /api/sensors` (returns current grid status and active permits)
  - `POST /api/evaluate_risk` (triggers the CrewAI agent logic)
  - `GET /api/evacuation_route` (calls the routing algorithm based on current hazards)

5. Visual Frontend (`index.html` & `app.js`)
- Create a single-page web dashboard.
- Integrate Leaflet.js using `L.CRS.Simple` to load a static image (a placeholder factory blueprint) as a coordinate map.
- Write a polling function in JS that hits the FastAPI endpoints every 3 seconds to update the map with red/yellow/green hazard zones and draws a polyline showing the active A* evacuation route.

Before writing the code, briefly acknowledge this architecture. Then, start by generating the `database.py` and `mock_data.py` files to lay the foundation.