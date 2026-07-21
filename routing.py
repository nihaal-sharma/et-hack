"""
routing.py — Geospatial Routing with NetworkX
Creates a 10x10 grid graph representing the factory floor.
Implements A* pathfinding with dynamic hazard avoidance —
hazardous nodes get infinite weight so the algorithm routes around them.
"""

import networkx as nx
from typing import List, Tuple, Optional, Dict

GRID_SIZE = 10

# Exit nodes are placed at the edges of the factory
EXIT_NODES = [
    (0, 0),   # NW corner — Main entrance
    (9, 0),   # NE corner — Loading dock exit
    (0, 9),   # SW corner — Emergency exit A
    (9, 9),   # SE corner — Emergency exit B
    (4, 0),   # North center — Fire exit
    (5, 9),   # South center — Fire exit
]


def build_factory_grid() -> nx.Graph:
    """
    Build a 10x10 grid graph with weighted edges.
    Each node represents a factory floor cell, edges represent walkable paths.
    Default edge weight is 1.0 (normal traversal cost).
    """
    G = nx.grid_2d_graph(GRID_SIZE, GRID_SIZE)

    # Add diagonal edges for more realistic movement
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):
            # Diagonal neighbors
            for dx, dy in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nx2, ny2 = x + dx, y + dy
                if 0 <= nx2 < GRID_SIZE and 0 <= ny2 < GRID_SIZE:
                    G.add_edge((x, y), (nx2, ny2))

    # Set default weights
    for u, v in G.edges():
        # Diagonal edges cost sqrt(2) ≈ 1.414
        dx = abs(u[0] - v[0])
        dy = abs(u[1] - v[1])
        if dx + dy == 2:  # diagonal
            G[u][v]['weight'] = 1.414
        else:
            G[u][v]['weight'] = 1.0

    return G


def apply_hazard_weights(G: nx.Graph, hazardous_nodes: List[Tuple[int, int]]) -> nx.Graph:
    """
    Apply infinite weight to all edges connected to hazardous nodes.
    This forces the routing algorithm to completely avoid these cells.
    Returns a copy of the graph with modified weights.
    """
    G_copy = G.copy()

    for node in hazardous_nodes:
        if node in G_copy.nodes():
            # Set all edges touching this node to extremely high weight
            for neighbor in G_copy.neighbors(node):
                G_copy[node][neighbor]['weight'] = 999999

    return G_copy


def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Euclidean distance heuristic for A*."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def find_nearest_safe_exit(G: nx.Graph, start: Tuple[int, int],
                           hazardous_nodes: List[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """Find the nearest exit node that is not hazardous."""
    safe_exits = [e for e in EXIT_NODES if e not in hazardous_nodes]

    if not safe_exits:
        # If all designated exits are blocked, find any safe edge node
        for x in range(GRID_SIZE):
            for y in [0, GRID_SIZE - 1]:
                if (x, y) not in hazardous_nodes:
                    safe_exits.append((x, y))
        for y in range(GRID_SIZE):
            for x in [0, GRID_SIZE - 1]:
                if (x, y) not in hazardous_nodes:
                    safe_exits.append((x, y))

    if not safe_exits:
        return None

    # Sort by heuristic distance to start
    safe_exits.sort(key=lambda e: heuristic(start, e))
    return safe_exits[0]


def get_evacuation_route(
    start: Tuple[int, int],
    hazardous_nodes: List[Tuple[int, int]],
    exit_node: Optional[Tuple[int, int]] = None
) -> Dict:
    """
    Calculate the optimal evacuation route using A* algorithm.

    Args:
        start: Starting grid position (x, y)
        hazardous_nodes: List of grid cells to avoid
        exit_node: Target exit. If None, nearest safe exit is selected.

    Returns:
        Dict with path, distance, exit_node, algorithm used, and hazards avoided.
    """
    G = build_factory_grid()

    # Validate start node
    if start[0] < 0 or start[0] >= GRID_SIZE or start[1] < 0 or start[1] >= GRID_SIZE:
        return {"error": f"Start position {start} is out of grid bounds", "path": []}

    if start in hazardous_nodes:
        return {
            "warning": "Start position is in a hazardous zone! Finding escape route.",
            "path": [],
            "start": list(start),
            "hazardous_nodes": [list(h) for h in hazardous_nodes]
        }

    # Select exit
    if exit_node is None:
        exit_node = find_nearest_safe_exit(G, start, hazardous_nodes)

    if exit_node is None:
        return {"error": "No safe exit available!", "path": []}

    # Apply hazard weights
    G_weighted = apply_hazard_weights(G, hazardous_nodes)

    try:
        # A* pathfinding
        path = nx.astar_path(
            G_weighted, start, exit_node,
            heuristic=heuristic, weight='weight'
        )
        distance = nx.astar_path_length(
            G_weighted, start, exit_node,
            heuristic=heuristic, weight='weight'
        )

        return {
            "path": [list(p) for p in path],
            "distance": round(distance, 2),
            "start": list(start),
            "exit_node": list(exit_node),
            "steps": len(path) - 1,
            "algorithm": "A*",
            "hazards_avoided": [list(h) for h in hazardous_nodes],
            "status": "route_found"
        }

    except nx.NetworkXNoPath:
        # Fallback: try Dijkstra with all exits
        for backup_exit in EXIT_NODES:
            if backup_exit not in hazardous_nodes and backup_exit != exit_node:
                try:
                    path = nx.dijkstra_path(G_weighted, start, backup_exit, weight='weight')
                    distance = nx.dijkstra_path_length(G_weighted, start, backup_exit, weight='weight')
                    return {
                        "path": [list(p) for p in path],
                        "distance": round(distance, 2),
                        "start": list(start),
                        "exit_node": list(backup_exit),
                        "steps": len(path) - 1,
                        "algorithm": "Dijkstra (fallback)",
                        "hazards_avoided": [list(h) for h in hazardous_nodes],
                        "status": "route_found_fallback"
                    }
                except nx.NetworkXNoPath:
                    continue

        return {
            "error": "No viable evacuation route found! All paths blocked.",
            "path": [],
            "start": list(start),
            "hazardous_nodes": [list(h) for h in hazardous_nodes],
            "status": "no_route"
        }


def get_all_exit_routes(hazardous_nodes: List[Tuple[int, int]]) -> List[Dict]:
    """Get evacuation routes from all exit nodes (for visualization)."""
    routes = []
    for exit_node in EXIT_NODES:
        if exit_node not in hazardous_nodes:
            routes.append({
                "exit_node": list(exit_node),
                "is_safe": True
            })
        else:
            routes.append({
                "exit_node": list(exit_node),
                "is_safe": False,
                "blocked_by": "hazard"
            })
    return routes


if __name__ == "__main__":
    # Demo: find route from center avoiding some hazards
    print("🗺️  Factory Routing Demo")
    print("=" * 40)

    hazards = [(3, 3), (3, 4), (4, 3), (4, 4), (5, 5)]
    result = get_evacuation_route(
        start=(5, 5),
        hazardous_nodes=hazards
    )

    if "error" not in result:
        print(f"Start:    {result['start']}")
        print(f"Exit:     {result['exit_node']}")
        print(f"Steps:    {result['steps']}")
        print(f"Distance: {result['distance']}")
        print(f"Algorithm: {result['algorithm']}")
        print(f"Path: {' → '.join(str(p) for p in result['path'])}")
    else:
        print(f"Error: {result['error']}")
