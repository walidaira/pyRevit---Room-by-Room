# -*- coding: utf-8 -*-
"""Module de création des vues pour chaque room.

Utilise GetBoundarySegments pour le contour précis des rooms.
Corrige l'API ElevationMarker.CreateElevation (2e param = vue en plan).
"""

from pyrevit import DB
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewPlan, ViewFamilyType, ViewFamily,
    BoundingBoxXYZ, XYZ, ElementId, BuiltInParameter,
    ElevationMarker, SpatialElementBoundaryOptions,
    SpatialElementBoundaryLocation, ViewType
)

from utils import mm_to_feet, get_unique_view_name


# ============================================================
# Helpers — Infos room
# ============================================================

def _get_vft_id(doc, view_family):
    """Premier ViewFamilyType pour une famille de vues."""
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if vft.ViewFamily == view_family:
            return vft.Id
    return None


def _find_template(doc, name):
    """Trouve un gabarit de vue par nom."""
    if not name:
        return None
    for v in FilteredElementCollector(doc).OfClass(DB.View):
        if v.IsTemplate and v.Name == name:
            return v
    return None


def _room_info(room):
    """(number, name) via BuiltInParameter."""
    np = room.get_Parameter(BuiltInParameter.ROOM_NUMBER)
    nm = room.get_Parameter(BuiltInParameter.ROOM_NAME)
    return (
        np.AsString() if np and np.HasValue else "?",
        nm.AsString() if nm and nm.HasValue else "Sans nom"
    )


def _room_level(doc, room):
    """Level de la room."""
    lp = room.get_Parameter(BuiltInParameter.ROOM_LEVEL_ID)
    if lp and lp.HasValue:
        lid = lp.AsElementId()
        if lid != ElementId.InvalidElementId:
            return doc.GetElement(lid)
    return None


# ============================================================
# Helpers — Géométrie précise de la room
# ============================================================

def _room_bounds(room):
    """Bornes précises XY depuis GetBoundarySegments + Z depuis BoundingBox.

    Returns:
        dict avec min_x, max_x, min_y, max_y, min_z, max_z ou None.
    """
    # Essayer GetBoundarySegments pour les bornes XY précises
    opts = SpatialElementBoundaryOptions()
    opts.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    segs = room.GetBoundarySegments(opts)

    pts = []
    if segs:
        for seg_loop in segs:
            for seg in seg_loop:
                crv = seg.GetCurve()
                pts.append(crv.GetEndPoint(0))
                pts.append(crv.GetEndPoint(1))

    bb = room.get_BoundingBox(None)

    if pts:
        min_x = min(p.X for p in pts)
        max_x = max(p.X for p in pts)
        min_y = min(p.Y for p in pts)
        max_y = max(p.Y for p in pts)
    elif bb:
        min_x, max_x = bb.Min.X, bb.Max.X
        min_y, max_y = bb.Min.Y, bb.Max.Y
    else:
        return None

    if bb:
        min_z, max_z = bb.Min.Z, bb.Max.Z
    else:
        doc = room.Document
        lev = _room_level(doc, room)
        min_z = lev.Elevation if lev else 0.0
        max_z = min_z + mm_to_feet(2700)

    return dict(min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
                min_z=min_z, max_z=max_z)


def _bounds_center(b):
    """Centre XYZ des bornes."""
    return XYZ(
        (b["min_x"] + b["max_x"]) / 2.0,
        (b["min_y"] + b["max_y"]) / 2.0,
        (b["min_z"] + b["max_z"]) / 2.0
    )


def _make_crop(b, offset):
    """CropBox BoundingBoxXYZ depuis bornes + offset en pieds."""
    c = BoundingBoxXYZ()
    c.Min = XYZ(b["min_x"] - offset, b["min_y"] - offset, b["min_z"])
    c.Max = XYZ(b["max_x"] + offset, b["max_y"] + offset, b["max_z"])
    return c


# ============================================================
# Trouver une vue en plan existante sur un niveau
# ============================================================

def _get_plan_view_id_for_level(doc, level):
    """Trouve une vue en plan FloorPlan existante sur ce niveau.

    L'ElevationMarker.CreateElevation() exige en 2e paramètre
    l'ElementId d'une ViewPlan associée au même Level.

    Returns:
        ElementId ou None.
    """
    # Chercher parmi toutes les vues en plan
    for v in FilteredElementCollector(doc).OfClass(ViewPlan):
        if v.IsTemplate:
            continue
        try:
            gen_level = v.GenLevel
            if gen_level and gen_level.Id == level.Id:
                if v.ViewType == ViewType.FloorPlan:
                    return v.Id
        except Exception:
            continue

    # Aucune trouvée — en créer une temporaire
    vft_id = _get_vft_id(doc, ViewFamily.FloorPlan)
    if vft_id:
        temp = ViewPlan.Create(doc, vft_id, level.Id)
        temp.Name = get_unique_view_name(doc, "_RBR_TMP_{}".format(level.Name))
        return temp.Id
    return None


