import math
from typing import Optional, Tuple
from passages_tool.editor.level import Level, PolylineType

def nearest_wall_edge(
    arch_pos: Tuple[float, float],
    level: Level
) -> Optional[Tuple[str, int, float, float]]:
    """
    Find the nearest Wall edge to arch_pos.
    Returns: (wall_polyline_id, edge_index, tangent_angle_degrees, distance)
    or None if there are no Wall polylines or edges.
    """
    px, pz = arch_pos
    best_dist = float('inf')
    best_res = None

    for pid, pl in level.polylines.items():
        if pl.type != PolylineType.WALL:
            continue
        verts = pl.vertices
        n = len(verts)
        if n < 2:
            continue

        num_edges = n if pl.closed else n - 1
        for i in range(num_edges):
            p0 = verts[i]
            p1 = verts[(i + 1) % n]
            
            x0, z0 = p0
            x1, z1 = p1
            
            dx = x1 - x0
            dz = z1 - z0
            lensq = dx*dx + dz*dz
            if lensq < 1e-9:
                t = 0.0
            else:
                t = ((px - x0) * dx + (pz - z0) * dz) / lensq
                t = max(0.0, min(1.0, t))
            
            cx = x0 + t * dx
            cz = z0 + t * dz
            dist = math.hypot(px - cx, pz - cz)
            
            if dist < best_dist:
                best_dist = dist
                tangent_ang = math.degrees(math.atan2(dz, dx)) % 360
                best_res = (pid, i, tangent_ang, dist)
                
    return best_res

def is_tangent_ambiguous(
    level: Level,
    wall_pid: str,
    edge_idx: int,
    arch_pos: Tuple[float, float],
    threshold_deg: float = 30.0
) -> bool:
    """
    Checks if the closest point on the edge is near a vertex, and if so,
    whether the angle of the adjacent edge differs from the current one
    by more than threshold_deg.
    """
    pl = level.polylines.get(wall_pid)
    if not pl or pl.type != PolylineType.WALL:
        return False
    
    verts = pl.vertices
    n = len(verts)
    if n < 2:
        return False
    
    p0 = verts[edge_idx]
    p1 = verts[(edge_idx + 1) % n]
    px, pz = arch_pos
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    lensq = dx*dx + dz*dz
    if lensq < 1e-9:
        t = 0.0
    else:
        t = ((px - p0[0]) * dx + (pz - p0[1]) * dz) / lensq
        t = max(0.0, min(1.0, t))
        
    NEAR_THRESHOLD_WORLD = 0.2
    
    dist_to_p0 = math.hypot(px - p0[0], pz - p0[1])
    dist_to_p1 = math.hypot(px - p1[0], pz - p1[1])
    
    near_vtx_idx = None
    if dist_to_p0 < NEAR_THRESHOLD_WORLD:
        near_vtx_idx = edge_idx
    elif dist_to_p1 < NEAR_THRESHOLD_WORLD:
        near_vtx_idx = (edge_idx + 1) % n
        
    if near_vtx_idx is None:
        return False
        
    num_edges = n if pl.closed else n - 1
    edge_a_idx = (near_vtx_idx - 1 + n) % n if pl.closed else near_vtx_idx - 1
    edge_b_idx = near_vtx_idx
    
    has_edge_a = (0 <= edge_a_idx < num_edges)
    has_edge_b = (0 <= edge_b_idx < num_edges)
    
    if not (has_edge_a and has_edge_b):
        return False
        
    pA0 = verts[edge_a_idx]
    pA1 = verts[(edge_a_idx + 1) % n]
    ang_a = math.degrees(math.atan2(pA1[1] - pA0[1], pA1[0] - pA0[0])) % 360
    
    pB0 = verts[edge_b_idx]
    pB1 = verts[(edge_b_idx + 1) % n]
    ang_b = math.degrees(math.atan2(pB1[1] - pB0[1], pB1[0] - pB0[0])) % 360
    
    diff = abs(ang_a - ang_b)
    diff = min(diff, 360 - diff)
    
    return diff > threshold_deg

def arch_perpendicular_angle(tangent_angle: float) -> float:
    """
    Offer the facing angle for the arch. Since the arch faces down the corridor
    to block it, the facing normal points parallel to the wall tangent direction.
    """
    return tangent_angle % 360

