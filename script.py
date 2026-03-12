# -*- coding: utf-8 -*-
"""Room by Room — Créateur automatique de plans pièce par pièce.

Cet outil permet de créer automatiquement des vues en plan,
élévations intérieures, plans de plafond, et des feuilles
pour chaque pièce sélectionnée du projet.
"""

__title__ = "Room by\nRoom"
__author__ = "BIM Automation"
__doc__ = "Créer automatiquement les plans room by room avec vues, feuilles et légendes."

import os
import sys

# Ajouter le dossier lib au path
SCRIPT_DIR = os.path.dirname(__file__)
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")

from System.Windows import Window, Visibility, Thickness, RoutedEventArgs, VerticalAlignment, FontWeights
from System.Windows.Controls import (
    TreeViewItem, CheckBox, StackPanel, TextBlock, Orientation,
    ListBoxItem
)
from System.Windows.Media import SolidColorBrush
from System.Windows.Media import Color as WColor

from pyrevit import revit, DB, UI, forms, script

# Modules locaux
from room_collector import (
    get_all_rooms, get_rooms_grouped_by_level, pick_rooms_from_plan,
    RoomData
)
from utils import (
    get_view_templates, get_view_templates_by_type,
    get_title_blocks, get_title_block_display_name,
    get_legends, get_view_family_types
)
from view_creator import create_all_views_for_room
from sheet_creator import create_sheet_for_room
from legend_placer import place_legends_on_sheet

from Autodesk.Revit.DB import TransactionGroup, Transaction

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()


# ============================================================
# Classe principale du formulaire WPF
# ============================================================