# ============================================================
# Création de vue en plan (Floor Plan)
# ============================================================

def create_floor_plan(doc, room, template_name=None, offset_mm=300, scale=100):
    """Crée une vue en plan délimitée par le contour réel de la room.

    Args:
        doc: Document Revit.
        room: Element Room.
        template_name: Nom du gabarit de vue.
        offset_mm: Marge en mm autour du contour.
        scale: Échelle de la vue (ex: 50 pour 1:50).

    Returns:
        ViewPlan ou None.
    """
    number, name = _room_info(room)
    level = _room_level(doc, room)
    if not level:
        return None

    vft_id = _get_vft_id(doc, ViewFamily.FloorPlan)
    if not vft_id:
        return None

    bounds = _room_bounds(room)
    if not bounds:
        return None

    offset = mm_to_feet(offset_mm)
    view_name = get_unique_view_name(doc, "Plan - {} - {}".format(number, name))

    view = ViewPlan.Create(doc, vft_id, level.Id)
    view.Name = view_name
    view.Scale = scale

    crop = _make_crop(bounds, offset)
    view.CropBoxActive = True
    view.CropBoxVisible = True
    view.CropBox = crop

    if template_name:
        tmpl = _find_template(doc, template_name)
        if tmpl:
            view.ViewTemplateId = tmpl.Id

    return view


# ============================================================
# Création de plan de plafond (Ceiling Plan)
# ============================================================

def create_ceiling_plan(doc, room, template_name=None, offset_mm=300, scale=100):
    """Crée un plan de plafond délimité par le contour réel de la room."""
    number, name = _room_info(room)
    level = _room_level(doc, room)
    if not level:
        return None

    vft_id = _get_vft_id(doc, ViewFamily.CeilingPlan)
    if not vft_id:
        return None

    bounds = _room_bounds(room)
    if not bounds:
        return None

    offset = mm_to_feet(offset_mm)
    view_name = get_unique_view_name(doc, "Plafond - {} - {}".format(number, name))

    view = ViewPlan.Create(doc, vft_id, level.Id)
    view.Name = view_name
    view.Scale = scale

    crop = _make_crop(bounds, offset)
    view.CropBoxActive = True
    view.CropBoxVisible = True
    view.CropBox = crop

    if template_name:
        tmpl = _find_template(doc, template_name)
        if tmpl:
            view.ViewTemplateId = tmpl.Id

    return view


# ============================================================
# Création des élévations intérieures (ElevationMarker)
# ============================================================

