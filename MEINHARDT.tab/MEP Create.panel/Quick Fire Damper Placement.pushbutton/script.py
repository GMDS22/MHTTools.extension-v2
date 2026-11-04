# -*- coding: utf-8 -*-
"""Place selected duct damper families at explicitly rated wall crossings."""

import clr
import codecs
import os
import json
import sys
import time
import traceback

clr.AddReference("System")
clr.AddReference("WindowsBase")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")

from Autodesk.Revit.DB import (
    BuiltInCategory, FilteredElementCollector, Transaction,
    Options, SolidCurveIntersectionMode, SolidCurveIntersectionOptions, SolidUtils, Transform
)
from Autodesk.Revit.DB.Structure import StructuralType as RevitStructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import DB, forms, revit, script
from pyrevitmep.event import CustomizableEvent
from System import Action
from System.Collections.Generic import List
from System.Windows.Threading import DispatcherPriority

TOOL_VERSION = "1.1"
DUPLICATE_CROSSING_TOLERANCE = 0.0164042
THIS_DIR = os.path.dirname(__file__)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
from wall_classification import is_rated_wall_material

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

STATE_PATH = os.path.join(os.path.dirname(doc.PathName) if doc and doc.PathName else os.path.expanduser("~"), "MHT_QuickDamperState.json") if doc else None
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MHTTools", "Logs")
LOG_PATH = os.path.join(LOG_DIR, "QuickFireDamper.log")


def _write_log(message):
    try:
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        try:
            text = unicode(message)
        except NameError:
            text = str(message)
        with codecs.open(LOG_PATH, "a", "utf-8") as handle:
            handle.write(u"{} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def _write_exception(context):
    _write_log("{}\n{}".format(context, traceback.format_exc()))


def _element_id(element):
    try:
        return str(element.Id.IntegerValue)
    except Exception:
        return str(element.Id)


def _param_text(element, name):
    params = []
    try:
        param = element.LookupParameter(name)
        if param:
            params.append(param)
    except Exception:
        pass
    try:
        element_document = getattr(element, "Document", None) or doc
        element_type = element_document.GetElement(element.GetTypeId()) if hasattr(element, "GetTypeId") else None
        type_param = element_type.LookupParameter(name) if element_type else None
        if type_param:
            params.append(type_param)
    except Exception:
        pass
    for param in params:
        try:
            value = param.AsValueString() or param.AsString()
            if value:
                return value.strip()
            if param.StorageType == DB.StorageType.Integer:
                value = str(param.AsInteger())
                if value:
                    return value
        except Exception:
            continue
    return ""


def _is_rated_wall(wall):
    value = (_param_text(wall, "NWB_Material") + " " + _param_text(wall, "NWB_MATERIAL")).lower()
    return is_rated_wall_material(value)


def _wall_type_key(wall):
    try:
        wall_document = wall.Document
    except Exception:
        wall_document = doc
    try:
        wall_type = wall_document.GetElement(wall.GetTypeId())
    except Exception:
        wall_type = None
    if wall_type is None:
        return ""
    try:
        name_param = wall_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if name_param:
            value = name_param.AsString() or name_param.AsValueString()
            if value:
                return value.strip()
    except Exception:
        pass
    try:
        value = wall_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if value:
            value = value.AsString() or value.AsValueString()
            if value:
                return value.strip()
    except Exception:
        pass
    try:
        return str(wall_type.Id.IntegerValue)
    except Exception:
        return ""


def _wall_family_name(wall):
    try:
        wall_document = wall.Document
    except Exception:
        wall_document = doc
    try:
        wall_type = wall_document.GetElement(wall.GetTypeId())
    except Exception:
        wall_type = None
    if wall_type is not None:
        try:
            family_name = wall_type.FamilyName
            if family_name and str(family_name).strip():
                return str(family_name).strip()
        except Exception:
            pass
    return _wall_type_key(wall)


def _family_category_id(family):
    try:
        category_id = family.FamilyCategoryId
        return category_id.IntegerValue
    except Exception:
        pass
    try:
        return family.FamilyCategory.Id.IntegerValue
    except Exception:
        return -1


def _wall_type_description(wall_type):
    if wall_type is None:
        return ""
    for built_in_name in ("ALL_MODEL_DESCRIPTION", "ALL_MODEL_TYPE_COMMENTS"):
        try:
            built_in = getattr(DB.BuiltInParameter, built_in_name)
            param = wall_type.get_Parameter(built_in)
            if param:
                value = param.AsString() or param.AsValueString()
                if value and value.strip():
                    return value.strip()
        except Exception:
            pass
    for param_name in ("Description", "Type Comments", "Comments"):
        try:
            param = wall_type.LookupParameter(param_name)
            if param:
                value = param.AsString() or param.AsValueString()
                if value and value.strip():
                    return value.strip()
        except Exception:
            pass
    return ""


def _safe_element_name(element, fallback=""):
    try:
        value = element.Name
        if value:
            return str(value)
    except Exception:
        pass
    for param_name in ("SYMBOL_NAME_PARAM", "ALL_MODEL_TYPE_NAME", "Family Name"):
        try:
            param = element.get_Parameter(getattr(DB.BuiltInParameter, param_name)) if hasattr(DB.BuiltInParameter, param_name) else element.LookupParameter(param_name)
            if param:
                value = param.AsString() or param.AsValueString()
                if value:
                    return str(value).strip()
        except Exception:
            pass
    try:
        return str(element.Id.IntegerValue)
    except Exception:
        return fallback


def _safe_family_name(family):
    try:
        value = family.Name
        if value:
            return str(value)
    except Exception:
        pass
    return _safe_element_name(family, "Unnamed Family")


class WallFamilyItem(object):
    def __init__(self, key, family_name, type_keys, type_names, sources, wall_count):
        self.Key = key
        self.Name = family_name
        self.TypeKeys = set(type_keys)
        self.TypeNames = sorted(type_names, key=lambda value: value.lower())
        self.TypeCount = len(self.TypeNames)
        self.Sources = set(sources)
        self.WallCount = wall_count
        source_label = "host + linked" if len(self.Sources) > 1 else ("linked" if "linked" in self.Sources else "host")
        self.DisplayName = "{} ({} rated types, {} walls, {})".format(family_name, self.TypeCount, wall_count, source_label)


class _DuctSelectionFilter(ISelectionFilter):
    def __init__(self, allowed_ids):
        self.allowed_ids = set(allowed_ids or [])

    def AllowElement(self, element):
        try:
            return (
                element.Category is not None
                and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_DuctCurves)
                and _element_id(element) in self.allowed_ids
            )
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return False


