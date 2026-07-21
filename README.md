# SentinelAI: Multi-Agent Industrial Safety Intelligence 

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![CrewAI](https://img.shields.io/badge/AI-CrewAI-FF9900.svg)](https://www.crewai.com/)
[![NetworkX](https://img.shields.io/badge/Routing-NetworkX-brightgreen.svg)](https://networkx.org/)

**ET AI Hackathon 2026 - Theme 1: AI-Powered Industrial Safety Intelligence for Zero-Harm Operations**

## Overview
Heavy industrial operations face severe safety challenges due to information fragmentation. Catastrophic events often occur because isolated signals (e.g., minor gas leaks, ongoing hot-work permits, and shift changeovers) fail to trigger a unified risk response. 

**SentinelAI** is a unified, real-time safety intelligence platform designed to eliminate fatal false negatives. By fusing multi-agent AI reasoning with dynamic spatial pathfinding, the platform detects compound risks hours before they escalate and autonomously routes personnel away from hazard zones.

##  Core Features

*   ** Autonomous Multi-Agent Reasoning (CrewAI):** Decouples safety monitoring into specialized AI agents (Sensor Analyst, Permit Auditor, Evacuation Orchestrator) that evaluate overlapping operational variables across time and space.
*   ** Dynamic Spatial Evacuation Rerouting:** Utilizes graph-based pathfinding algorithms ($A^*$ and Dijkstra's) via `NetworkX`. When a compound hazard is detected, edge weights $w_{ij}$ in the affected nodes are dynamically penalized to infinity, ensuring evacuation paths route safely around active threat zones.
*   ** Zero-Delay Regulatory Compliance (RAG):** Employs a local vector database (ChromaDB) to cross-reference active plant conditions against statutory regulations (OISD, DGMS, The Factory Act) instantly[cite: 2].
*   ** Real-Time Situational Dashboard:** A fast, responsive frontend using `Leaflet.js` over custom plant blueprints to render live safety heatmaps and optimized evacuation routes[cite: 2].

##  Technical Architecture

This project is built using a lightweight, open-source stack optimized for rapid edge deployment:

*   **Backend:** Python, FastAPI, SQLite
*   **AI/Orchestration:** CrewAI, Google Gemini 1.5 Flash (LLM Brain)
*   **Vector Database:** ChromaDB (with HuggingFace `all-MiniLM-L6-v2` embeddings)
*   **Routing Engine:** NetworkX ($A^*$ / Dijkstra's implementation)
*   **Frontend:** HTML5, Vanilla JavaScript, Leaflet.js
*   **Alerting:** Automated Discord/Telegram Webhooks[cite: 2]

##  Installation & Setup

### Prerequisites
* Python 3.10+
* Git
* A free Google Gemini API Key

### 1. Clone the Repository
```bash
git clone [https://github.com/yourusername/SentinelAI.git](https://github.com/yourusername/SentinelAI.git)
cd SentinelAI
