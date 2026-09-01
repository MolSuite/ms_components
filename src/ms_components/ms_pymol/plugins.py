"""
pymol_plugins.py
----------------
PyMOL extensions for visualising docking boxes and bounding boxes.

Commands are registered straight onto `cmd` with the `pymol_command` decorator,
which makes them reachable from Python code and from the PyMOL console alike.
"""

from __future__ import annotations

from pymol import cmd
from pymol.cgo import (
    ALPHA, BEGIN, END, TRIANGLE_STRIP, LINES, LINEWIDTH,
    COLOR, VERTEX, CYLINDER,
)


# ---------------------------------------------------------------------------
# Registration decorator
# ---------------------------------------------------------------------------

def pymol_command(func):
    """
    Register a function as a PyMOL command.
    If a command with that name already exists, keep its original docstring.
    """
    name = func.__name__
    if existing_doc := getattr(getattr(cmd, name, None), "__doc__", None):
        func.__doc__ = existing_doc
    setattr(cmd, name, func)
    cmd.extend(name, func)
    return func


# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------

Color3f = tuple[float, float, float]
Point3f = tuple[float, float, float]


# ---------------------------------------------------------------------------
# Registered commands
# ---------------------------------------------------------------------------

@pymol_command
def draw_box(
        points: tuple[Point3f, Point3f] = ((0.0, 0.0, 0.0), (5.0, 5.0, 5.0)),
        show_face: bool = True,
        face_color_x: Color3f = (1.0, 0.0, 0.0),
        face_color_y: Color3f = (0.0, 1.0, 0.0),
        face_color_z: Color3f = (0.0, 0.0, 1.0),
        show_edge: bool = True,
        edge_style: str = "line",  # "line" | "cylinder"
        edge_color: Color3f = (1.0, 1.0, 1.0),
        edge_width: float = 2.0,
        face_opacity: float = 0.5,
        obj_name: str = "gridbox",
) -> None:
    """
    Draw a 3D box in PyMOL with semi-transparent faces and edges.

    Parameters
    ----------
    points       : ((xmin,ymin,zmin), (xmax,ymax,zmax))
    show_face    : draw semi-transparent faces
    face_color_* : normalised RGB colours [0,1] per axis
    show_edge    : draw edges
    edge_style   : "line" for fast lines, "cylinder" for 3D tubes
    edge_color   : RGB colour of the edges
    edge_width   : edge thickness (lines) or radius (cylinders ×0.1)
    face_opacity : face transparency [0.0 – 1.0]
    obj_name     : name of the CGO object in PyMOL
    """
    (xmin, ymin, zmin), (xmax, ymax, zmax) = (
        (float(v) for v in points[0]),
        (float(v) for v in points[1]),
    )
    opacity = float(face_opacity)
    width = float(edge_width)

    # Save the view so loading the CGO does not change it
    saved_view = cmd.get_view()
    cmd.delete(obj_name)

    cgo: list = []

    # -- Semi-transparent faces --
    if show_face:
        faces = [
            (face_color_x, [(xmin, ymin, zmin), (xmin, ymin, zmax), (xmin, ymax, zmin), (xmin, ymax, zmax)]),
            (face_color_x, [(xmax, ymin, zmin), (xmax, ymin, zmax), (xmax, ymax, zmin), (xmax, ymax, zmax)]),
            (face_color_y, [(xmin, ymin, zmin), (xmin, ymin, zmax), (xmax, ymin, zmin), (xmax, ymin, zmax)]),
            (face_color_y, [(xmin, ymax, zmin), (xmin, ymax, zmax), (xmax, ymax, zmin), (xmax, ymax, zmax)]),
            (face_color_z, [(xmin, ymin, zmin), (xmin, ymax, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin)]),
            (face_color_z, [(xmin, ymin, zmax), (xmin, ymax, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax)]),
        ]
        for color, verts in faces:
            cgo += [ALPHA, opacity, BEGIN, TRIANGLE_STRIP, COLOR, *color]
            for v in verts:
                cgo += [VERTEX, *v]
            cgo += [END]

    # -- Edges --
    if show_edge:
        corners = {
            1: (xmin, ymin, zmin), 2: (xmin, ymin, zmax),
            3: (xmin, ymax, zmin), 4: (xmin, ymax, zmax),
            5: (xmax, ymin, zmin), 6: (xmax, ymin, zmax),
            7: (xmax, ymax, zmin), 8: (xmax, ymax, zmax),
        }
        edges = [
            (1, 2), (3, 4), (5, 6), (7, 8),  # edges along Z
            (1, 5), (3, 7), (4, 8), (2, 6),  # edges along X
            (1, 3), (5, 7), (2, 4), (6, 8),  # edges along Y
        ]

        if edge_style == "line":
            cgo += [ALPHA, 1.0, LINEWIDTH, width, BEGIN, LINES, COLOR, *edge_color]
            for a, b in edges:
                cgo += [VERTEX, *corners[a], VERTEX, *corners[b]]
            cgo += [END]

        elif edge_style == "cylinder":
            r = width / 10.0
            c = edge_color
            for a, b in edges:
                cgo += [CYLINDER, *corners[a], *corners[b], r, *c, *c]

    cmd.load_cgo(cgo, obj_name)
    cmd.set("cgo_line_width", width)
    cmd.set_view(saved_view)


@pymol_command
def draw_bounding_box(selection: str = "all", obj_name: str = "gridbox") -> None:
    """Draw the box that exactly wraps the given selection."""
    extent = cmd.get_extent(selection)
    draw_box(points=extent, obj_name=obj_name)


@pymol_command
def get_box_extent(selection: str = "gridbox") -> tuple[Point3f, Point3f] | None:
    """
    Return ((xmin,ymin,zmin),(xmax,ymax,zmax)) of the given object.
    Unlike the original, it returns the value so it can be used from code.
    """
    return cmd.get_extent(selection)


@pymol_command
def reset_scene() -> None:
    """Reinitialise PyMOL, preserving the internal panel state."""
    internal_gui = cmd.get("internal_gui")
    cmd.reinitialize()
    cmd.set("internal_gui", internal_gui)
