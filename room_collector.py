# -*- coding: utf-8 -*-
"""Module de collecte des rooms du modèle Revit.

Fournit les fonctions pour récupérer les rooms, les grouper par niveau,
et gérer la sélection interactive sur le plan.
"""

from pyrevit import revit, DB, UI
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    ElementId, SpatialElementBoundaryOptions
)


class RoomData(object):
    """Objet léger représentant une room pour l'interface."""

    def __init__(self, room_element):
        self.element = room_element
        self.id = room_element.Id
        self.id_int = room_element.Id.IntegerValue

        # Paramètres via BuiltInParameter (compatible toutes langues)
        name_param = room_element.get_Parameter(BuiltInParameter.ROOM_NAME)
        number_param = room_element.get_Parameter(BuiltInParameter.ROOM_NUMBER)
        area_param = room_element.get_Parameter(BuiltInParameter.ROOM_AREA)
        level_param = room_element.get_Parameter(BuiltInParameter.ROOM_LEVEL_ID)

        self.name = name_param.AsString() if name_param and name_param.HasValue else "Sans nom"
        self.number = number_param.AsString() if number_param and number_param.HasValue else "?"
        self.area = area_param.AsDouble() if area_param and area_param.HasValue else 0.0
        self.level_id = level_param.AsElementId() if level_param and level_param.HasValue else ElementId.InvalidElementId

        # Nom du niveau
        doc = room_element.Document
        level_elem = doc.GetElement(self.level_id) if self.level_id != ElementId.InvalidElementId else None
        self.level_name = level_elem.Name if level_elem else "Aucun niveau"

        # Vérifier que la room est placée et délimitée (area > 0)
        self.is_valid = self.area > 0

    @property
    def display_name(self):
        """Nom d'affichage pour l'interface : 'Numéro - Nom'."""
        return "{} - {}".format(self.number, self.name)

    def __repr__(self):
        return "<RoomData {} - {} (Level: {})>".format(
            self.number, self.name, self.level_name
        )


def get_all_rooms(doc):
    """Récupère toutes les rooms placées et délimitées du modèle.

    Args:
        doc: Document Revit actif.

    Returns:
        list[RoomData]: Liste des rooms valides.
    """
    collector = FilteredElementCollector(doc) \
        .OfCategory(BuiltInCategory.OST_Rooms) \
        .WhereElementIsNotElementType()

    rooms = []
    for room in collector:
        rd = RoomData(room)
        if rd.is_valid:
            rooms.append(rd)

    # Tri par niveau puis par numéro
    rooms.sort(key=lambda r: (r.level_name, r.number))
    return rooms


def get_rooms_grouped_by_level(doc):
    """Récupère les rooms groupées par niveau.

    Args:
        doc: Document Revit actif.

    Returns:
        dict: {level_name: [RoomData, ...]}
              Ordonné par élévation du niveau.
    """
    all_rooms = get_all_rooms(doc)

    # Grouper par niveau
    level_groups = {}
    level_elevations = {}

    for rd in all_rooms:
        if rd.level_name not in level_groups:
            level_groups[rd.level_name] = []
            # Stocker l'élévation pour le tri
            level_elem = doc.GetElement(rd.level_id)
            if level_elem:
                elev_param = level_elem.get_Parameter(BuiltInParameter.LEVEL_ELEV)
                level_elevations[rd.level_name] = elev_param.AsDouble() if elev_param else 0.0
            else:
                level_elevations[rd.level_name] = 0.0
        level_groups[rd.level_name].append(rd)

    # Trier les niveaux par élévation
    sorted_levels = sorted(level_groups.keys(), key=lambda n: level_elevations.get(n, 0.0))

    result = {}
    for level_name in sorted_levels:
        result[level_name] = level_groups[level_name]

    return result


def pick_rooms_from_plan(uidoc):
    """Permet à l'utilisateur de sélectionner des rooms sur le plan.

    Args:
        uidoc: UIDocument Revit actif.

    Returns:
        list[RoomData]: Liste des rooms sélectionnées, ou liste vide si annulé.
    """
    doc = uidoc.Document

    try:
        # Filtre pour ne sélectionner que des rooms
        room_filter = RoomSelectionFilter()
        references = uidoc.Selection.PickObjects(
            UI.Selection.ObjectType.Element,
            room_filter,
            "Sélectionnez les rooms puis appuyez sur Terminer"
        )

        rooms = []
        for ref in references:
            elem = doc.GetElement(ref.ElementId)
            if elem:
                rd = RoomData(elem)
                if rd.is_valid:
                    rooms.append(rd)

        return rooms

    except Exception:
        # L'utilisateur a appuyé sur Échap
        return []


class RoomSelectionFilter(UI.Selection.ISelectionFilter):
    """Filtre de sélection pour n'autoriser que les rooms."""

    def AllowElement(self, element):
        if element.Category and \
           element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Rooms):
            return True
        return False

    def AllowReference(self, reference, position):
        return False


def get_room_bounding_box(room):
    """Récupère la BoundingBox d'une room.

    Args:
        room: Element Room Revit.

    Returns:
        BoundingBoxXYZ ou None si impossible.
    """
    bb = room.get_BoundingBox(None)
    if bb:
        return bb
    return None


def get_room_center(room):
    """Calcule le point central d'une room.

    Args:
        room: Element Room Revit.

    Returns:
        XYZ: Point central de la room, ou None.
    """
    bb = get_room_bounding_box(room)
    if bb:
        center = DB.XYZ(
            (bb.Min.X + bb.Max.X) / 2.0,
            (bb.Min.Y + bb.Max.Y) / 2.0,
            (bb.Min.Z + bb.Max.Z) / 2.0
        )
        return center

    # Fallback : utiliser le Location de la room
    loc = room.Location
    if loc and hasattr(loc, 'Point'):
        return loc.Point

    return None