class FamilyItem(object):
    def __init__(self, family):
        self.Family = family
        self.Name = _safe_family_name(family)


class SymbolItem(object):
    def __init__(self, symbol):
        self.Symbol = symbol
        self.Name = _safe_element_name(symbol, "Unnamed Type")


class QuickDamperWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(THIS_DIR, "QuickFireDamper.xaml"))
        self._revit_event = CustomizableEvent()
        self._utility_event = CustomizableEvent()
        self._utility_action_running = False
        self._revit_event.logger = logger
        self._utility_event.logger = logger
        _write_log("Window initialized for document '{}'".format(doc.Title if doc else "<none>"))
        self.wall_families = []
        self.families = []
        self._symbols_by_family = {}
        self._wall_records = []
        self._wall_solids = []
        self._wall_prepare_index = 0
        self._picked_duct_ids = []
        self._picked_view_id = doc.ActiveView.Id if doc else None
        self.cancelled = False
        self._placement_running = False
        self.cancel_button.Click += self._cancel
        self.Closing += self._on_closing
        self.place_button.Click += self._place
        self.family_box.SelectionChanged += self._family_changed
        self.refresh_button.Click += self._refresh_wall_types_click
        self.select_ducts_button.Click += self._select_active_view_ducts
        self.clear_ducts_button.Click += self._clear_duct_targets
        self._capture_initial_duct_selection()
        self._load_families()
        self._refresh_wall_types()
        self._restore_state()
        _write_log("Initial UI population complete: {} damper families, {} rated wall families".format(len(self.families), len(self.wall_families)))

    def _select_active_view_ducts(self, sender, args):
        self._queue_utility_action(self._pick_active_view_ducts_api)

    def _capture_initial_duct_selection(self):
        try:
            selected_ids = set(str(element_id.IntegerValue) for element_id in uidoc.Selection.GetElementIds())
            active_duct_ids = set(_element_id(duct) for duct in self._active_view_ducts())
            self._picked_duct_ids = sorted(selected_ids.intersection(active_duct_ids))
        except Exception:
            _write_exception("Could not read the initial Revit duct selection")
            self._picked_duct_ids = []
        if self._picked_duct_ids:
            self.status_text.Text = "{} selected duct targets".format(len(self._picked_duct_ids))
        else:
            self.status_text.Text = "Select duct targets before placement"
        self.place_button.IsEnabled = bool(self._picked_duct_ids)

    def _clear_duct_targets(self, sender, args):
        if self._utility_action_running or self._placement_running:
            return
        self._picked_duct_ids = []
        self._picked_view_id = doc.ActiveView.Id
        self.status_text.Text = "No duct targets selected"
        self.place_button.IsEnabled = False

    def _pick_active_view_ducts_api(self):
        picked_ids = []
        previous_ids = list(self._picked_duct_ids or [])
        self.Hide()
        try:
            ducts = self._active_view_ducts()
            allowed_ids = set(_element_id(duct) for duct in ducts)
            if not allowed_ids:
                self.status_text.Text = "No ducts in active view"
                forms.alert("No ducts were found in the active view.", exitscript=False)
                return
            references = uidoc.Selection.PickObjects(
                ObjectType.Element,
                _DuctSelectionFilter(allowed_ids),
                "Pick one or more ducts in the active view, then click Finish.",
            )
            for reference in references or []:
                try:
                    element_id = str(reference.ElementId.IntegerValue)
                except Exception:
                    element_id = str(reference.ElementId)
                if element_id in allowed_ids and element_id not in picked_ids:
                    picked_ids.append(element_id)
            if picked_ids:
                self._picked_duct_ids = picked_ids
                self._picked_view_id = doc.ActiveView.Id
                self.status_text.Text = "{} selected duct targets".format(len(picked_ids))
                self.place_button.IsEnabled = True
                _write_log("User picked {} ducts from active view '{}'".format(len(picked_ids), doc.ActiveView.Name))
            else:
                self.status_text.Text = "No new ducts picked; {} existing targets kept".format(len(previous_ids))
                _write_log("Duct pick completed with no elements; retained {} prior targets".format(len(previous_ids)))
        except OperationCanceledException:
            self.status_text.Text = "Duct pick cancelled; {} existing targets kept".format(len(previous_ids))
            _write_log("Duct pick cancelled; retained {} prior picks".format(len(previous_ids or [])))
        except Exception as exc:
            _write_exception("Interactive duct pick failed")
            forms.alert("Could not pick ducts: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
        finally:
            self.Show()
            self.Activate()
            self._finish_utility_action()

    def _active_view_ducts(self, view_id=None):
        target_view_id = view_id if view_id is not None else doc.ActiveView.Id
        return list(FilteredElementCollector(doc, target_view_id).OfCategory(BuiltInCategory.OST_DuctCurves).WhereElementIsNotElementType().ToElements())

    def _refresh_wall_types_click(self, sender, args):
        self._queue_utility_action(self._refresh_wall_types_api)

    def _refresh_wall_types_api(self):
        try:
            self._refresh_wall_types()
        except Exception as exc:
            _write_exception("Rated wall family refresh failed")
            forms.alert("Could not refresh wall families: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
        finally:
            self._finish_utility_action()

    def _queue_utility_action(self, action):
        if self._utility_action_running or self._placement_running:
            return
        self._utility_action_running = True
        self.select_ducts_button.IsEnabled = False
        self.clear_ducts_button.IsEnabled = False
        self.refresh_button.IsEnabled = False
        self.place_button.IsEnabled = False
        try:
            self._utility_event.raise_event(action)
        except Exception as exc:
            _write_exception("Could not queue modeless utility action")
            self._finish_utility_action()
            forms.alert("Could not complete the requested action: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)

    def _finish_utility_action(self):
        self._utility_action_running = False
        self.select_ducts_button.IsEnabled = True
        self.clear_ducts_button.IsEnabled = True
        self.refresh_button.IsEnabled = True
        self.place_button.IsEnabled = bool(self._picked_duct_ids)

    def _cancel(self, sender, args):
        if self._utility_action_running:
            self.status_text.Text = "Please wait for the Revit selection/refresh to finish."
            return
        self.cancelled = True
        if not getattr(self, "_placement_running", False):
            self.Close()
        else:
            self.progress_text.Text = "Cancelling... completed items will be kept"
            self.cancel_button.IsEnabled = False

    def _on_closing(self, sender, args):
        if self._utility_action_running:
            args.Cancel = True
            return
        if getattr(self, "_placement_running", False):
            self.cancelled = True
            self.progress_text.Text = "Cancelling... completed items will be kept"
            args.Cancel = True

    def _load_families(self):
        damper_families = []
        collector = FilteredElementCollector(doc).OfClass(DB.Family)
        for family in collector:
            try:
                if _family_category_id(family) == int(BuiltInCategory.OST_DuctAccessory):
                    damper_families.append(family)
            except Exception:
                pass
        damper_families.sort(key=lambda f: _safe_family_name(f).lower())
        self.families = damper_families
        self._symbols_by_family = {}
        for family in damper_families:
            symbol_items = []
            try:
                for symbol_id in family.GetFamilySymbolIds():
                    symbol = doc.GetElement(symbol_id)
                    if symbol:
                        symbol_items.append(SymbolItem(symbol))
            except Exception:
                _write_exception("Could not cache symbols for duct accessory family '{}'".format(_safe_family_name(family)))
            symbol_items.sort(key=lambda item: item.Name.lower())
            self._symbols_by_family[_element_id(family)] = symbol_items
        self.family_box.ItemsSource = [FamilyItem(f) for f in damper_families]
        _write_log("Loaded {} duct accessory families".format(len(damper_families)))
        if not damper_families:
            _write_log("WARNING: no Duct Accessory families were found in the active document")
        if damper_families:
            self.family_box.SelectedIndex = 0

    def _family_changed(self, sender, args):
        self._populate_family_symbols()

    def _populate_family_symbols(self):
        selected = self.family_box.SelectedItem
        if selected is None:
            self.symbol_box.ItemsSource = None
            return
        symbols = self._symbols_by_family.get(_element_id(selected.Family), [])
        self.symbol_box.ItemsSource = symbols
        _write_log("Family '{}' has {} symbols".format(selected.Name, len(symbols)))
        if not symbols:
            _write_log("WARNING: selected family has no loadable symbols")
        if symbols:
            self.symbol_box.SelectedIndex = 0

    def _bounding_box_bounds(self, bounding_box, transform=None):
        if bounding_box is None:
            return None
        points = []
        for x in (bounding_box.Min.X, bounding_box.Max.X):
            for y in (bounding_box.Min.Y, bounding_box.Max.Y):
                for z in (bounding_box.Min.Z, bounding_box.Max.Z):
                    point = DB.XYZ(x, y, z)
                    points.append(transform.OfPoint(point) if transform is not None else point)
        return (
            (min(point.X for point in points), min(point.Y for point in points), min(point.Z for point in points)),
            (max(point.X for point in points), max(point.Y for point in points), max(point.Z for point in points)),
        )

    def _active_crop_bounds(self, view):
        try:
            if not view.CropBoxActive:
                return None
            crop_box = view.CropBox
            return self._bounding_box_bounds(crop_box, crop_box.Transform)
        except Exception:
            _write_exception("Could not read active view crop extents; view-scoped link collection remains in effect")
            return None

    def _bounds_overlap(self, first, second, horizontal_only=False):
        if not first or not second:
            return False
        axes = (0, 1) if horizontal_only else range(3)
        for axis in axes:
            if first[1][axis] < second[0][axis] or second[1][axis] < first[0][axis]:
                return False
        return True

    def _linked_architecture_walls(self, view_id=None):
        records = []
        target_view_id = view_id if view_id is not None else doc.ActiveView.Id
        target_view = doc.GetElement(target_view_id)
        crop_bounds = self._active_crop_bounds(target_view)
        try:
            horizontal_view = abs(target_view.ViewDirection.Z) > 0.9
        except Exception:
            horizontal_view = False
        links = FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements()
        _write_log("Checking {} Revit link instances for walls".format(len(links)))
        for link in links:
            try:
                if link.IsHidden(target_view):
                    continue
                linked_doc = link.GetLinkDocument()
                if not linked_doc:
                    continue
                transform = link.GetTotalTransform() if hasattr(link, "GetTotalTransform") else link.GetTransform()
                walls = FilteredElementCollector(doc, target_view_id, link.Id).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
                for wall in walls:
                    if crop_bounds is not None:
                        try:
                            wall_bounds = self._bounding_box_bounds(wall.get_BoundingBox(None), transform)
                        except Exception:
                            wall_bounds = None
                        if not self._bounds_overlap(wall_bounds, crop_bounds, horizontal_view):
                            _write_log("Skipped linked wall {} from '{}': outside active view crop or has no bounding box".format(_element_id(wall), linked_doc.Title))
                            continue
                    records.append((wall, transform, linked_doc.Title))
            except Exception:
                _write_exception("Linked wall collection failed for link '{}'".format(getattr(link, "Name", "<unknown>")))
                logger.debug("Link wall collection skipped")
        _write_log("Collected {} walls from loaded, visible links".format(len(records)))
        return records

    def _refresh_wall_types(self, view_id=None):
        family_groups = {}
        self._wall_records = []
        target_view_id = view_id if view_id is not None else doc.ActiveView.Id
        host_walls = FilteredElementCollector(doc, target_view_id).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
        host_rated = 0

        def add_rated_wall(wall, transform, source_name, source_model=None, placement_candidate=True):
            family_name = _wall_family_name(wall)
            family_key = family_name.strip().lower()
            if not family_key:
                return
            type_key = _wall_type_key(wall)
            wall_document = getattr(wall, "Document", None)
            model_name = source_model or getattr(wall_document, "Title", "Host model")
            type_label = "{} [{}]".format(type_key, model_name) if source_name == "linked" else type_key
            group = family_groups.setdefault(family_key, {"name": family_name, "types": set(), "type_names": set(), "sources": set(), "wall_ids": set()})
            if type_key:
                group["types"].add(type_key)
                group["type_names"].add(type_label)
            group["sources"].add(source_name)
            try:
                wall_identity = "{}:{}".format(model_name, wall.UniqueId)
            except Exception:
                wall_identity = "{}:{}".format(model_name, _element_id(wall))
            group["wall_ids"].add(wall_identity)
            if placement_candidate:
                self._wall_records.append((wall, transform, source_name))

        for wall in host_walls:
            if _is_rated_wall(wall):
                host_rated += 1
                add_rated_wall(wall, Transform.Identity, "host")

        for wall, transform, source_name in self._linked_architecture_walls(target_view_id):
            if _is_rated_wall(wall):
                add_rated_wall(wall, transform, "linked", source_name)

        self.wall_families = []
        for family_key in sorted(family_groups):
            group = family_groups[family_key]
            self.wall_families.append(WallFamilyItem(family_key, group["name"], group["types"], group["type_names"], group["sources"], len(group["wall_ids"])))
        self.wall_families_box.ItemsSource = self.wall_families
        rated_type_count = sum(item.TypeCount for item in self.wall_families)
        self.status_text.Text = "{} families | {} rated types | {} in-view walls".format(len(self.wall_families), rated_type_count, len(self._wall_records))
        _write_log("Wall inventory: {} host-view walls / {} rated; {} rated types; {} families; {} in-view host/link placement records".format(len(host_walls), host_rated, rated_type_count, len(self.wall_families), len(self._wall_records)))
        for item in self.wall_families:
            _write_log("Wall family choice '{}': {} types | {} walls | {}".format(item.Name, item.TypeCount, item.WallCount, "; ".join(item.TypeNames)))
        if not self.wall_families:
            _write_log("WARNING: no explicitly rated walls found; check NWB_Material/NWB_MATERIAL values and active view/link visibility")

    def _state_key(self):
        title = doc.Title.replace("/", "-").replace("\\", "-") if doc else "NoDocument"
        return os.path.abspath(STATE_PATH or os.path.join(os.path.expanduser("~"), "MHT_QuickDamperState.json"))

    def _load_state(self):
        try:
            with open(self._state_key(), "r") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _save_state(self):
        state = self._load_state()
        state[doc.Title if doc else "document"] = {
            "family": getattr(self.family_box.SelectedItem, "Name", ""),
            "symbol": getattr(self.symbol_box.SelectedItem.Symbol, "Name", "") if self.symbol_box.SelectedItem else "",
        }
        try:
            with open(self._state_key(), "w") as handle:
                json.dump(state, handle, indent=2)
        except Exception as exc:
            logger.warning("Could not save quick damper state: {}".format(exc))

    def _restore_state(self):
        state = self._load_state().get(doc.Title if doc else "document", {})
        if state.get("family"):
            for index, family in enumerate(self.family_box.ItemsSource or []):
                if family.Name == state["family"]:
                    self.family_box.SelectedIndex = index
                    break
        if state.get("symbol"):
            for index, symbol in enumerate(self.symbol_box.ItemsSource or []):
                if symbol.Name == state["symbol"]:
                    self.symbol_box.SelectedIndex = index
                    break
    def _point_distance(self, a, b):
        return a.DistanceTo(b)

    def _duct_length_point(self, duct):
        location = duct.Location
        curve = getattr(location, "Curve", None)
        if curve is None:
            return None
        try:
            start = curve.GetEndPoint(0)
            end = curve.GetEndPoint(1)
            return start.Add(end.Subtract(start).Multiply(0.5))
        except Exception:
            return None

    def _geometry_solids(self, element):
        result = []
        try:
            geometry = element.get_Geometry(Options())
            for obj in geometry:
                if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                    result.append(obj)
                elif isinstance(obj, DB.GeometryInstance):
                    for solid in obj.GetInstanceGeometry():
                        if isinstance(solid, DB.Solid) and solid.Volume > 1e-9:
                            result.append(solid)
        except Exception:
            _write_exception("Geometry extraction failed for element {}".format(_element_id(element)))
        if not result:
            _write_log("WARNING: element {} returned no solid geometry".format(_element_id(element)))
        return result

    def _prepare_wall_solids(self):
        total = len(self._wall_records)
        if self.cancelled:
            self._finish_placement("Cancelled")
            return
        end_index = min(self._wall_prepare_index + 10, total)
        while self._wall_prepare_index < end_index:
            index = self._wall_prepare_index
            wall, transform, source = self._wall_records[index]
            self._wall_prepare_index += 1
            self.progress_text.Text = "Preparing rated wall geometry {}/{}...".format(self._wall_prepare_index, total)
            for wall_solid in self._geometry_solids(wall):
                transformed = wall_solid
                if transform is not None and transform != Transform.Identity:
                    try:
                        transformed = SolidUtils.CreateTransformed(wall_solid, transform)
                    except Exception:
                        _write_exception("Could not transform linked wall {} from '{}'".format(_element_id(wall), source))
                        continue
                self._wall_solids.append((transformed, wall, source))
        if self._wall_prepare_index < total:
            self._schedule_placement_callback(self._prepare_wall_solids, "Could not continue rated wall geometry preparation")
            return
        if not self._wall_solids:
            self._finish_placement("Failed", "Rated walls were found, but their geometry could not be read. Check the wall geometry and linked model visibility.")
            return
        self._schedule_placement_callback(self._collect_placement_targets, "Could not continue selected duct preparation")

    def _schedule_placement_callback(self, callback, error_context):
        try:
            continuation = Action(lambda: self._revit_event.raise_event(callback))
            self.Dispatcher.BeginInvoke(continuation, DispatcherPriority.Background)
            return True
        except Exception as exc:
            _write_exception(error_context)
            self._finish_placement("Failed", "Could not continue placement: {}".format(exc))
            return False

    def _clash_points(self, duct):
        location = getattr(duct.Location, "Curve", None)
        if location is None:
            _write_log("Duct {} cannot be tested: curve location is missing".format(_element_id(duct)))
            return []
        crossings = []
        tested_walls = len(self._wall_records)
        intersection_options = SolidCurveIntersectionOptions()
        intersection_options.ResultType = SolidCurveIntersectionMode.CurveSegmentsInside
        for wall_solid, wall, source in self._wall_solids:
            key = _wall_type_key(wall)
            try:
                intersections = wall_solid.IntersectWithCurve(location, intersection_options)
                for segment_index in range(intersections.SegmentCount):
                    segment = intersections.GetCurveSegment(segment_index)
                    point = segment.Evaluate(0.5, True)
                    if any(point.DistanceTo(existing[0]) <= 0.01 for existing in crossings):
                        continue
                    crossings.append((point, wall, source))
                    _write_log("CLASH: duct {} with wall type '{}' from '{}' at ({:.3f}, {:.3f}, {:.3f})".format(_element_id(duct), key, source, point.X, point.Y, point.Z))
            except Exception:
                _write_exception("Curve/solid intersection failed for duct {} and wall {}".format(_element_id(duct), _element_id(wall)))
        def _curve_parameter(hit):
            try:
                projection = location.Project(hit[0])
                return projection.Parameter if projection else 0.0
            except Exception:
                return 0.0

        crossings.sort(key=_curve_parameter)
        _write_log("Duct {}: {} distinct crossing(s) across {} selected rated wall records".format(_element_id(duct), len(crossings), tested_walls))
        return crossings

    def _place(self, sender, args):
        if not self._picked_duct_ids:
            forms.alert("Select one or more duct targets before placing dampers.", exitscript=False)
            return
        if self.family_box.SelectedItem is None or self.symbol_box.SelectedItem is None:
            _write_log("Placement aborted: no family or symbol selected")
            forms.alert("Select a damper family and symbol.", exitscript=False)
            return
        self._placement_symbol = self.symbol_box.SelectedItem.Symbol
        self._placement_symbol_name = self.symbol_box.SelectedItem.Name
        self._placement_family_name = self.family_box.SelectedItem.Name
        self._placement_counts = {"placed": 0, "skipped": 0, "duplicate": 0, "crossings": 0}
        self._placement_errors = []
        self._placed_elements = []
        self._isolation_ids = []
        self._placement_view_id = None
        self._placement_running = True
        self.cancelled = False
        self.cancel_button.IsEnabled = True
        self.place_button.IsEnabled = False
        for control in (self.family_box, self.symbol_box, self.wall_families_box, self.refresh_button, self.select_ducts_button, self.clear_ducts_button):
            control.IsEnabled = False
        self.progress_bar.Value = 0
        self.progress_text.Text = "Starting..."
        _write_log("=" * 72)
        try:
            self._revit_event.raise_event(self._begin_placement)
        except Exception as exc:
            _write_exception("Could not queue placement ExternalEvent")
            self._finish_placement("Failed", "Could not start placement: {}".format(exc))

    def _begin_placement(self):
        try:
            if self.cancelled:
                self._finish_placement("Cancelled")
                return
            self._placement_counts = {"placed": 0, "skipped": 0, "duplicate": 0, "crossings": 0}
            self._placement_errors = []
            self._placed_elements = []
            self._isolation_ids = []
            self._placement_view_id = doc.ActiveView.Id
            if self._picked_view_id is None or self._picked_view_id != self._placement_view_id:
                self._finish_placement("Failed", "The active view changed after duct selection. Select the duct targets again in the current view.")
                return
            self._save_state()
            self.progress_text.Text = "Scanning rated walls in the active view and linked models..."
            self._refresh_wall_types(self._placement_view_id)
            if not self._wall_records:
                self._finish_placement("Failed", "No explicitly rated walls were found in this view. Check the NWB_Material value and linked model visibility.")
                return
            self._wall_solids = []
            self._wall_prepare_index = 0
            self._prepare_wall_solids()
        except Exception as exc:
            _write_exception("Could not initialize placement run")
            self._finish_placement("Failed", "Placement initialization failed: {}".format(exc))

    def _collect_placement_targets(self):
        try:
            if self.cancelled:
                self._finish_placement("Cancelled")
                return
            self.progress_text.Text = "Collecting selected duct targets..."
            self._placement_ducts = self._active_view_ducts(self._placement_view_id)
            picked_ids = set(self._picked_duct_ids)
            self._placement_ducts = [duct for duct in self._placement_ducts if _element_id(duct) in picked_ids]
            if len(self._placement_ducts) != len(picked_ids):
                self._finish_placement("Failed", "One or more selected duct targets are no longer available in this view. Select the targets again before placement.")
                return
            self._placement_index = 0
            self._existing_points = []
            symbol_id = self._placement_symbol.Id
            accessories = FilteredElementCollector(doc, self._placement_view_id).OfCategory(BuiltInCategory.OST_DuctAccessory).WhereElementIsNotElementType().ToElements()
            for accessory in accessories:
                try:
                    location = accessory.Location
                    if accessory.Symbol.Id == symbol_id and hasattr(location, "Point"):
                        self._existing_points.append(location.Point)
                except Exception:
                    continue
            _write_log("PLACEMENT START: document='{}', view='{}', family='{}', type='{}'".format(doc.Title, doc.ActiveView.Name, self._placement_family_name, self._placement_symbol_name))
            _write_log("Auto-detected rated wall families: {}".format(", ".join(item.Key for item in self.wall_families)))
            _write_log("Candidate wall records: {}; selected duct targets: {}; matching existing symbols: {}".format(len(self._wall_records), len(self._placement_ducts), len(self._existing_points)))
            if not self._placement_ducts:
                self._finish_placement("Completed")
                return
            self._schedule_placement_callback(self._process_placement_batch, "Could not queue first selected duct")
        except Exception as exc:
            _write_exception("Could not collect selected duct targets")
            self._finish_placement("Failed", "Could not prepare selected duct targets: {}".format(exc))

    def _process_placement_batch(self):
        if self.cancelled:
            self._finish_placement("Cancelled")
            return
        batch_start_index = self._placement_index
        batch_counts_before = dict(self._placement_counts)
        batch_placed_count = len(self._placed_elements)
        batch_isolation_count = len(self._isolation_ids)
        batch_point_count = len(self._existing_points)
        batch_error_count = len(self._placement_errors)
        transaction = None
        try:
            transaction = Transaction(doc, "Place fire smoke dampers")
            transaction.Start()
            if not self._placement_symbol.IsActive:
                self._placement_symbol.Activate()
                _write_log("Activated family symbol {}".format(_element_id(self._placement_symbol)))
            end_index = min(self._placement_index + 1, len(self._placement_ducts))
            while self._placement_index < end_index and not self.cancelled:
                duct = self._placement_ducts[self._placement_index]
                self._placement_index += 1
                crossings = self._clash_points(duct)
                self._placement_counts["crossings"] += len(crossings)
                if not crossings:
                    self._placement_counts["skipped"] += 1
                    continue
                for location, wall, wall_source in crossings:
                    if self.cancelled:
                        break
                    if any(location.DistanceTo(point) <= DUPLICATE_CROSSING_TOLERANCE for point in self._existing_points):
                        self._placement_counts["duplicate"] += 1
                        _write_log("DUPLICATE: selected damper symbol already exists at this crossing (5 mm tolerance) on duct {}".format(_element_id(duct)))
                        continue
                    try:
                        try:
                            instance = doc.Create.NewFamilyInstance(location, self._placement_symbol, duct, RevitStructuralType.NonStructural)
                            _write_log("Placed using duct-hosted overload; duct={}, instance={}".format(_element_id(duct), _element_id(instance) if instance else "<none>"))
                        except Exception:
                            _write_exception("Duct-hosted placement overload failed for duct {} and symbol {}".format(_element_id(duct), _element_id(self._placement_symbol)))
                            level = doc.GetElement(duct.LevelId)
                            instance = doc.Create.NewFamilyInstance(location, self._placement_symbol, duct, level, RevitStructuralType.NonStructural)
                            _write_log("Placed using level fallback overload; duct={}, instance={}".format(_element_id(duct), _element_id(instance) if instance else "<none>"))
                        if instance:
                            self._placement_counts["placed"] += 1
                            self._placed_elements.append(instance.Id)
                            self._isolation_ids.append(duct.Id)
                            if wall_source == "host":
                                self._isolation_ids.append(wall.Id)
                            self._existing_points.append(location)
                        else:
                            self._placement_counts["skipped"] += 1
                    except Exception as exc:
                        self._placement_counts["skipped"] += 1
                        _write_exception("All placement overloads failed for duct {} and symbol {}: {}".format(_element_id(duct), _element_id(self._placement_symbol), exc))
                        if len(self._placement_errors) < 3:
                            self._placement_errors.append("Duct {}: {}".format(_element_id(duct), str(exc)))
            transaction.Commit()
            _write_log("Committed selected duct {}/{}".format(self._placement_index, len(self._placement_ducts)))
        except Exception as exc:
            _write_exception("Placement failed at selected duct index {}".format(self._placement_index))
            try:
                if transaction is not None and transaction.HasStarted():
                    transaction.RollBack()
                    _write_log("Failed selected-duct transaction rolled back")
            except Exception:
                _write_exception("Could not roll back failed placement batch")
            self._placement_index = batch_start_index
            self._placement_counts = batch_counts_before
            del self._placed_elements[batch_placed_count:]
            del self._isolation_ids[batch_isolation_count:]
            del self._existing_points[batch_point_count:]
            del self._placement_errors[batch_error_count:]
            self._finish_placement("Failed", "Placement stopped after {} ducts: {}".format(self._placement_index, exc))
            return

        percent = int(float(self._placement_index) * 100.0 / float(len(self._placement_ducts)))
        self.progress_bar.Value = percent
        self.progress_text.Text = "{}/{} ducts | {} crossings | {} placed | {} duplicates".format(
            self._placement_index,
            len(self._placement_ducts),
            self._placement_counts["crossings"],
            self._placement_counts["placed"],
            self._placement_counts["duplicate"],
        )
        if self.cancelled:
            self._finish_placement("Cancelled")
        elif self._placement_index >= len(self._placement_ducts):
            self._finish_placement("Completed")
        else:
            self._schedule_placement_callback(self._process_placement_batch, "Could not schedule next selected duct")

    def _finish_placement(self, state, error_message=None):
        counts = getattr(self, "_placement_counts", {"placed": 0, "skipped": 0, "duplicate": 0, "crossings": 0})
        self._placement_running = False
        self.place_button.IsEnabled = True
        self.cancel_button.IsEnabled = True
        for control in (self.family_box, self.symbol_box, self.wall_families_box, self.refresh_button, self.select_ducts_button, self.clear_ducts_button):
            control.IsEnabled = True
        self.place_button.IsEnabled = bool(self._picked_duct_ids)
        self.progress_text.Text = state
        if state == "Completed":
            self.progress_bar.Value = 100
        isolation_error = None
        if bool(self.isolate_box.IsChecked) and getattr(self, "_placed_elements", None):
            ids = list(self._placed_elements) + list(self._isolation_ids)
            isolation_error = self._isolate_placed(ids, getattr(self, "_placement_view_id", None))
        summary = "{}: {} ducts checked, {} wall crossings, {} dampers placed, {} duplicates, {} ducts skipped.".format(
            state,
            getattr(self, "_placement_index", 0),
            counts["crossings"],
            counts["placed"],
            counts["duplicate"],
            counts["skipped"],
        )
        errors = getattr(self, "_placement_errors", [])
        if errors:
            summary += "\nFirst placement error: {}".format(errors[0])
        if error_message:
            summary += "\n{}".format(error_message)
        if isolation_error:
            summary += "\nTemporary isolation could not be applied: {}".format(isolation_error)
        elif bool(self.isolate_box.IsChecked) and getattr(self, "_placed_elements", None):
            summary += "\nPlaced dampers and related host elements are temporarily isolated in the placement view."
        _write_log("PLACEMENT SUMMARY: {}; errors captured={}".format(summary.replace("\n", " | "), len(errors)))
        summary += "\n\nFull diagnostic log:\n{}".format(LOG_PATH)
        forms.alert(summary, exitscript=False)
        self.Close()

    def _isolate_placed(self, element_ids, view_id=None):
        if not element_ids:
            return None
        try:
            target_view = doc.GetElement(view_id) if view_id is not None else doc.ActiveView
            if target_view is None:
                return "the placement view is no longer available"
            unique_ids = List[DB.ElementId]()
            seen_ids = set()
            for element_id in element_ids:
                try:
                    key = element_id.IntegerValue
                except Exception:
                    key = str(element_id)
                if key not in seen_ids:
                    seen_ids.add(key)
                    unique_ids.Add(element_id)
            if unique_ids.Count:
                target_view.IsolateElementsTemporary(unique_ids)
            return None
        except Exception as exc:
            logger.debug("Temporary isolation unavailable: {}".format(exc))
            return str(exc)


if not doc:
    forms.alert("This tool requires an active Revit project.", exitscript=True)

_write_log("=" * 72)
_write_log("SCRIPT INVOCATION: document='{}'; log='{}'".format(doc.Title if doc else "<none>", LOG_PATH))
try:
    window = QuickDamperWindow()
    window.Show()
except Exception as exc:
    _write_exception("Unhandled tool initialization/window exception: {}".format(exc))
    forms.alert("Quick Fire Damper failed to start: {}\n\nFull details saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