def create_interior_elevations(doc, room, template_name=None, offset_mm=300,
                                directions=None, scale=50):
    """Crée un ElevationMarker au centre de la room + les 4 élévations.

    API correcte :
        marker = ElevationMarker.CreateElevationMarker(doc, vftId, center, scale)
        view   = marker.CreateElevation(doc, planViewId, markerIndex)

    Le 2e paramètre de CreateElevation est l'Id d'une VUE EN PLAN (pas du marker).

    Indices du marker dans Revit (orientation standard, Nord = +Y) :
        0 = regard vers +Y  → voit le mur côté +Y (Nord)
        1 = regard vers +X  → voit le mur côté +X (Est)
        2 = regard vers -Y  → voit le mur côté -Y (Sud)
        3 = regard vers -X  → voit le mur côté -X (Ouest)

    Args:
        doc: Document Revit.
        room: Element Room.
        template_name: Nom du gabarit de vue.
        offset_mm: Marge en mm.
        directions: {"north": bool, "south": bool, "east": bool, "west": bool}
        scale: Échelle (ex: 50).

    Returns:
        list[View] : Vues d'élévation créées.
    """
    if directions is None:
        directions = {"north": True, "south": True, "east": True, "west": True}

    number, name = _room_info(room)
    level = _room_level(doc, room)
    if not level:
        return []

    bounds = _room_bounds(room)
    if not bounds:
        return []

    center = _bounds_center(bounds)

    vft_id = _get_vft_id(doc, ViewFamily.Elevation)
    if not vft_id:
        return []

    # Trouver une vue en plan pour ce niveau (OBLIGATOIRE pour CreateElevation)
    plan_view_id = _get_plan_view_id_for_level(doc, level)
    if not plan_view_id:
        return []

    offset = mm_to_feet(offset_mm)

    # Dimensions de la room
    w = bounds["max_x"] - bounds["min_x"]   # largeur X
    d = bounds["max_y"] - bounds["min_y"]   # profondeur Y
    h = bounds["max_z"] - bounds["min_z"]   # hauteur Z

    # Créer le marker au centre, à l'élévation du niveau
    marker_pt = XYZ(center.X, center.Y, level.Elevation)
    marker = ElevationMarker.CreateElevationMarker(doc, vft_id, marker_pt, scale)
    if not marker:
        return []

    # Configuration par direction
    # half_w = demi-largeur de la vue (en X local de la vue)
    # far    = profondeur du far clip (distance centre → mur regardé)
    dir_config = {
        "north": {"idx": 0, "pfx": "Elev N",  "half_w": w / 2.0, "far": bounds["max_y"] - center.Y},
        "east":  {"idx": 1, "pfx": "Elev E",  "half_w": d / 2.0, "far": bounds["max_x"] - center.X},
        "south": {"idx": 2, "pfx": "Elev S",  "half_w": w / 2.0, "far": center.Y - bounds["min_y"]},
        "west":  {"idx": 3, "pfx": "Elev W",  "half_w": d / 2.0, "far": center.X - bounds["min_x"]},
    }

    tmpl = _find_template(doc, template_name) if template_name else None
    created = []

    for dk, cfg in dir_config.items():
        if not directions.get(dk, False):
            continue

        idx = cfg["idx"]
        half_w = cfg["half_w"] + offset
        far = cfg["far"] + offset

        try:
            # ── Créer l'élévation ──
            ev = marker.CreateElevation(doc, plan_view_id, idx)
            if not ev:
                continue

            # Nom
            ev.Name = get_unique_view_name(
                doc, "{} - {} - {}".format(cfg["pfx"], number, name)
            )

            # Échelle
            ev.Scale = scale

            # ── CropBox ──
            ev.CropBoxActive = True
            ev.CropBoxVisible = True

            try:
                cb = ev.CropBox
                # Repère local de l'élévation :
                #   X local = gauche/droite (largeur)
                #   Y local = bas/haut (hauteur)
                #   Z local = near/far (profondeur)
                new_cb = BoundingBoxXYZ()
                new_cb.Min = XYZ(-half_w, cb.Min.Y, cb.Min.Z)
                new_cb.Max = XYZ(half_w, h + offset, cb.Max.Z)
                ev.CropBox = new_cb
            except Exception:
                pass

            # ── Far Clip ──
            try:
                p_clip = ev.get_Parameter(BuiltInParameter.VIEWER_BOUND_FAR_CLIPPING)
                if p_clip and not p_clip.IsReadOnly:
                    p_clip.Set(1)  # Clip with line

                p_far = ev.get_Parameter(BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
                if p_far and not p_far.IsReadOnly:
                    p_far.Set(far)
            except Exception:
                pass

            # ── Gabarit ──
            if tmpl:
                ev.ViewTemplateId = tmpl.Id

            created.append(ev)

        except Exception:
            continue

    return created


# ============================================================
# Orchestrateur
# ============================================================

def create_all_views_for_room(doc, room, config):
    """Crée toutes les vues demandées pour une room.

    Returns:
        dict: {"floor_plan": View|None, "ceiling_plan": View|None, "elevations": [View]}
    """
    result = {"floor_plan": None, "ceiling_plan": None, "elevations": []}

    if config.get("create_floor_plan"):
        result["floor_plan"] = create_floor_plan(
            doc, room,
            template_name=config.get("floor_template_name"),
            offset_mm=config.get("floor_offset_mm", 300),
            scale=config.get("floor_scale", 100),
        )

    if config.get("create_ceiling_plan"):
        result["ceiling_plan"] = create_ceiling_plan(
            doc, room,
            template_name=config.get("ceiling_template_name"),
            offset_mm=config.get("ceiling_offset_mm", 300),
            scale=config.get("ceiling_scale", 100),
        )

    if config.get("create_elevations"):
        result["elevations"] = create_interior_elevations(
            doc, room,
            template_name=config.get("elev_template_name"),
            offset_mm=config.get("elev_offset_mm", 300),
            directions=config.get("elev_directions",
                                  {"north": True, "south": True,
                                   "east": True, "west": True}),
            scale=config.get("elev_scale", 50),
        )

    return result
