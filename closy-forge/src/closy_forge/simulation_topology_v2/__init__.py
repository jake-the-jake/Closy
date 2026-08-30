"""Opt-in physical topology-v2 experiment surfaces.

The admitted D runtime remains pinned to simulation topology v1. Importing this package does not
change canonical package generation or runtime capability selection.
"""

from .triangulator import (
    INTERIOR_CONSTRAINED_TRIANGULATOR_VERSION,
    SIMULATION_TOPOLOGY_VERSION,
    TopologyV2Result,
    build_panel_meshes_v2,
    triangulate_panel_v2,
)

__all__ = [
    "INTERIOR_CONSTRAINED_TRIANGULATOR_VERSION",
    "SIMULATION_TOPOLOGY_VERSION",
    "TopologyV2Result",
    "build_panel_meshes_v2",
    "triangulate_panel_v2",
]
