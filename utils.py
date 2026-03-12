# -*- coding: utf-8 -*-
"""Fonctions utilitaires pour le plugin Room by Room.

Conversions d'unités, helpers pour noms uniques, collecte de gabarits, etc.
"""

from pyrevit import DB
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    ViewFamilyType, ViewFamily, ViewType, ElementId
)


# ============================================================
# Conversion d'unités
# ============================================================

def mm_to_feet(mm):
    """Convertit des millimètres en pieds (unité interne Revit).

    Args:
        mm (float): Valeur en millimètres.

    Returns:
        float: Valeur en pieds.
    """
    return mm / 304.8


def feet_to_mm(feet):
    """Convertit des pieds (unité interne) en millimètres.

    Args:
        feet (float): Valeur en pieds.

    Returns:
        float: Valeur en millimètres.
    """
    return feet * 304.8


def m_to_feet(m):
    """Convertit des mètres en pieds."""
    return m / 0.3048


def feet_to_m(feet):
    """Convertit des pieds en mètres."""
    return feet * 0.3048


# ============================================================
# Collecte des gabarits de vue
# ============================================================

def get_view_templates(doc):
    """Récupère tous les gabarits de vue du document.

    Args:
        doc: Document Revit.

    Returns:
        list[View]: Liste des gabarits de vue triés par nom.
    """
    views = FilteredElementCollector(doc) \
        .OfClass(DB.View) \
        .ToElements()

    templates = []
    for v in views:
        if v.IsTemplate:
            templates.append(v)

    templates.sort(key=lambda v: v.Name)
    return templates


def get_view_templates_by_type(doc, view_family=None):
    """Récupère les gabarits filtrés par type de vue.

    Args:
        doc: Document Revit.
        view_family (ViewFamily, optional): Type de famille de vue pour filtrer.

    Returns:
        list[View]: Gabarits de vue correspondants.
    """
    all_templates = get_view_templates(doc)
    if view_family is None:
        return all_templates

    # Filtrer par ViewType correspondant
    type_map = {
        ViewFamily.FloorPlan: [ViewType.FloorPlan],
        ViewFamily.CeilingPlan: [ViewType.CeilingPlan],
        ViewFamily.Section: [ViewType.Section],
        ViewFamily.Elevation: [ViewType.Elevation],
    }

    allowed_types = type_map.get(view_family, [])
    if not allowed_types:
        return all_templates

    filtered = [t for t in all_templates if t.ViewType in allowed_types]
    return filtered if filtered else all_templates


# ============================================================
# Collecte des ViewFamilyType
# ============================================================

def get_view_family_types(doc):
    """Récupère tous les ViewFamilyType du document.

    Returns:
        dict: {ViewFamily: [ViewFamilyType, ...]}
    """
    types = FilteredElementCollector(doc) \
        .OfClass(ViewFamilyType) \
        .ToElements()

    result = {}
    for vft in types:
        vf = vft.ViewFamily
        if vf not in result:
            result[vf] = []
        result[vf].append(vft)

    return result


def get_first_view_family_type(doc, view_family):
    """Récupère le premier ViewFamilyType pour une famille de vues donnée.

    Args:
        doc: Document Revit.
        view_family: ViewFamily enum (FloorPlan, CeilingPlan, Section, etc.)

    Returns:
        ViewFamilyType ou None.
    """
    types = get_view_family_types(doc)
    family_types = types.get(view_family, [])
    return family_types[0] if family_types else None


# ============================================================
# Collecte des cartouches (TitleBlocks)
# ============================================================

def get_title_blocks(doc):
    """Récupère tous les types de cartouche disponibles.

    Returns:
        list[FamilySymbol]: Types de cartouche triés par nom.
    """
    tbs = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_TitleBlocks) \
        .WhereElementIsElementType() \
        .ToElements()

    result = list(tbs)
    result.sort(key=lambda t: "{}: {}".format(
        t.FamilyName if hasattr(t, 'FamilyName') else "",
        t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() if t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM) else t.Name
    ))
    return result


def get_title_block_display_name(tb):
    """Nom d'affichage d'un cartouche : 'Famille : Type'."""
    family_name = tb.FamilyName if hasattr(tb, 'FamilyName') else "?"
    type_param = tb.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    type_name = type_param.AsString() if type_param else tb.Name
    return "{}: {}".format(family_name, type_name)


# ============================================================
# Collecte des légendes
# ============================================================

def get_legends(doc):
    """Récupère toutes les vues de type légende.

    Returns:
        list[View]: Légendes triées par nom.
    """
    views = FilteredElementCollector(doc) \
        .OfClass(DB.View) \
        .ToElements()

    legends = [v for v in views if v.ViewType == ViewType.Legend and not v.IsTemplate]
    legends.sort(key=lambda v: v.Name)
    return legends


# ============================================================
# Noms uniques
# ============================================================

def get_unique_view_name(doc, desired_name):
    """Génère un nom de vue unique dans le document.

    Si le nom existe déjà, ajoute un suffixe incrémental.

    Args:
        doc: Document Revit.
        desired_name (str): Nom souhaité.

    Returns:
        str: Nom unique.
    """
    existing_names = set()
    views = FilteredElementCollector(doc) \
        .OfClass(DB.View) \
        .ToElements()

    for v in views:
        try:
            existing_names.add(v.Name)
        except Exception:
            pass

    if desired_name not in existing_names:
        return desired_name

    counter = 1
    while True:
        candidate = "{} ({})".format(desired_name, counter)
        if candidate not in existing_names:
            return candidate
        counter += 1


def get_unique_sheet_number(doc, desired_number):
    """Génère un numéro de feuille unique.

    Args:
        doc: Document Revit.
        desired_number (str): Numéro souhaité.

    Returns:
        str: Numéro unique.
    """
    existing_numbers = set()
    sheets = FilteredElementCollector(doc) \
        .OfClass(DB.ViewSheet) \
        .ToElements()

    for s in sheets:
        num_param = s.get_Parameter(BuiltInParameter.SHEET_NUMBER)
        if num_param and num_param.HasValue:
            existing_numbers.add(num_param.AsString())

    if desired_number not in existing_numbers:
        return desired_number

    counter = 1
    while True:
        candidate = "{}-{}".format(desired_number, counter)
        if candidate not in existing_numbers:
            return candidate
        counter += 1