class RoomByRoomWindow(forms.WPFWindow):
    """Fenêtre principale du wizard Room by Room."""

    def __init__(self):
        # Charger le XAML
        xaml_path = os.path.join(SCRIPT_DIR, "RoomByRoomUI.xaml")
        forms.WPFWindow.__init__(self, xaml_path)

        # État interne
        self.current_step = 1
        self.total_steps = 4
        self.selected_rooms = []          # list[RoomData]
        self.rooms_by_level = {}          # {level_name: [RoomData, ...]}
        self.all_room_data = []           # flat list
        self._tree_checkboxes = {}        # {room_id_int: CheckBox}
        self._level_checkboxes = {}       # {level_name: CheckBox}
        self._legend_checkboxes = {}      # {legend_id_int: (CheckBox, legend_view)}

        # Données du modèle
        self.view_templates = []
        self.title_blocks = []
        self.legend_views = []
        self.view_family_types = {}

        # Charger les données
        self._load_model_data()
        self._populate_step1()
        self._populate_step2()
        self._populate_step3()
        self._update_navigation()

    # ========================================================
    # Chargement des données modèle
    # ========================================================

    def _load_model_data(self):
        """Charge toutes les données nécessaires depuis le modèle Revit."""
        self.rooms_by_level = get_rooms_grouped_by_level(doc)
        self.all_room_data = get_all_rooms(doc)
        self.view_templates = get_view_templates(doc)
        self.title_blocks = get_title_blocks(doc)
        self.legend_views = get_legends(doc)
        self.view_family_types = get_view_family_types(doc)

    # ========================================================
    # ÉTAPE 1 — Sélection des rooms
    # ========================================================

    def _populate_step1(self):
        """Peuple le TreeView avec les rooms groupées par niveau."""
        self.tree_rooms.Items.Clear()
        self._tree_checkboxes.clear()
        self._level_checkboxes.clear()

        for level_name, rooms in self.rooms_by_level.items():
            # Noeud parent = Niveau
            level_item = TreeViewItem()
            level_item.IsExpanded = True
            level_item.Margin = Thickness(0, 2, 0, 2)

            # Header du niveau avec CheckBox
            level_header = StackPanel()
            level_header.Orientation = Orientation.Horizontal

            level_cb = CheckBox()
            level_cb.Margin = Thickness(0, 0, 8, 0)
            level_cb.VerticalAlignment = VerticalAlignment.Center
            level_cb.Tag = level_name
            level_cb.Checked += self._level_checkbox_changed
            level_cb.Unchecked += self._level_checkbox_changed
            self._level_checkboxes[level_name] = level_cb

            level_label = TextBlock()
            level_label.Text = u"{} ({} rooms)".format(level_name, len(rooms))
            level_label.FontWeight = FontWeights.SemiBold
            level_label.FontSize = 13
            level_label.Foreground = SolidColorBrush(WColor.FromRgb(124, 143, 255))

            level_header.Children.Add(level_cb)
            level_header.Children.Add(level_label)
            level_item.Header = level_header

            # Enfants = Rooms
            for rd in rooms:
                room_item = TreeViewItem()
                room_item.Margin = Thickness(0, 1, 0, 1)

                room_header = StackPanel()
                room_header.Orientation = Orientation.Horizontal

                room_cb = CheckBox()
                room_cb.Margin = Thickness(0, 0, 8, 0)
                room_cb.Tag = rd.id_int
                room_cb.Checked += self._room_checkbox_changed
                room_cb.Unchecked += self._room_checkbox_changed
                self._tree_checkboxes[rd.id_int] = room_cb

                room_label = TextBlock()
                room_label.Text = rd.display_name
                room_label.FontSize = 12
                room_label.Foreground = SolidColorBrush(WColor.FromRgb(238, 238, 255))

                room_header.Children.Add(room_cb)
                room_header.Children.Add(room_label)
                room_item.Header = room_header

                level_item.Items.Add(room_item)

            self.tree_rooms.Items.Add(level_item)

    def _level_checkbox_changed(self, sender, args):
        """Quand on coche/décoche un niveau, cascade sur toutes ses rooms."""
        level_name = sender.Tag
        is_checked = sender.IsChecked

        rooms = self.rooms_by_level.get(level_name, [])
        for rd in rooms:
            cb = self._tree_checkboxes.get(rd.id_int)
            if cb:
                cb.IsChecked = is_checked

        self._update_selected_rooms_from_tree()

    def _room_checkbox_changed(self, sender, args):
        """Quand on coche/décoche une room individuelle."""
        self._update_selected_rooms_from_tree()

    def _update_selected_rooms_from_tree(self):
        """Met à jour la liste des rooms sélectionnées depuis le TreeView."""
        if self.rb_select_list.IsChecked:
            self.selected_rooms = []
            for rd in self.all_room_data:
                cb = self._tree_checkboxes.get(rd.id_int)
                if cb and cb.IsChecked:
                    self.selected_rooms.append(rd)
            self._update_room_count()

    def _update_room_count(self):
        """Met à jour le compteur de rooms dans la sidebar."""
        self.txt_room_count.Text = str(len(self.selected_rooms))

    # --- Handlers de l'interface Étape 1 ---

    def selection_mode_changed(self, sender, args):
        """Bascule entre les deux modes de sélection."""
        if self.rb_select_plan.IsChecked:
            self.panel_select_plan.Visibility = Visibility.Visible
            self.panel_select_list.Visibility = Visibility.Collapsed
        else:
            self.panel_select_plan.Visibility = Visibility.Collapsed
            self.panel_select_list.Visibility = Visibility.Visible
            # Recalculer depuis le tree
            self._update_selected_rooms_from_tree()

    def pick_rooms_click(self, sender, args):
        """Lance la sélection interactive des rooms sur le plan."""
        self.Hide()
        try:
            picked = pick_rooms_from_plan(uidoc)
            if picked:
                self.selected_rooms = picked
                # Afficher dans la liste
                self.list_picked_rooms.Items.Clear()
                for rd in picked:
                    item = ListBoxItem()
                    item.Content = u"[{}]  {} - {}".format(
                        rd.level_name, rd.number, rd.name
                    )
                    item.Foreground = SolidColorBrush(WColor.FromRgb(238, 238, 255))
                    item.FontSize = 12
                    self.list_picked_rooms.Items.Add(item)

                self.txt_picked_info.Text = u"✓ {} room(s) sélectionnée(s)".format(len(picked))
            else:
                self.txt_picked_info.Text = u"Aucune room sélectionnée."
        except Exception as e:
            logger.error("Erreur sélection rooms: {}".format(str(e)))
            self.txt_picked_info.Text = u"Erreur: {}".format(str(e))
        finally:
            self.Show()

        self._update_room_count()

    def check_all_click(self, sender, args):
        """Coche toutes les rooms."""
        for cb in self._level_checkboxes.values():
            cb.IsChecked = True

    def uncheck_all_click(self, sender, args):
        """Décoche toutes les rooms."""
        for cb in self._level_checkboxes.values():
            cb.IsChecked = False

    def search_rooms_changed(self, sender, args):
        """Filtre les rooms dans le TreeView selon le texte saisi."""
        search_text = self.txt_search_rooms.Text.strip().lower()

        for level_item in self.tree_rooms.Items:
            level_visible = False
            for room_item in level_item.Items:
                # Récupérer le TextBlock dans le header
                header = room_item.Header
                if header and hasattr(header, 'Children') and header.Children.Count > 1:
                    label = header.Children[1]  # TextBlock
                    text = label.Text.lower() if hasattr(label, 'Text') else ""
                    if not search_text or search_text in text:
                        room_item.Visibility = Visibility.Visible
                        level_visible = True
                    else:
                        room_item.Visibility = Visibility.Collapsed

            level_item.Visibility = Visibility.Visible if level_visible or not search_text \
                else Visibility.Collapsed

    # ========================================================
    # ÉTAPE 2 — Choix des vues (pré-rempli, actif Phase 2)
    # ========================================================

    def _populate_step2(self):
        """Peuple les ComboBox de gabarits de vue."""
        # Option "Aucun gabarit"
        no_template = "<Aucun gabarit>"

        # Floor Plan templates
        self.cmb_floor_template.Items.Clear()
        self.cmb_floor_template.Items.Add(no_template)
        for t in self.view_templates:
            self.cmb_floor_template.Items.Add(t.Name)
        self.cmb_floor_template.SelectedIndex = 0

        # Elevation templates
        self.cmb_elev_template.Items.Clear()
        self.cmb_elev_template.Items.Add(no_template)
        for t in self.view_templates:
            self.cmb_elev_template.Items.Add(t.Name)
        self.cmb_elev_template.SelectedIndex = 0

        # Ceiling Plan templates
        self.cmb_ceiling_template.Items.Clear()
        self.cmb_ceiling_template.Items.Add(no_template)
        for t in self.view_templates:
            self.cmb_ceiling_template.Items.Add(t.Name)
        self.cmb_ceiling_template.SelectedIndex = 0

    # ========================================================
    # ÉTAPE 3 — Feuilles & Légendes (pré-rempli, actif Phase 4)
    # ========================================================

    def _populate_step3(self):
        """Peuple les cartouches et légendes."""
        # Cartouches
        self.cmb_titleblock.Items.Clear()
        for tb in self.title_blocks:
            self.cmb_titleblock.Items.Add(get_title_block_display_name(tb))
        if self.title_blocks:
            self.cmb_titleblock.SelectedIndex = 0

        # Légendes avec CheckBox
        self.list_legends.Items.Clear()
        self._legend_checkboxes.clear()
        for legend in self.legend_views:
            sp = StackPanel()
            sp.Orientation = Orientation.Horizontal
            sp.Margin = Thickness(4, 3, 4, 3)

            cb = CheckBox()
            cb.Margin = Thickness(0, 0, 8, 0)
            cb.VerticalAlignment = VerticalAlignment.Center

            lbl = TextBlock()
            lbl.Text = legend.Name
            lbl.FontSize = 12
            lbl.Foreground = SolidColorBrush(WColor.FromRgb(238, 238, 255))
            lbl.VerticalAlignment = VerticalAlignment.Center

            sp.Children.Add(cb)
            sp.Children.Add(lbl)

            item = ListBoxItem()
            item.Content = sp
            item.Background = SolidColorBrush(WColor.FromArgb(0, 0, 0, 0))
            self.list_legends.Items.Add(item)

            self._legend_checkboxes[legend.Id.IntegerValue] = (cb, legend)

    # ========================================================
    # ÉTAPE 4 — Résumé (actif Phase 4-5)
    # ========================================================

    def _build_summary(self):
        """Construit le texte récapitulatif pour l'étape 4."""
        lines = []
        n = len(self.selected_rooms)
        lines.append(u"── Rooms sélectionnées : {} ──".format(n))
        lines.append("")

        # Vues
        view_count = 0
        lines.append(u"── Vues à créer ──")
        if self.chk_floor_plan.IsChecked:
            lines.append(u"  ▸ Vues en plan : {} (1:{})".format(
                n, self.txt_floor_scale.Text))
            view_count += n
        if self.chk_ceiling_plan.IsChecked:
            lines.append(u"  ▸ Plans de plafond : {} (1:{})".format(
                n, self.txt_ceiling_scale.Text))
            view_count += n
        if self.chk_elevations.IsChecked:
            elev_dirs = sum([
                1 if self.chk_elev_north.IsChecked else 0,
                1 if self.chk_elev_south.IsChecked else 0,
                1 if self.chk_elev_east.IsChecked else 0,
                1 if self.chk_elev_west.IsChecked else 0,
            ])
            dirs_labels = []
            if self.chk_elev_north.IsChecked: dirs_labels.append("N")
            if self.chk_elev_south.IsChecked: dirs_labels.append("S")
            if self.chk_elev_east.IsChecked: dirs_labels.append("E")
            if self.chk_elev_west.IsChecked: dirs_labels.append("W")
            lines.append(u"  ▸ Élévations : {} ({} × {}) (1:{})".format(
                elev_dirs * n, "+".join(dirs_labels), n, self.txt_elev_scale.Text))
            view_count += elev_dirs * n

        lines.append(u"  ▸ Total : {} vues".format(view_count))

        # Feuilles
        lines.append(u"")
        lines.append(u"── Feuilles ──")
        lines.append(u"  ▸ Feuilles à créer : {}".format(n))

        prefix = self.txt_sheet_prefix.Text.strip()
        start = self.txt_sheet_start.Text.strip()
        try:
            start_num = int(start)
            padding = max(len(start), 3)
            first_num = "{}{}".format(prefix, str(start_num).zfill(padding))
            last_num = "{}{}".format(prefix, str(start_num + n - 1).zfill(padding))
            lines.append(u"  ▸ Numérotation : {} → {}".format(first_num, last_num))
        except ValueError:
            pass

        if self.cmb_titleblock.SelectedIndex >= 0:
            lines.append(u"  ▸ Cartouche : {}".format(self.cmb_titleblock.SelectedItem))

        # Légendes
        selected_legends = [leg.Name for lid, (cb, leg)
                           in self._legend_checkboxes.items() if cb.IsChecked]
        lines.append(u"")
        lines.append(u"── Légendes ──")
        if selected_legends:
            for lg_name in selected_legends:
                lines.append(u"  ▸ {}".format(lg_name))
            lines.append(u"  ({} légende(s) sur chaque feuille)".format(len(selected_legends)))
        else:
            lines.append(u"  Aucune légende sélectionnée")

        return "\n".join(lines)

    # ========================================================
    # Navigation du wizard
    # ========================================================

    def _update_navigation(self):
        """Met à jour la visibilité des boutons et indicateurs d'étapes."""
        # Panels
        self.step1_panel.Visibility = Visibility.Visible if self.current_step == 1 else Visibility.Collapsed
        self.step2_panel.Visibility = Visibility.Visible if self.current_step == 2 else Visibility.Collapsed
        self.step3_panel.Visibility = Visibility.Visible if self.current_step == 3 else Visibility.Collapsed
        self.step4_panel.Visibility = Visibility.Visible if self.current_step == 4 else Visibility.Collapsed

        # Boutons
        self.btn_prev.Visibility = Visibility.Visible if self.current_step > 1 else Visibility.Collapsed
        self.btn_next.Visibility = Visibility.Visible if self.current_step < self.total_steps else Visibility.Collapsed
        self.btn_create.Visibility = Visibility.Visible if self.current_step == self.total_steps else Visibility.Collapsed

        # Indicateurs d'étapes (sidebar)
        steps_indicators = [
            self.step1_indicator, self.step2_indicator,
            self.step3_indicator, self.step4_indicator
        ]
        for i, ind in enumerate(steps_indicators):
            if i + 1 == self.current_step:
                ind.Style = self.FindResource("StepActive")
                # Rendre le texte du step actif en blanc
                for child in ind.Child.Children:
                    if isinstance(child, TextBlock) and child.FontSize == 13:
                        child.Foreground = SolidColorBrush(WColor.FromRgb(238, 238, 255))
            else:
                ind.Style = self.FindResource("StepInactive")
                for child in ind.Child.Children:
                    if isinstance(child, TextBlock) and child.FontSize == 13:
                        child.Foreground = SolidColorBrush(WColor.FromRgb(153, 153, 187))

        # Si on arrive à l'étape 4, construire le résumé
        if self.current_step == 4:
            self.txt_summary.Text = self._build_summary()

    def _validate_current_step(self):
        """Valide l'étape courante avant de passer à la suivante.

        Returns:
            bool: True si la validation est ok.
        """
        if self.current_step == 1:
            if not self.selected_rooms:
                forms.alert(
                    "Veuillez sélectionner au moins une room.",
                    title="Sélection requise"
                )
                return False

        elif self.current_step == 2:
            if not any([
                self.chk_floor_plan.IsChecked,
                self.chk_elevations.IsChecked,
                self.chk_ceiling_plan.IsChecked
            ]):
                forms.alert(
                    "Veuillez sélectionner au moins un type de vue à créer.",
                    title="Vue requise"
                )
                return False

        elif self.current_step == 3:
            if self.cmb_titleblock.SelectedIndex < 0:
                forms.alert(
                    "Veuillez sélectionner un cartouche.",
                    title="Cartouche requis"
                )
                return False

        return True

    def next_click(self, sender, args):
        """Avance à l'étape suivante."""
        if not self._validate_current_step():
            return

        if self.current_step < self.total_steps:
            self.current_step += 1
            self._update_navigation()

    def prev_click(self, sender, args):
        """Retourne à l'étape précédente."""
        if self.current_step > 1:
            self.current_step -= 1
            self._update_navigation()

    def cancel_click(self, sender, args):
        """Ferme la fenêtre."""
        self.Close()

    def create_click(self, sender, args):
        """Lance la création complète : vues → feuilles → viewports → légendes."""
        config = self._collect_configuration()
        rooms = config["rooms"]

        if not rooms:
            forms.alert("Aucune room sélectionnée.", title="Erreur")
            return

        # Afficher la barre de progression
        self.panel_progress.Visibility = Visibility.Visible
        self.btn_create.IsEnabled = False
        self.btn_prev.IsEnabled = False
        total = len(rooms)

        # Compteurs
        count_plans = 0
        count_ceilings = 0
        count_elevations = 0
        count_sheets = 0
        count_viewports = 0
        count_legends = 0
        errors = []

        # Stocker les résultats par room
        views_per_room = {}

        # TransactionGroup pour tout regrouper en un seul Undo
        tg = TransactionGroup(doc, "Room by Room — Création complète")
        tg.Start()

        try:
            # ──────────────────────────────────────────────
            # PASSE 1 : Créer toutes les vues
            # ──────────────────────────────────────────────
            for i, room_data in enumerate(rooms):
                room = doc.GetElement(room_data.id)
                if not room:
                    errors.append(u"Room {} introuvable".format(room_data.display_name))
                    continue

                self._update_progress(
                    int(((i + 0.5) / total) * 50),
                    u"Création des vues {}/{} — {} {}...".format(
                        i + 1, total, room_data.number, room_data.name
                    )
                )

                t = Transaction(doc, "RBR Vues — {}".format(room_data.display_name))
                t.Start()
                try:
                    views_result = create_all_views_for_room(doc, room, config)

                    if views_result["floor_plan"]:
                        count_plans += 1
                    if views_result["ceiling_plan"]:
                        count_ceilings += 1
                    count_elevations += len(views_result["elevations"])

                    views_per_room[room_data.id_int] = {
                        "room_data": room_data,
                        "views": views_result,
                    }
                    t.Commit()

                except Exception as e:
                    t.RollBack()
                    errors.append(u"Vues {} : {}".format(room_data.display_name, str(e)))
                    logger.error("Erreur vues room {}: {}".format(room_data.id_int, str(e)))

            # ──────────────────────────────────────────────
            # PASSE 2 : Créer les feuilles + placer viewports
            # ──────────────────────────────────────────────
            sheet_index = 0
            for i, room_data in enumerate(rooms):
                entry = views_per_room.get(room_data.id_int)
                if not entry:
                    continue  # pas de vues → pas de feuille

                views_result = entry["views"]

                # Vérifier qu'il y a au moins une vue à placer
                has_views = (
                    views_result.get("floor_plan") or
                    views_result.get("ceiling_plan") or
                    views_result.get("elevations")
                )
                if not has_views:
                    continue

                self._update_progress(
                    50 + int(((i + 0.5) / total) * 50),
                    u"Feuille {}/{} — {} {}...".format(
                        i + 1, total, room_data.number, room_data.name
                    )
                )

                t = Transaction(doc, "RBR Feuille — {}".format(room_data.display_name))
                t.Start()
                try:
                    sheet_result = create_sheet_for_room(
                        doc, room_data, views_result, config, sheet_index
                    )

                    if sheet_result["sheet"]:
                        count_sheets += 1
                        count_viewports += len(sheet_result["viewports"])
                        sheet_index += 1

                        # Placer les légendes si la feuille a été créée
                        legends = config.get("legends", [])
                        if legends and sheet_result["sheet"]:
                            legend_vps = place_legends_on_sheet(
                                doc, sheet_result["sheet"], legends
                            )
                            count_legends += len(legend_vps)

                    t.Commit()

                except Exception as e:
                    t.RollBack()
                    errors.append(u"Feuille {} : {}".format(
                        room_data.display_name, str(e)))
                    logger.error("Erreur feuille room {}: {}".format(
                        room_data.id_int, str(e)))

            tg.Assimilate()

        except Exception as e:
            tg.RollBack()
            forms.alert(
                u"Erreur critique : {}\n\n"
                u"Toutes les modifications ont été annulées.".format(str(e)),
                title="Erreur"
            )
            self.btn_create.IsEnabled = True
            self.btn_prev.IsEnabled = True
            return

        # ──────────────────────────────────────────────
        # Résultat final
        # ──────────────────────────────────────────────
        self.progress_bar.Value = 100
        self.txt_progress.Text = u"Terminé !"

        total_views = count_plans + count_ceilings + count_elevations
        summary_lines = [
            u"Création terminée avec succès !\n",
            u"── Vues ──",
            u"▸ Plans créés : {}".format(count_plans),
            u"▸ Plans de plafond : {}".format(count_ceilings),
            u"▸ Élévations : {}".format(count_elevations),
            u"▸ Total vues : {}".format(total_views),
            u"",
            u"── Feuilles ──",
            u"▸ Feuilles créées : {}".format(count_sheets),
            u"▸ Viewports placés : {}".format(count_viewports),
        ]

        if count_legends > 0:
            summary_lines.append(u"▸ Légendes placées : {}".format(count_legends))

        if errors:
            summary_lines.append(u"\n⚠ Erreurs ({}) :".format(len(errors)))
            for err in errors[:10]:
                summary_lines.append(u"  • {}".format(err))
            if len(errors) > 10:
                summary_lines.append(u"  ... et {} autres".format(len(errors) - 10))

        forms.alert(
            "\n".join(summary_lines),
            title="Room by Room — Résultat"
        )

        self.Close()

    def _update_progress(self, percent, text):
        """Met à jour la barre de progression et force le refresh WPF."""
        self.progress_bar.Value = percent
        self.txt_progress.Text = text
        try:
            import System.Windows.Threading
            System.Windows.Threading.Dispatcher.CurrentDispatcher.Invoke(
                System.Windows.Threading.DispatcherPriority.Render,
                System.Action(lambda: None)
            )
        except Exception:
            pass

    def _collect_configuration(self):
        """Rassemble toute la configuration choisie par l'utilisateur.

        Returns:
            dict: Configuration complète.
        """
        config = {
            "rooms": self.selected_rooms,

            # Vues
            "create_floor_plan": self.chk_floor_plan.IsChecked,
            "floor_template_name": self.cmb_floor_template.SelectedItem \
                if self.cmb_floor_template.SelectedIndex > 0 else None,
            "floor_offset_mm": self._parse_float(self.txt_floor_offset.Text, 300),
            "floor_scale": int(self._parse_float(self.txt_floor_scale.Text, 100)),

            "create_elevations": self.chk_elevations.IsChecked,
            "elev_template_name": self.cmb_elev_template.SelectedItem \
                if self.cmb_elev_template.SelectedIndex > 0 else None,
            "elev_directions": {
                "north": self.chk_elev_north.IsChecked,
                "south": self.chk_elev_south.IsChecked,
                "east": self.chk_elev_east.IsChecked,
                "west": self.chk_elev_west.IsChecked,
            },
            "elev_offset_mm": self._parse_float(self.txt_elev_offset.Text, 300),
            "elev_scale": int(self._parse_float(self.txt_elev_scale.Text, 50)),

            "create_ceiling_plan": self.chk_ceiling_plan.IsChecked,
            "ceiling_template_name": self.cmb_ceiling_template.SelectedItem \
                if self.cmb_ceiling_template.SelectedIndex > 0 else None,
            "ceiling_offset_mm": self._parse_float(self.txt_ceiling_offset.Text, 300),
            "ceiling_scale": int(self._parse_float(self.txt_ceiling_scale.Text, 100)),

            # Feuilles
            "titleblock_index": self.cmb_titleblock.SelectedIndex,
            "titleblock": self.title_blocks[self.cmb_titleblock.SelectedIndex] \
                if self.cmb_titleblock.SelectedIndex >= 0 and self.title_blocks else None,
            "sheet_prefix": self.txt_sheet_prefix.Text.strip(),
            "sheet_start": self.txt_sheet_start.Text.strip(),

            # Légendes
            "legends": [
                leg for lid, (cb, leg) in self._legend_checkboxes.items()
                if cb.IsChecked
            ],
        }
        return config

    @staticmethod
    def _parse_float(text, default=0.0):
        """Parse un texte en float avec valeur par défaut."""
        try:
            return float(text)
        except (ValueError, TypeError):
            return default


# ============================================================
# Point d'entrée
# ============================================================

def main():
    """Lance le wizard Room by Room."""
    window = RoomByRoomWindow()
    window.ShowDialog()


if __name__ == "__main__":
    main()

main()
