# -*- coding: utf-8 -*-
"""Module de création des feuilles et placement des viewports.

Layout de la feuille :
┌─────────────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────┐    ┌──────────┐    │
│  │   PLAN   │  │ PLAFOND  │    │ Légende1 │    │
│  │          │  │          │    ├──────────┤    │
│  └──────────┘  └──────────┘    │ Légende2 │    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─┐  └──────────┘    │
│  │Elev │ │Elev │ │Elev │ │E│                   │
│  │ N   │ │ E   │ │ S   │ │W│                   │
│  └─────┘ └─────┘ └─────┘ └─┘                   │
│                                   [Cartouche]   │
└─────────────────────────────────────────────────┘
"""

from pyrevit import DB
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSheet, Viewport, BuiltInParameter,
    BuiltInCategory, XYZ, ElementId
)

from utils import get_unique_sheet_number, mm_to_feet


# ============================================================
# Helpers
# ============================================================

def _get_sheet_size(doc, sheet):
    """Dimensions du cartouche (largeur, hauteur) en pieds."""
    tbs = FilteredElementCollector(doc, sheet.Id) \
        .OfCategory(BuiltInCategory.OST_TitleBlocks) \
        .WhereElementIsNotElementType() \
        .ToElements()

    for tb in tbs:
        bb = tb.get_BoundingBox(sheet)
        if bb:
            w = bb.Max.X - bb.Min.X
            h = bb.Max.Y - bb.Min.Y
            if w > 0 and h > 0:
                return w, h

    return mm_to_feet(841), mm_to_feet(594)  # A1 par défaut


def _vp_outline_size(vp):
    """(largeur, hauteur) du viewport en pieds."""
    outline = vp.GetBoxOutline()
    if outline:
        return (outline.MaximumPoint.X - outline.MinimumPoint.X,
                outline.MaximumPoint.Y - outline.MinimumPoint.Y)
    return mm_to_feet(200), mm_to_feet(150)


# ============================================================
# Création de feuille
# ============================================================

def create_sheet(doc, titleblock, sheet_number, sheet_name):
    """Crée une ViewSheet avec cartouche et numérotation unique."""
    if not titleblock:
        return None

    if not titleblock.IsActive:
        titleblock.Activate()

    unique_num = get_unique_sheet_number(doc, sheet_number)
    sheet = ViewSheet.Create(doc, titleblock.Id)
    sheet.SheetNumber = unique_num
    sheet.Name = sheet_name
    return sheet


# ============================================================
# Moteur de placement
# ============================================================

