# -*- coding: utf-8 -*-
"""Module de placement des légendes sur les feuilles.

Les légendes (ViewType.Legend) sont des vues spéciales qui peuvent
être placées sur plusieurs feuilles simultanément via Viewport.Create.
"""

from pyrevit import DB
from Autodesk.Revit.DB import (
    Viewport, XYZ, FilteredElementCollector,
    BuiltInCategory
)

from utils import mm_to_feet


def place_legend_on_sheet(doc, sheet, legend_view, position=None):
    """Place une légende sur une feuille.

    Les légendes peuvent être placées sur plusieurs feuilles (contrairement
    aux vues classiques qui ne peuvent être que sur une seule feuille).

    Args:
        doc: Document Revit.
        sheet: ViewSheet cible.
        legend_view: Vue de type Legend.
        position: XYZ du centre du viewport. Si None, position par défaut.

    Returns:
        Viewport créé, ou None si erreur.
    """
    if not sheet or not legend_view:
        return None

    # Position par défaut : bas-droite de la feuille
    if position is None:
        position = _get_default_legend_position(doc, sheet)

    # Les légendes utilisent aussi Viewport.Create
    try:
        if Viewport.CanAddViewToSheet(doc, sheet.Id, legend_view.Id):
            vp = Viewport.Create(doc, sheet.Id, legend_view.Id, position)
            return vp
    except Exception:
        pass

    return None


def place_legends_on_sheet(doc, sheet, legend_views, start_position=None,
                           direction="vertical", spacing_mm=10):
    """Place plusieurs légendes sur une feuille, empilées.

    Args:
        doc: Document Revit.
        sheet: ViewSheet.
        legend_views (list): Vues légendes à placer.
        start_position: XYZ de la première légende. None = auto.
        direction (str): "vertical" ou "horizontal".
        spacing_mm (float): Espace entre les légendes en mm.

    Returns:
        list[Viewport]: Viewports créés.
    """
    if not legend_views:
        return []

    if start_position is None:
        start_position = _get_default_legend_position(doc, sheet)

    spacing = mm_to_feet(spacing_mm)
    viewports = []
    current_pos = start_position

    for legend_view in legend_views:
        vp = place_legend_on_sheet(doc, sheet, legend_view, current_pos)
        if vp:
            viewports.append(vp)

            # Calculer le décalage pour la prochaine légende
            outline = vp.GetBoxOutline()
            if outline:
                vp_height = outline.MaximumPoint.Y - outline.MinimumPoint.Y
                vp_width = outline.MaximumPoint.X - outline.MinimumPoint.X
            else:
                vp_height = mm_to_feet(40)
                vp_width = mm_to_feet(80)

            if direction == "vertical":
                current_pos = XYZ(
                    current_pos.X,
                    current_pos.Y + vp_height + spacing,
                    0
                )
            else:
                current_pos = XYZ(
                    current_pos.X + vp_width + spacing,
                    current_pos.Y,
                    0
                )

    return viewports


def _get_default_legend_position(doc, sheet):
    """Calcule une position par défaut pour les légendes (bas-droite).

    Args:
        doc: Document Revit.
        sheet: ViewSheet.

    Returns:
        XYZ: Position de placement.
    """
    # Chercher le cartouche pour les dimensions
    tbs = FilteredElementCollector(doc, sheet.Id) \
        .OfCategory(BuiltInCategory.OST_TitleBlocks) \
        .WhereElementIsNotElementType() \
        .ToElements()

    sheet_width = mm_to_feet(841)  # A1 par défaut
    sheet_height = mm_to_feet(594)

    for tb in tbs:
        bb = tb.get_BoundingBox(sheet)
        if bb:
            w = bb.Max.X - bb.Min.X
            h = bb.Max.Y - bb.Min.Y
            if w > 0 and h > 0:
                sheet_width = w
                sheet_height = h
                break

    # Position bas-droite avec marges
    x = sheet_width - mm_to_feet(80)
    y = mm_to_feet(40)

    return XYZ(x, y, 0)
