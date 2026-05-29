# coding: utf8
from __future__ import print_function

import io
import os
import tempfile
from collections import defaultdict
from datetime import datetime

from Autodesk.Revit.DB import (
    BuiltInCategory,
    ElementId,
    ElementTypeGroup,
    FamilyInstance,
    FamilySymbol,
    FilteredElementCollector,
    IndependentTag,
    Reference,
    RevitLinkInstance,
    TextNote,
    TextNoteOptions,
    TextNoteType,
    Transaction,
    View,
    ViewPlan,
    XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import DB, forms, revit, script
from pyrevit.forms import WPFWindow
from System.Windows.Controls import CheckBox
from System.Windows import Visibility
import System


doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

__title__ = "Linked Type\nOverlay"
__doc__ = "Select linked element types, analyze host plan views, and create family, tag, or text overlays at linked element locations."


def normalize_name(text):
    if not text:
        return ""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def safe_name(element, fallback="<Unnamed>"):
    try:
        value = getattr(element, "Name", None)
        if value:
            return value
    except Exception:
        pass
    return fallback


def safe_link_name(link_inst):
    try:
        return link_inst.Name or "<Unnamed Link>"
    except Exception:
        return "<Unnamed Link>"


def is_architectural_link(name):
    lowered = (name or "").lower()
    return any(token in lowered for token in ("arch", "architect", "a_", "ar_", "-a-", "[a]"))


def get_loaded_links():
    rows = []
    try:
        instances = FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements()
    except Exception:
        instances = []

    for link_inst in instances:
        try:
            link_doc = link_inst.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            continue

        name = safe_link_name(link_inst)
        rows.append(
            {
                "instance": link_inst,
                "name": name,
                "display": "{0} [{1}]".format(
                    name,
                    "ARCH" if is_architectural_link(name) else "LINK",
                ),
            }
        )

    rows.sort(key=lambda item: (0 if is_architectural_link(item["name"]) else 1, item["name"].lower()))
    return rows


def get_plan_views():
    views = []
    try:
        collected = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    except Exception:
        collected = []

    allowed_types = {
        DB.ViewType.FloorPlan,
        DB.ViewType.CeilingPlan,
        DB.ViewType.EngineeringPlan,
        DB.ViewType.AreaPlan,
    }

    for view in collected:
        try:
            if view is None or view.IsTemplate:
                continue
            if view.ViewType not in allowed_types:
                continue
            level_name = "No Level"
            try:
                if hasattr(view, "GenLevel") and view.GenLevel:
                    level_name = view.GenLevel.Name
            except Exception:
                pass
            display = "{0} | {1} | {2}".format(level_name, safe_name(view), str(view.ViewType))
            search_text = "{0} {1} {2}".format(level_name, safe_name(view), str(view.ViewType)).lower()
            views.append({"view": view, "display": display, "search": search_text})
        except Exception:
            continue

    views.sort(key=lambda item: item["display"].lower())
    return views


def _center_from_bbox(bbox):
    if bbox is None:
        return None
    try:
        return XYZ(
            (bbox.Min.X + bbox.Max.X) * 0.5,
            (bbox.Min.Y + bbox.Max.Y) * 0.5,
            (bbox.Min.Z + bbox.Max.Z) * 0.5,
        )
    except Exception:
        return None


def get_element_point(element, source_doc=None):
    if element is None:
        return None

    try:
        loc = element.Location
        if loc is not None:
            if hasattr(loc, "Point") and loc.Point is not None:
                return loc.Point
            if hasattr(loc, "Curve") and loc.Curve is not None:
                return loc.Curve.Evaluate(0.5, True)
    except Exception:
        pass

    try:
        bbox = element.get_BoundingBox(None)
        if bbox is not None:
            return _center_from_bbox(bbox)
    except Exception:
        pass

    if source_doc is not None:
        try:
            owner_view_id = getattr(element, "OwnerViewId", None)
            if owner_view_id and owner_view_id != ElementId.InvalidElementId:
                owner_view = source_doc.GetElement(owner_view_id)
                bbox = element.get_BoundingBox(owner_view) if owner_view is not None else None
                point = _center_from_bbox(bbox)
                if point is not None:
                    return point
        except Exception:
            pass

        try:
            options = DB.Options()
            options.IncludeNonVisibleObjects = True
            geometry = element.get_Geometry(options)
            if geometry is not None:
                try:
                    geom_bbox = geometry.GetBoundingBox()
                except Exception:
                    geom_bbox = None
                point = _center_from_bbox(geom_bbox)
                if point is not None:
                    return point
        except Exception:
            pass

    return None


def get_source_descriptor(element, source_doc):
    if element is None or source_doc is None:
        return None

    try:
        category = element.Category
    except Exception:
        category = None

    if category is None:
        return None

    category_id = None
    category_name = "<No Category>"
    try:
        category_id = category.Id.IntegerValue
        category_name = category.Name or "<No Category>"
    except Exception:
        return None

    type_elem = None
    type_name = ""
    family_name = ""
    source_label = safe_name(element)

    try:
        type_id = element.GetTypeId()
    except Exception:
        type_id = ElementId.InvalidElementId
    type_id_int = None
    try:
        if type_id and type_id != ElementId.InvalidElementId:
            type_id_int = type_id.IntegerValue
    except Exception:
        type_id_int = None

    if type_id and type_id != ElementId.InvalidElementId:
        try:
            type_elem = source_doc.GetElement(type_id)
        except Exception:
            type_elem = None

    if isinstance(element, FamilyInstance):
        try:
            symbol = getattr(element, "Symbol", None)
            family = getattr(symbol, "Family", None) if symbol is not None else None
            if family is not None:
                family_name = safe_name(family, "")
            if symbol is not None:
                type_name = safe_name(symbol, "")
        except Exception:
            pass

    if not family_name and type_elem is not None:
        try:
            family_name = getattr(type_elem, "FamilyName", None) or ""
        except Exception:
            family_name = ""

    if not type_name and type_elem is not None:
        type_name = safe_name(type_elem, "")

    if not family_name:
        family_name = category_name
    if not type_name:
        type_name = source_label or category_name

    if type_id_int is not None:
        key = (category_id, "tid", type_id_int)
    else:
        key = (category_id, "name", normalize_name(family_name), normalize_name(type_name))
    return {
        "key": key,
        "category_id": category_id,
        "category_name": category_name,
        "family_name": family_name,
        "type_name": type_name,
        "type_id_int": type_id_int,
        "source_label": source_label,
    }


def _collect_link_levels(link_doc):
    """Return all Level elements from the linked doc (cached per call site)."""
    try:
        return list(FilteredElementCollector(link_doc).OfClass(DB.Level).ToElements())
    except Exception:
        return []


def best_match_link_level(host_level, link_levels):
    """Find the best-matching level in link_levels for host_level.
    Accepts a pre-fetched list so the collector runs only once per view.
    """
    if not host_level or not link_levels:
        return None

    if not link_levels:
        return None

    host_name = None
    host_elevation = None
    try:
        host_name = host_level.Name
    except Exception:
        pass
    try:
        host_elevation = host_level.Elevation
    except Exception:
        pass

    if host_name:
        for level in link_levels:
            try:
                if level.Name == host_name:
                    return level
            except Exception:
                continue

    if host_elevation is not None:
        best = None
        best_delta = None
        for level in link_levels:
            try:
                delta = abs(level.Elevation - host_elevation)
                if best_delta is None or delta < best_delta:
                    best = level
                    best_delta = delta
            except Exception:
                continue
        return best

    return None


def point_in_view_crop(view, world_point):
    if view is None or world_point is None:
        return False

    try:
        if not view.CropBoxActive:
            return True
    except Exception:
        return True

    try:
        crop = view.CropBox
        if crop is None:
            return True
        transform = crop.Transform
        if transform is None:
            local = world_point
        else:
            local = transform.Inverse.OfPoint(world_point)
        tol = 1e-6
        return (
            crop.Min.X - tol <= local.X <= crop.Max.X + tol
            and crop.Min.Y - tol <= local.Y <= crop.Max.Y + tol
        )
    except Exception:
        return True


def family_placement_name(symbol):
    if symbol is None:
        return ""
    try:
        family = symbol.Family
        placement = getattr(family, "FamilyPlacementType", None)
        if placement is not None:
            return str(placement)
    except Exception:
        pass
    return ""


def is_supported_host_symbol(symbol):
    placement_name = family_placement_name(symbol)
    return "ViewBased" in placement_name or "OneLevelBased" in placement_name


def write_log(lines, slug):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(tempfile.gettempdir(), "{0}-{1}.log".format(slug, timestamp))
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path


class LinkedTypeOverlayWindow(WPFWindow):
    _DUPLICATE_TOLERANCE = 0.25

    def __init__(self, xaml_file_name):
        WPFWindow.__init__(self, xaml_file_name)

        self.links = []
        self.active_link_id = None
        self.source_type_items = []
        self.source_instances_by_key = {}
        self.view_items = []
        self.visible_source_items = []
        self.visible_view_items = []
        self.host_symbol_items = []
        self.tag_symbol_items = []
        self.text_type_items = []
        self.analysis_rows = []
        self.last_summary = []

        self._load_links()
        if not self.links:
            return

        self._seed_active_link()
        self._build_view_list()
        self._load_output_choices()
        self.cmbSourceInputMode.SelectedIndex = 0
        self._update_source_input_mode_ui()
        self.txtNoteFormat.Text = ""
        self.cmbOutputMode.SelectedIndex = 0
        self._refresh_source_types()
        self._refresh_view_list("")
        self._update_output_mode_ui()
        self._update_source_summary()
        self._update_view_summary()

    def _load_links(self):
        self.links = get_loaded_links()
        if not self.links:
            forms.alert("No loaded Revit links found. Load at least one linked model and retry.")
            self.Close()

    def _seed_active_link(self):
        if not self.links:
            self.active_link_id = None
            return
        # Prefer architectural-like links, fallback to first loaded link.
        chosen = self.links[0]
        for row in self.links:
            if is_architectural_link(row.get("name", "")):
                chosen = row
                break
        try:
            self.active_link_id = chosen["instance"].Id.IntegerValue
        except Exception:
            self.active_link_id = None
        self._update_active_link_info()

    def _get_link_row_by_id(self, link_id_int):
        if link_id_int is None:
            return None
        for row in self.links:
            try:
                if row["instance"].Id.IntegerValue == link_id_int:
                    return row
            except Exception:
                continue
        return None

    def _selected_link(self):
        row = self._get_link_row_by_id(self.active_link_id)
        if row is not None:
            return row["instance"]
        return self.links[0]["instance"] if self.links else None

    def _selected_link_doc(self):
        link_inst = self._selected_link()
        if link_inst is None:
            return None
        try:
            return link_inst.GetLinkDocument()
        except Exception:
            return None

    def _set_selected_link_by_id(self, link_id_int):
        row = self._get_link_row_by_id(link_id_int)
        if row is None:
            return False
        try:
            self.active_link_id = row["instance"].Id.IntegerValue
        except Exception:
            self.active_link_id = None
        self._update_active_link_info()
        return True

    def _update_active_link_info(self):
        box = getattr(self, "txtActiveLinkInfo", None)
        if box is None:
            return
        row = self._get_link_row_by_id(self.active_link_id)
        if row is None:
            box.Text = "No active linked model yet. Click Pick from Current View to set it automatically."
            return
        box.Text = "{0}".format(row.get("display", "<Linked Model>"))

    def _build_source_checkbox(self, item):
        cb = CheckBox()
        cb.Content = item["display"]
        cb.IsChecked = False
        cb.ToolTip = "Tick this linked element type to include it in the analysis and overlay run."
        cb.Checked += self.source_selection_changed
        cb.Unchecked += self.source_selection_changed
        return cb

    def _build_view_checkbox(self, item, is_checked):
        cb = CheckBox()
        cb.Content = item["display"]
        cb.IsChecked = is_checked
        cb.ToolTip = "Tick this host plan view to analyze linked element locations and place overlay output there."
        cb.Checked += self.view_selection_changed
        cb.Unchecked += self.view_selection_changed
        return cb

    def _refresh_source_types(self):
        selected_keys = set(
            item["key"] for item in self.source_type_items if bool(item["cb"].IsChecked)
        )

        link_doc = self._selected_link_doc()
        self.source_type_items = []
        self.source_instances_by_key = {}

        if link_doc is None:
            self._refresh_source_list("")
            self._reset_analysis()
            return

        counters = {}
        try:
            instances = FilteredElementCollector(link_doc).WhereElementIsNotElementType().ToElements()
        except Exception:
            instances = []

        for inst in instances:
            descriptor = get_source_descriptor(inst, link_doc)
            if descriptor is None:
                continue

            key = descriptor["key"]
            data = counters.get(key)
            if data is None:
                data = dict(descriptor)
                data["count"] = 0
                counters[key] = data
            data["count"] += 1
            self.source_instances_by_key.setdefault(key, []).append(inst)

        for key, data in sorted(counters.items(), key=lambda item: (
            item[1]["category_name"].lower(),
            item[1]["family_name"].lower(),
            item[1]["type_name"].lower(),
        )):
            display = "{0} | {1} : {2} [{3}]".format(
                data["category_name"],
                data["family_name"],
                data["type_name"],
                data["count"],
            )
            row = dict(data)
            row["display"] = display
            row["search"] = "{0} {1} {2}".format(
                data["category_name"],
                data["family_name"],
                data["type_name"],
            ).lower()
            row["cb"] = self._build_source_checkbox(row)
            if key in selected_keys:
                row["cb"].IsChecked = True
            self.source_type_items.append(row)

        self._refresh_source_list(self.txtSourceSearch.Text)
        self._reset_analysis()
        self._update_active_link_info()

    def _refresh_source_list(self, search_text):
        self.lstSourceTypes.Items.Clear()
        self.visible_source_items = []
        query = (search_text or "").strip().lower()
        for item in self.source_type_items:
            if query and query not in item["search"]:
                continue
            self.visible_source_items.append(item)
            self.lstSourceTypes.Items.Add(item["cb"])
        self._update_source_summary()

    def _set_selected_source_keys(self, keys_to_select):
        keys_to_select = set(keys_to_select or [])
        if not keys_to_select:
            return 0

        selected_count = 0
        for item in self.source_type_items:
            should_select = item["key"] in keys_to_select
            item["cb"].IsChecked = should_select
            if should_select:
                selected_count += 1

        self._update_source_summary()
        self._reset_analysis()
        return selected_count

    def _build_view_list(self):
        active_view_id = None
        try:
            active_view = revit.active_view
            if active_view is not None:
                active_view_id = active_view.Id.IntegerValue
        except Exception:
            active_view_id = None

        self.view_items = []
        for item in get_plan_views():
            view = item["view"]
            try:
                is_checked = view.Id.IntegerValue == active_view_id
            except Exception:
                is_checked = False
            row = dict(item)
            row["cb"] = self._build_view_checkbox(row, is_checked)
            self.view_items.append(row)

        if self.view_items and not any(bool(item["cb"].IsChecked) for item in self.view_items):
            self.view_items[0]["cb"].IsChecked = True

    def _refresh_view_list(self, search_text):
        self.lstPlanViews.Items.Clear()
        self.visible_view_items = []
        query = (search_text or "").strip().lower()
        for item in self.view_items:
            if query and query not in item["search"]:
                continue
            self.visible_view_items.append(item)
            self.lstPlanViews.Items.Add(item["cb"])
        self._update_view_summary()

    def _set_active_view_only(self):
        active_view_id = None
        try:
            if revit.active_view is not None:
                active_view_id = revit.active_view.Id.IntegerValue
        except Exception:
            active_view_id = None

        if active_view_id is None:
            return False

        matched = False
        for item in self.view_items:
            try:
                is_active = item["view"].Id.IntegerValue == active_view_id
            except Exception:
                is_active = False
            item["cb"].IsChecked = is_active
            matched = matched or is_active
        return matched

    def _load_output_choices(self):
        self.host_symbol_items = []
        self.tag_symbol_items = []
        self.text_type_items = []

        try:
            family_symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).WhereElementIsElementType().ToElements()
        except Exception:
            family_symbols = []

        for symbol in family_symbols:
            try:
                category = symbol.Category
                family = symbol.Family
                if category is None or family is None:
                    continue
                display = "{0} | {1} : {2}".format(
                    category.Name or "<No Category>",
                    safe_name(family),
                    safe_name(symbol),
                )
                row = {"symbol": symbol, "display": display}
                if is_supported_host_symbol(symbol):
                    self.host_symbol_items.append(row)
                if bool(getattr(category, "IsTagCategory", False)):
                    self.tag_symbol_items.append(row)
            except Exception:
                continue

        self.host_symbol_items.sort(key=lambda item: item["display"].lower())
        self.tag_symbol_items.sort(key=lambda item: item["display"].lower())

        try:
            text_types = FilteredElementCollector(doc).OfClass(TextNoteType).ToElements()
        except Exception:
            text_types = []
        for text_type in text_types:
            self.text_type_items.append({"type": text_type, "display": safe_name(text_type)})
        self.text_type_items.sort(key=lambda item: item["display"].lower())

        self.cmbHostFamilyType.Items.Clear()
        for item in self.host_symbol_items:
            self.cmbHostFamilyType.Items.Add(item["display"])
        if self.host_symbol_items:
            self.cmbHostFamilyType.SelectedIndex = 0

        self.cmbTagType.Items.Clear()
        for item in self.tag_symbol_items:
            self.cmbTagType.Items.Add(item["display"])
        if self.tag_symbol_items:
            self.cmbTagType.SelectedIndex = 0

        self.cmbTextType.Items.Clear()
        for item in self.text_type_items:
            self.cmbTextType.Items.Add(item["display"])
        if self.text_type_items:
            self.cmbTextType.SelectedIndex = 0

    def _selected_source_items(self):
        return [item for item in self.source_type_items if bool(item["cb"].IsChecked)]

    def _selected_views(self):
        return [item["view"] for item in self.view_items if bool(item["cb"].IsChecked)]

    def _selected_output_mode(self):
        selected = getattr(self.cmbOutputMode, "SelectedItem", None)
        if selected is None:
            return "family"
        text = str(selected.Content) if hasattr(selected, "Content") else str(selected)
        lowered = text.lower()
        if "tag" in lowered:
            return "tag"
        if "text" in lowered:
            return "text"
        return "family"

    def _selected_source_input_mode(self):
        selected = getattr(self.cmbSourceInputMode, "SelectedItem", None)
        if selected is None:
            return "find"
        text = str(selected.Content) if hasattr(selected, "Content") else str(selected)
        lowered = text.lower()
        if "pick" in lowered:
            return "pick"
        return "find"

    def _selected_host_symbol(self):
        idx = getattr(self.cmbHostFamilyType, "SelectedIndex", -1)
        if idx is None or idx < 0 or idx >= len(self.host_symbol_items):
            return None
        return self.host_symbol_items[idx]["symbol"]

    def _selected_tag_symbol(self):
        idx = getattr(self.cmbTagType, "SelectedIndex", -1)
        if idx is None or idx < 0 or idx >= len(self.tag_symbol_items):
            return None
        return self.tag_symbol_items[idx]["symbol"]

    def _selected_text_type(self):
        idx = getattr(self.cmbTextType, "SelectedIndex", -1)
        if idx is None or idx < 0 or idx >= len(self.text_type_items):
            return None
        return self.text_type_items[idx]["type"]

    def _update_source_summary(self):
        selected = self._selected_source_items()
        if not selected:
            self.txtSourceSummary.Text = "No linked element types selected yet."
            return

        lines = ["Selected linked element types: {0}".format(len(selected))]
        for item in selected[:6]:
            lines.append("- {0}".format(item["display"]))
        if len(selected) > 6:
            lines.append("- ... {0} more".format(len(selected) - 6))
        self.txtSourceSummary.Text = "\n".join(lines)

    def _update_view_summary(self):
        selected = self._selected_views()
        if not selected:
            self.txtViewSummary.Text = "No host plan views selected yet."
            return

        lines = ["Checked host plan views: {0}".format(len(selected))]
        for view in selected[:6]:
            try:
                level_name = view.GenLevel.Name if hasattr(view, "GenLevel") and view.GenLevel else "No Level"
            except Exception:
                level_name = "No Level"
            lines.append("- {0} | {1}".format(level_name, safe_name(view)))
        if len(selected) > 6:
            lines.append("- ... {0} more".format(len(selected) - 6))
        self.txtViewSummary.Text = "\n".join(lines)

    def _update_output_mode_ui(self):
        mode = self._selected_output_mode()
        family_visible = mode == "family"
        tag_visible = mode == "tag"
        text_visible = mode == "text"

        for name, visible in (
            ("pnlHostFamilyType", family_visible),
            ("pnlTagType", tag_visible),
            ("pnlTextType", text_visible),
            ("pnlTextNoteContent", text_visible),
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.Visibility = Visibility.Visible if visible else Visibility.Collapsed

        self.cmbHostFamilyType.IsEnabled = family_visible
        self.cmbTagType.IsEnabled = tag_visible
        self.cmbTextType.IsEnabled = text_visible
        self.txtNoteFormat.IsEnabled = text_visible

        if mode == "family":
            message = "Family overlay will place the selected supported host family type at each linked element location, including detail items and generic annotations when those host families are loaded and view-based."
        elif mode == "tag":
            message = "Tag overlay will tag each linked element using the selected tag type when compatible."
        else:
            message = "Text-note overlay will place the exact text from Text Note Content at each linked element location using the selected text note type."
        self.txtOutputSummary.Text = message

    def _update_source_input_mode_ui(self):
        mode = self._selected_source_input_mode()
        find_visible = mode == "find"
        pick_visible = mode == "pick"

        for name, visible in (
            ("pnlFindSourceTypes", find_visible),
            ("pnlPickSourceElements", pick_visible),
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.Visibility = Visibility.Visible if visible else Visibility.Collapsed


    def _reset_analysis(self):
        self.analysis_rows = []
        self.last_summary = []
        self.txtRunSummary.Text = "No analysis has run yet."

    def _confirm(self, message, title="Confirm"):
        try:
            result = forms.alert(message, title=title, yes=True, no=True)
            if isinstance(result, bool):
                return result
            text = (str(result) if result is not None else "").strip().lower()
            return text in ("yes", "y", "true", "ok", "1")
        except Exception:
            return False

    def _source_instance_matches_view(self, source_inst, link_doc, link_inst, view,
                                       matched_link_level=None, link_transform=None):
        """Check whether source_inst should appear in view.
        Pre-computed matched_link_level and link_transform are accepted so callers
        can compute them once per view instead of once per instance.
        Returns (matches, world_point).  world_point is None only when the element
        has no locatable geometry; other rejection reasons still carry the point.
        """
        try:
            if link_inst.IsHidden(view):
                return False, None
        except Exception:
            pass

        point = get_element_point(source_inst, link_doc)
        if point is None:
            # Genuinely unlocatable element
            return False, None

        source_level_id = None
        try:
            source_level_id = source_inst.LevelId
        except Exception:
            source_level_id = None

        if matched_link_level is not None and source_level_id is not None and source_level_id != ElementId.InvalidElementId:
            if source_level_id != matched_link_level.Id:
                return False, point

        world_point = point
        if link_transform is not None:
            try:
                world_point = link_transform.OfPoint(point)
            except Exception:
                world_point = point

        if not point_in_view_crop(view, world_point):
            return False, point

        return True, world_point

    def _collect_analysis_rows(self):
        selected_types = self._selected_source_items()
        selected_views = self._selected_views()
        link_inst = self._selected_link()
        link_doc = self._selected_link_doc()

        if link_inst is None or link_doc is None:
            forms.alert("Pick source elements first to set the active linked model.")
            return []
        if not selected_types:
            forms.alert("Select at least one linked element type in Step 1.")
            return []
        if not selected_views:
            forms.alert("Select at least one host plan view in Step 2.")
            return []

        # Pre-fetch link levels and transform once — shared across all instances/views.
        link_levels = _collect_link_levels(link_doc)
        try:
            link_transform = link_inst.GetTransform()
        except Exception:
            link_transform = None

        rows = []
        skipped_unlocatable = 0
        for view in selected_views:
            # Resolve the matching link level once per view, not per instance.
            host_level = None
            try:
                if hasattr(view, "GenLevel"):
                    host_level = view.GenLevel
            except Exception:
                host_level = None
            matched_link_level = best_match_link_level(host_level, link_levels)

            for item in selected_types:
                for source_inst in self.source_instances_by_key.get(item["key"], []):
                    matches, world_point = self._source_instance_matches_view(
                        source_inst, link_doc, link_inst, view,
                        matched_link_level=matched_link_level,
                        link_transform=link_transform,
                    )
                    # world_point is None only when get_element_point could not locate the element.
                    if world_point is None:
                        skipped_unlocatable += 1
                    if not matches:
                        continue
                    rows.append(
                        {
                            "view": view,
                            "link_inst": link_inst,
                            "source": source_inst,
                            "source_item": item,
                            "world_point": world_point,
                        }
                    )
        self._last_skipped_unlocatable = skipped_unlocatable
        return rows

    def _build_analysis_summary(self, rows):
        by_view = defaultdict(int)
        by_type = defaultdict(int)
        for row in rows:
            try:
                by_view[safe_name(row["view"])] += 1
            except Exception:
                by_view["<View>"] += 1
            by_type[row["source_item"]["display"]] += 1

        lines = [
            "Analysis complete.",
            "Checked views: {0}".format(len(self._selected_views())),
            "Selected linked element types: {0}".format(len(self._selected_source_items())),
            "Matched linked instances: {0}".format(len(rows)),
        ]

        skipped_unlocatable = getattr(self, "_last_skipped_unlocatable", 0)
        if skipped_unlocatable:
            lines.append("Skipped instances without usable location: {0}".format(skipped_unlocatable))

        if by_view:
            lines.append("Views with matches:")
            for view_name in sorted(by_view.keys())[:10]:
                lines.append("- {0}: {1}".format(view_name, by_view[view_name]))
            if len(by_view) > 10:
                lines.append("- ... {0} more views".format(len(by_view) - 10))

        if by_type:
            lines.append("Source types with matches:")
            for display in sorted(by_type.keys())[:8]:
                lines.append("- {0}: {1}".format(display, by_type[display]))
            if len(by_type) > 8:
                lines.append("- ... {0} more types".format(len(by_type) - 8))

        if not rows:
            lines.append("No linked instances matched the checked views. Verify link visibility, level alignment, and the plan crop." )

        return lines

    def _points_close(self, point_a, point_b):
        if point_a is None or point_b is None:
            return False
        try:
            return point_a.DistanceTo(point_b) <= self._DUPLICATE_TOLERANCE
        except Exception:
            try:
                dx = point_a.X - point_b.X
                dy = point_a.Y - point_b.Y
                dz = point_a.Z - point_b.Z
                return (dx * dx + dy * dy + dz * dz) ** 0.5 <= self._DUPLICATE_TOLERANCE
            except Exception:
                return False

    def _existing_points_for_mode(self, mode, selected_type):
        result = defaultdict(list)

        for view in self._selected_views():
            view_id = view.Id.IntegerValue

            if mode == "family":
                try:
                    elems = FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance).WhereElementIsNotElementType().ToElements()
                except Exception:
                    elems = []
                for element in elems:
                    try:
                        if element.Symbol.Id != selected_type.Id:
                            continue
                    except Exception:
                        continue
                    point = get_element_point(element, doc)
                    if point is not None:
                        result[view_id].append((point, None))
                continue

            if mode == "text":
                try:
                    elems = FilteredElementCollector(doc, view.Id).OfClass(TextNote).WhereElementIsNotElementType().ToElements()
                except Exception:
                    elems = []
                for element in elems:
                    try:
                        if selected_type is not None and element.GetTypeId() != selected_type.Id:
                            continue
                    except Exception:
                        continue
                    point = get_element_point(element, doc)
                    if point is not None:
                        result[view_id].append((point, getattr(element, "Text", None)))
                continue

            if mode == "tag":
                try:
                    elems = FilteredElementCollector(doc, view.Id).OfClass(IndependentTag).WhereElementIsNotElementType().ToElements()
                except Exception:
                    elems = []
                for element in elems:
                    try:
                        if selected_type is not None and element.GetTypeId() != selected_type.Id:
                            continue
                    except Exception:
                        continue
                    try:
                        point = element.TagHeadPosition
                    except Exception:
                        point = None
                    if point is not None:
                        result[view_id].append((point, None))

        return result

    def _note_text_for_row(self, row):
        content = (self.txtNoteFormat.Text or "").strip()
        if content:
            return content

        source_item = row["source_item"]
        return source_item["type_name"] or source_item["category_name"] or "Linked Item"

    def _ensure_symbol_active(self, symbol):
        if symbol is None:
            return
        try:
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
        except Exception:
            pass

    def _create_family_overlay(self, row, symbol, existing_points):
        view = row["view"]
        point = row["world_point"]
        view_id = view.Id.IntegerValue

        if bool(self.chkSkipDuplicates.IsChecked):
            for existing_point, _ in existing_points.get(view_id, []):
                if self._points_close(existing_point, point):
                    return False, "duplicate"

        placement = family_placement_name(symbol)
        if "ViewBased" in placement:
            try:
                placed = doc.Create.NewFamilyInstance(point, symbol, view)
                existing_points[view_id].append((point, None))
                return True, placed
            except Exception as exc:
                return False, str(exc)

        if "OneLevelBased" in placement:
            level = None
            try:
                if hasattr(view, "GenLevel"):
                    level = view.GenLevel
            except Exception:
                level = None
            if level is None:
                return False, "view has no level for one-level-based family placement"
            try:
                placed = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
                existing_points[view_id].append((point, None))
                return True, placed
            except Exception as exc:
                return False, str(exc)

        return False, "unsupported family placement type"

    def _create_tag_overlay(self, row, tag_symbol, existing_points):
        view = row["view"]
        point = row["world_point"]
        view_id = view.Id.IntegerValue

        if bool(self.chkSkipDuplicates.IsChecked):
            for existing_point, _ in existing_points.get(view_id, []):
                if self._points_close(existing_point, point):
                    return False, "duplicate"

        try:
            reference = Reference(row["source"]).CreateLinkReference(row["link_inst"])
        except Exception as exc:
            return False, "failed to build link reference: {0}".format(exc)

        try:
            tag = IndependentTag.Create(
                doc,
                view.Id,
                reference,
                False,
                DB.TagMode.TM_ADDBY_CATEGORY,
                DB.TagOrientation.Horizontal,
                point,
            )
        except Exception as exc:
            return False, str(exc)

        if tag_symbol is not None:
            try:
                tag.ChangeTypeId(tag_symbol.Id)
            except Exception:
                pass

        existing_points[view_id].append((point, None))
        return True, tag

    def _create_text_overlay(self, row, text_type, existing_points):
        view = row["view"]
        point = row["world_point"]
        view_id = view.Id.IntegerValue
        note_text = self._note_text_for_row(row)

        if bool(self.chkSkipDuplicates.IsChecked):
            for existing_point, existing_text in existing_points.get(view_id, []):
                if existing_text == note_text and self._points_close(existing_point, point):
                    return False, "duplicate"

        try:
            options = TextNoteOptions(text_type.Id if text_type is not None else doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType))
            note = TextNote.Create(doc, view.Id, point, note_text, options)
        except Exception as exc:
            return False, str(exc)

        existing_points[view_id].append((point, note_text))
        return True, note

    def pick_source_elements_click(self, sender, e):
        link_inst = self._selected_link()
        if link_inst is None:
            forms.alert("No loaded linked models found.")
            return

        self.Hide()
        picked_refs = None
        try:
            picked_refs = uidoc.Selection.PickObjects(
                ObjectType.LinkedElement,
                "Pick linked source elements in the current view (ESC to finish)",
            )
        except Exception:
            pass
        finally:
            self.Show()

        if not picked_refs:
            return

        selected_link_id = None
        try:
            selected_link_id = link_inst.Id.IntegerValue
        except Exception:
            selected_link_id = None

        chosen_keys_by_link = defaultdict(set)
        skipped_not_in_selected_link = 0
        skipped_unusable = 0

        for picked in picked_refs:
            if picked is None:
                continue

            try:
                picked_link = doc.GetElement(picked.ElementId)
            except Exception:
                picked_link = None
            if picked_link is None:
                continue

            try:
                link_doc = picked_link.GetLinkDocument()
                linked_id = getattr(picked, "LinkedElementId", ElementId.InvalidElementId)
                if link_doc is not None and linked_id and linked_id != ElementId.InvalidElementId:
                    linked_element = link_doc.GetElement(linked_id)
                else:
                    linked_element = None
            except Exception:
                linked_element = None

            descriptor = get_source_descriptor(linked_element, link_doc) if linked_element is not None else None
            if descriptor is None:
                skipped_unusable += 1
                continue

            try:
                picked_link_id = picked_link.Id.IntegerValue
            except Exception:
                picked_link_id = None
            if picked_link_id is None:
                skipped_unusable += 1
                continue

            chosen_keys_by_link[picked_link_id].add(descriptor["key"])

        if not chosen_keys_by_link:
            lines = ["No usable linked elements were selected for the current link model."]
            if skipped_unusable:
                lines.append("Picked elements missing usable category/type metadata: {0}".format(skipped_unusable))
            forms.alert("\n".join(lines), title="Linked Type Overlay")
            return

        chosen_link_id = selected_link_id
        if chosen_link_id not in chosen_keys_by_link:
            chosen_link_id = max(chosen_keys_by_link.keys(), key=lambda k: len(chosen_keys_by_link[k]))
            switched = self._set_selected_link_by_id(chosen_link_id)
            if switched:
                self._refresh_source_types()
        else:
            self._set_selected_link_by_id(chosen_link_id)

        available_keys = set(item["key"] for item in self.source_type_items)
        chosen_keys = set()
        for key in chosen_keys_by_link.get(chosen_link_id, set()):
            if key in available_keys:
                chosen_keys.add(key)
            else:
                skipped_not_in_selected_link += 1

        if not chosen_keys:
            lines = ["Picked linked elements could not be matched to the selected link model type list."]
            if skipped_not_in_selected_link:
                lines.append("Not found in selected link model list: {0}".format(skipped_not_in_selected_link))
            if skipped_unusable:
                lines.append("Picked elements missing usable category/type metadata: {0}".format(skipped_unusable))
            forms.alert("\n".join(lines), title="Linked Type Overlay")
            return

        selected_count = self._set_selected_source_keys(chosen_keys)
        lines = ["Selected linked element types from current view: {0}".format(selected_count)]
        if skipped_not_in_selected_link:
            lines.append("Ignored picks not present in selected link model list: {0}".format(skipped_not_in_selected_link))
        if skipped_unusable:
            lines.append("Ignored linked picks with no usable category/type metadata: {0}".format(skipped_unusable))
        forms.alert("\n".join(lines), title="Linked Type Overlay")

    def source_search_changed(self, sender, e):
        self._refresh_source_list(self.txtSourceSearch.Text)

    def source_input_mode_changed(self, sender, e):
        self._update_source_input_mode_ui()

    def view_search_changed(self, sender, e):
        self._refresh_view_list(self.txtViewSearch.Text)

    def source_selection_changed(self, sender, e):
        self._update_source_summary()
        self._reset_analysis()

    def view_selection_changed(self, sender, e):
        self._update_view_summary()
        self._reset_analysis()

    def output_mode_changed(self, sender, e):
        self._update_output_mode_ui()

    def refresh_source_types_click(self, sender, e):
        self._refresh_source_types()

    def select_all_source_types_click(self, sender, e):
        for item in self.visible_source_items:
            item["cb"].IsChecked = True
        self._update_source_summary()
        self._reset_analysis()

    def deselect_all_source_types_click(self, sender, e):
        for item in self.source_type_items:
            item["cb"].IsChecked = False
        self._update_source_summary()
        self._reset_analysis()

    def select_all_views_click(self, sender, e):
        for item in self.visible_view_items:
            item["cb"].IsChecked = True
        self._update_view_summary()
        self._reset_analysis()

    def deselect_all_views_click(self, sender, e):
        for item in self.view_items:
            item["cb"].IsChecked = False
        self._update_view_summary()
        self._reset_analysis()

    def use_active_view_click(self, sender, e):
        if not self._set_active_view_only():
            forms.alert("The active Revit view is not a plan view that this tool can use.")
            return

        self._update_view_summary()
        self._reset_analysis()

    def apply_view_option_click(self, sender, e):
        selected_item = getattr(self.cmbQuickViewMode, "SelectedItem", None)
        selected_text = ""
        try:
            selected_text = str(selected_item.Content) if hasattr(selected_item, "Content") else str(selected_item)
        except Exception:
            selected_text = ""

        if "active" in selected_text.lower():
            self.use_active_view_click(sender, e)
            return

        self._update_view_summary()
        self._reset_analysis()
        forms.alert(
            "Current checked view set kept as-is. Use the list or Active button to change it.",
            title="Linked Type Overlay",
        )

    def analyze_click(self, sender, e):
        rows = self._collect_analysis_rows()
        self.analysis_rows = rows
        summary = self._build_analysis_summary(rows)
        self.last_summary = list(summary)
        self.txtRunSummary.Text = "\n".join(summary)

    def create_overlay_click(self, sender, e):
        if bool(self.chkAnalyzeBeforeCreate.IsChecked) or not self.analysis_rows:
            self.analyze_click(sender, e)
        if not self.analysis_rows:
            forms.alert("No linked instances matched the checked views. Nothing was created.")
            return

        mode = self._selected_output_mode()
        output_type = None
        if mode == "family":
            output_type = self._selected_host_symbol()
            if output_type is None:
                forms.alert("Choose a supported host family type in Step 3.")
                return
        elif mode == "tag":
            output_type = self._selected_tag_symbol()
        else:
            output_type = self._selected_text_type()
            if output_type is None:
                forms.alert("Choose a text note type in Step 3.")
                return

        if len(self.analysis_rows) > 1200:
            if not self._confirm(
                "Creating overlay objects for {0} linked instances may take a while. Continue?".format(len(self.analysis_rows)),
                title="Large Overlay Run",
            ):
                return

        skip_dupes = bool(self.chkSkipDuplicates.IsChecked)
        existing_points = self._existing_points_for_mode(mode, output_type) if skip_dupes else {}
        created = 0
        skipped_duplicates = 0
        failed = 0
        fail_messages = []

        # Activate the output symbol once before the transaction loop.
        if mode == "family" and output_type is not None:
            self._ensure_symbol_active(output_type)

        tx = Transaction(doc, "Linked Type Overlay")
        tx.Start()
        try:
            for row in self.analysis_rows:
                if mode == "family":
                    ok, result = self._create_family_overlay(row, output_type, existing_points)
                elif mode == "tag":
                    ok, result = self._create_tag_overlay(row, output_type, existing_points)
                else:
                    ok, result = self._create_text_overlay(row, output_type, existing_points)

                if ok:
                    created += 1
                    continue

                if result == "duplicate":
                    skipped_duplicates += 1
                    continue

                failed += 1
                if len(fail_messages) < 10:
                    try:
                        fail_messages.append(
                            "{0} | {1}: {2}".format(
                                safe_name(row["view"]),
                                row["source_item"]["display"],
                                result,
                            )
                        )
                    except Exception:
                        fail_messages.append(str(result))

            tx.Commit()
        except Exception as exc:
            tx.RollBack()
            forms.alert("Overlay creation failed and the transaction was rolled back:\n{0}".format(exc))
            return

        summary = [
            "Overlay Summary",
            "Mode: {0}".format(mode.title()),
            "Checked views: {0}".format(len(self._selected_views())),
            "Selected linked element types: {0}".format(len(self._selected_source_items())),
            "Analyzed linked instances: {0}".format(len(self.analysis_rows)),
            "Created objects: {0}".format(created),
            "Skipped nearby duplicates: {0}".format(skipped_duplicates),
            "Failures: {0}".format(failed),
        ]

        if fail_messages:
            summary.append("Sample failures:")
            summary.extend("- {0}".format(message) for message in fail_messages)

        log_path = write_log(summary, "LinkedTypeOverlay")
        summary.append("Log file: {0}".format(log_path))
        self.last_summary = list(summary)
        self.txtRunSummary.Text = "\n".join(summary)
        forms.alert("\n".join(summary), title="Linked Type Overlay")

    def cancel_click(self, sender, e):
        self.Close()


try:
    ui = LinkedTypeOverlayWindow("WPFWindow.xaml")
    if getattr(ui, "links", None):
        ui.ShowDialog()
except Exception as ex:
    logger.exception("Linked Type Overlay failed")
    forms.alert("Linked Type Overlay failed to open:\n{0}".format(ex))