class SheetLayoutEngine(object):
    """Place les vues et légendes sur une feuille.

    Organisation :
    - Zone gauche (75% largeur) : vues (plans en haut, élévations en bas)
    - Zone droite (25% largeur) : légendes empilées verticalement
    """

    def __init__(self, doc, sheet):
        self.doc = doc
        self.sheet = sheet
        self.sw, self.sh = _get_sheet_size(doc, sheet)

        # Marges en pieds
        self.ml = mm_to_feet(25)   # gauche
        self.mr = mm_to_feet(15)   # droite
        self.mt = mm_to_feet(15)   # haut
        self.mb = mm_to_feet(25)   # bas
        self.gap = mm_to_feet(8)   # entre viewports

        # Zone utile
        self.left = self.ml
        self.right = self.sw - self.mr
        self.top = self.sh - self.mt
        self.bottom = self.mb
        self.uw = self.right - self.left
        self.uh = self.top - self.bottom

    def place_all(self, views_result, legends=None):
        """Place toutes les vues + légendes.

        Args:
            views_result: dict avec floor_plan, ceiling_plan, elevations.
            legends: liste de vues legend.

        Returns:
            list[Viewport]
        """
        all_vps = []

        # Séparer zone vues / zone légendes
        has_legends = legends and len(legends) > 0
        if has_legends:
            views_right = self.right - self.uw * 0.25
            legend_left = views_right + self.gap
        else:
            views_right = self.right
            legend_left = self.right

        views_width = views_right - self.left

        # Collecter les vues
        plans = []
        if views_result.get("floor_plan"):
            plans.append(views_result["floor_plan"])
        if views_result.get("ceiling_plan"):
            plans.append(views_result["ceiling_plan"])
        elevs = views_result.get("elevations", [])

        has_plans = len(plans) > 0
        has_elevs = len(elevs) > 0

        # Répartition verticale
        if has_plans and has_elevs:
            plan_top = self.top
            plan_bot = self.bottom + self.uh * 0.45
            elev_top = plan_bot - self.gap
            elev_bot = self.bottom
        elif has_plans:
            plan_top = self.top
            plan_bot = self.bottom
            elev_top = elev_bot = 0
        elif has_elevs:
            plan_top = plan_bot = 0
            elev_top = self.top
            elev_bot = self.bottom
        else:
            return all_vps

        # ── Placer les plans (rangée haut) ──
        if has_plans:
            vps = self._place_row(plans, self.left, views_right,
                                   plan_top, plan_bot)
            all_vps.extend(vps)

        # ── Placer les élévations (rangée bas) ──
        if has_elevs:
            vps = self._place_row(elevs, self.left, views_right,
                                   elev_top, elev_bot)
            all_vps.extend(vps)

        # ── Placer les légendes à droite, empilées ──
        if has_legends:
            vps = self._place_legends_column(legends, legend_left,
                                              self.right, self.top)
            all_vps.extend(vps)

        return all_vps

    def _place_row(self, views, x_left, x_right, y_top, y_bot):
        """Place une rangée de vues centrées horizontalement.

        Méthode : placer temporairement → mesurer → repositionner → supprimer les temp.
        """
        n = len(views)
        if n == 0:
            return []

        zone_w = x_right - x_left
        cy = (y_top + y_bot) / 2.0

        # Placer temporairement chaque vue pour mesurer sa taille
        measurements = []
        temp_vps = []

        for i, view in enumerate(views):
            temp_x = x_left + mm_to_feet(50) + mm_to_feet(120) * i
            temp_pos = XYZ(temp_x, cy, 0)

            if not Viewport.CanAddViewToSheet(self.doc, self.sheet.Id, view.Id):
                measurements.append({"w": mm_to_feet(100), "h": mm_to_feet(80),
                                     "view": view, "vp": None})
                continue

            vp = Viewport.Create(self.doc, self.sheet.Id, view.Id, temp_pos)
            w, h = _vp_outline_size(vp)
            measurements.append({"w": w, "h": h, "view": view, "vp": vp})
            temp_vps.append(vp)

        # Calculer la disposition finale centrée
        total_w = sum(m["w"] for m in measurements) + self.gap * (n - 1)
        start_x = x_left + (zone_w - total_w) / 2.0
        if start_x < x_left:
            start_x = x_left

        positions = []
        cx = start_x
        for m in measurements:
            pos = XYZ(cx + m["w"] / 2.0, cy, 0)
            positions.append(pos)
            cx += m["w"] + self.gap

        # Supprimer les viewports temporaires
        for vp in temp_vps:
            self.doc.Delete(vp.Id)

        # Recréer les viewports aux bonnes positions
        result = []
        for m, pos in zip(measurements, positions):
            if not Viewport.CanAddViewToSheet(self.doc, self.sheet.Id, m["view"].Id):
                continue
            vp = Viewport.Create(self.doc, self.sheet.Id, m["view"].Id, pos)
            result.append(vp)

        return result

    def _place_legends_column(self, legends, x_left, x_right, y_top):
        """Place les légendes empilées verticalement dans la zone droite.

        Commence en haut et descend.
        """
        result = []
        cx = (x_left + x_right) / 2.0
        current_y = y_top

        for legend in legends:
            if not Viewport.CanAddViewToSheet(self.doc, self.sheet.Id, legend.Id):
                continue

            pos = XYZ(cx, current_y, 0)
            vp = Viewport.Create(self.doc, self.sheet.Id, legend.Id, pos)

            # Mesurer la taille réelle et repositionner
            w, h = _vp_outline_size(vp)

            # Repositionner : le centre doit être à current_y - h/2
            final_pos = XYZ(cx, current_y - h / 2.0, 0)
            vp.SetBoxCenter(final_pos)

            current_y -= h + self.gap
            result.append(vp)

        return result


# ============================================================
# Fonction haut niveau
# ============================================================

def create_sheet_for_room(doc, room_data, views_result, config, sheet_index):
    """Crée une feuille pour une room et y place toutes les vues + légendes.

    Args:
        doc: Document Revit.
        room_data: RoomData.
        views_result: dict de vues créées.
        config: Configuration du wizard.
        sheet_index: Index pour la numérotation.

    Returns:
        dict: {"sheet": ViewSheet, "viewports": [Viewport]}
    """
    result = {"sheet": None, "viewports": []}

    titleblock = config.get("titleblock")
    if not titleblock:
        return result

    # Numéro de feuille
    prefix = config.get("sheet_prefix", "RBR-")
    start_str = config.get("sheet_start", "001")
    try:
        start_num = int(start_str)
    except ValueError:
        start_num = 1

    padding = max(len(start_str), 3)
    sheet_number = "{}{}".format(prefix, str(start_num + sheet_index).zfill(padding))
    sheet_name = "{} - {}".format(room_data.number, room_data.name)

    # Créer la feuille
    sheet = create_sheet(doc, titleblock, sheet_number, sheet_name)
    if not sheet:
        return result
    result["sheet"] = sheet

    # Placer les vues + légendes
    layout = SheetLayoutEngine(doc, sheet)
    legends = config.get("legends", [])
    vps = layout.place_all(views_result, legends=legends if legends else None)
    result["viewports"] = vps

    return result
