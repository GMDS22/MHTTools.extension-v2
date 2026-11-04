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
from Autodesk.Revit.Exceptions import OperationCanceledException, RegenerationFailedException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import DB, forms, revit, script
from pyrevitmep.event import CustomizableEvent
from System import Action
from System.Collections.Generic import List
from System.Threading import AbandonedMutexException, Mutex
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


def _event_request_accepted(request):
    try:
        return request.ToString() == "Accepted"
    except Exception:
        return str(request) == "Accepted"


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
        self.Id = int(family.Id.IntegerValue)
        self.Name = _safe_family_name(family)


class SymbolItem(object):
    def __init__(self, symbol):
        self.Id = int(symbol.Id.IntegerValue)
        self.Name = _safe_element_name(symbol, "Unnamed Type")


def _capture_preselected_duct_ids():
    try:
        view_id = int(doc.ActiveView.Id.IntegerValue)
        selected_ids = set(str(element_id.IntegerValue) for element_id in uidoc.Selection.GetElementIds())
        selected_duct_ids = []
        ducts = FilteredElementCollector(doc, DB.ElementId(view_id)).OfCategory(BuiltInCategory.OST_DuctCurves).WhereElementIsNotElementType().ToElements()
        for duct in ducts:
            duct_id = _element_id(duct)
            if duct_id in selected_ids:
                selected_duct_ids.append(duct_id)
        return sorted(set(selected_duct_ids)), view_id
    except Exception:
        _write_exception("Could not capture selected duct targets before opening the tool")
        try:
            return [], int(doc.ActiveView.Id.IntegerValue)
        except Exception:
            return [], None


def _acquire_run_mutex():
    mutex_name = "Local\\MHTTools_QuickFireDamper_{}".format(os.getpid())
    run_mutex = Mutex(False, mutex_name)
    try:
        acquired = run_mutex.WaitOne(0, False)
    except AbandonedMutexException:
        acquired = True
    if not acquired:
        run_mutex.Close()
        return None
    return run_mutex


def _release_unassigned_mutex(run_mutex):
    if run_mutex is None:
        return
    try:
        run_mutex.ReleaseMutex()
    except Exception:
        pass
    try:
        run_mutex.Close()
    except Exception:
        pass


class QuickDamperWindow(forms.WPFWindow):
    def __init__(self, initial_duct_ids, initial_view_id, run_mutex):
        forms.WPFWindow.__init__(self, os.path.join(THIS_DIR, "QuickFireDamper.xaml"))
        self._run_mutex = run_mutex
        self._run_mutex_released = False
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
        self._picked_duct_ids = list(initial_duct_ids or [])
        self._picked_view_id = initial_view_id
        self.cancelled = False
        self._placement_running = False
        self.cancel_button.Click += self._cancel
        self.Closing += self._on_closing
        self.place_button.Click += self._place
        self.family_box.SelectionChanged += self._family_changed
        self.refresh_button.Click += self._refresh_wall_types_click
        self.select_ducts_button.Click += self._select_active_view_ducts
        self.clear_ducts_button.Click += self._clear_duct_targets
        self._load_families()
        self._refresh_wall_types()
        self._restore_state()
        self._set_duct_target_status()
        _write_log("Initial UI population complete: {} damper families, {} rated wall families".format(len(self.families), len(self.wall_families)))

    def _select_active_view_ducts(self, sender, args):
        self._queue_utility_action(self._pick_active_view_ducts_api)

    def _set_duct_target_status(self):
        if self._picked_duct_ids:
            self.status_text.Text = "{} selected duct targets".format(len(self._picked_duct_ids))
        else:
            self.status_text.Text = "Select duct targets before placement"
        self.place_button.IsEnabled = bool(self._picked_duct_ids)

    def _clear_duct_targets(self, sender, args):
        if self._utility_action_running or self._placement_running:
            return
        self._picked_duct_ids = []
        self._picked_view_id = None
        self._set_duct_target_status()

    def _pick_active_view_ducts_api(self):
        picked_ids = []
        previous_ids = list(self._picked_duct_ids or [])
        active_uidoc = self._get_active_uidoc()
        if active_uidoc is None:
            self._invalidate_duct_targets()
            self.status_text.Text = "Return to the source project to pick ducts"
            self._finish_utility_action()
            return
        try:
            pick_view_id = int(doc.ActiveView.Id.IntegerValue)
            self.Hide()
            ducts = self._active_view_ducts(pick_view_id)
            allowed_ids = set(_element_id(duct) for duct in ducts)
            if not allowed_ids:
                self.status_text.Text = "No ducts in active view"
                forms.alert("No ducts were found in the active view.", exitscript=False)
                return
            references = active_uidoc.Selection.PickObjects(
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
            if int(doc.ActiveView.Id.IntegerValue) != pick_view_id:
                self._invalidate_duct_targets()
                self.status_text.Text = "Active view changed; pick duct targets again"
                return
            if picked_ids:
                self._picked_duct_ids = picked_ids
                self._picked_view_id = pick_view_id
                self._set_duct_target_status()
                _write_log("User picked {} ducts from active view '{}'".format(len(picked_ids), doc.ActiveView.Name))
            else:
                self.status_text.Text = "No new ducts picked; {} existing targets kept".format(len(previous_ids))
                _write_log("Duct pick completed with no elements; retained {} prior targets".format(len(previous_ids)))
        except OperationCanceledException:
            self.status_text.Text = "Duct pick cancelled; {} existing targets kept".format(len(previous_ids))
            _write_log("Duct pick cancelled; retained {} prior picks".format(len(previous_ids or [])))
        except RegenerationFailedException:
            raise
        except Exception as exc:
            _write_exception("Interactive duct pick failed")
            forms.alert("Could not pick ducts: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
        finally:
            try:
                self.Show()
                self.Activate()
            except Exception:
                _write_exception("Could not restore the damper window after duct picking")
            self._finish_utility_action()

    def _active_view_ducts(self, view_id=None):
        target_view_id = DB.ElementId(int(view_id)) if view_id is not None else doc.ActiveView.Id
        elements = (
            FilteredElementCollector(doc, target_view_id)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        duct_category_id = int(BuiltInCategory.OST_DuctCurves)
        return [
            element for element in elements
            if element.Category is not None
            and element.Category.Id.IntegerValue == duct_category_id
        ]

    def _refresh_wall_types_click(self, sender, args):
        self._queue_utility_action(self._refresh_wall_types_api)

    def _refresh_wall_types_api(self):
        try:
            if self._get_active_uidoc() is None:
                self.status_text.Text = "Return to the source project to refresh wall candidates"
                return
            self._refresh_wall_types()
        except RegenerationFailedException:
            raise
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
            request = self._utility_event.raise_event(action)
            if not _event_request_accepted(request):
                raise RuntimeError("Revit did not accept the requested ExternalEvent ({})".format(request))
        except Exception as exc:
            _write_exception("Could not queue modeless utility action")
            self._finish_utility_action()
            forms.alert("Could not complete the requested action: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)

    def _finish_utility_action(self):
        self._utility_action_running = False
        self.select_ducts_button.IsEnabled = True
        self.clear_ducts_button.IsEnabled = True
        self.refresh_button.IsEnabled = True
        self._set_duct_target_status()

    def _get_active_uidoc(self):
        try:
            active_uidoc = revit.uidoc
            if active_uidoc is None or not doc.IsValidObject:
                return None
            if active_uidoc.Document != doc:
                return None
            return active_uidoc
        except Exception:
            return None

    def _cancel(self, sender, args):
        if self._utility_action_running:
            self.status_text.Text = "Please wait for the Revit selection/refresh to finish."
            return
        if getattr(self, "_commit_pending", False):
            self.Close()
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
            return
        self._release_run_mutex()

    def _release_run_mutex(self):
        if self._run_mutex_released:
            return
        self._run_mutex_released = True
        try:
            self._run_mutex.ReleaseMutex()
        except Exception:
            _write_exception("Could not release the damper tool run lock")
        try:
            self._run_mutex.Close()
        except Exception:
            pass

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
        self.families = []
        self._symbols_by_family = {}
        for family in damper_families:
            family_item = FamilyItem(family)
            self.families.append(family_item)
            symbol_items = []
            try:
                for symbol_id in family.GetFamilySymbolIds():
                    symbol = doc.GetElement(symbol_id)
                    if symbol:
                        symbol_items.append(SymbolItem(symbol))
            except Exception:
                _write_exception("Could not cache symbols for duct accessory family '{}'".format(_safe_family_name(family)))
            symbol_items.sort(key=lambda item: item.Name.lower())
            self._symbols_by_family[str(family_item.Id)] = symbol_items
        self.family_box.ItemsSource = self.families
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
        symbols = self._symbols_by_family.get(str(selected.Id), [])
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
        target_view_id = int(view_id) if view_id is not None else int(doc.ActiveView.Id.IntegerValue)
        target_view_element_id = DB.ElementId(target_view_id)
        target_view = doc.GetElement(target_view_element_id)
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
                walls = FilteredElementCollector(doc, target_view_element_id, link.Id).OfClass(DB.Wall).WhereElementIsNotElementType().ToElements()
                for wall in walls:
                    if crop_bounds is not None:
                        try:
                            wall_bounds = self._bounding_box_bounds(wall.get_BoundingBox(None), transform)
                        except Exception:
                            wall_bounds = None
                        if not self._bounds_overlap(wall_bounds, crop_bounds, horizontal_view):
                            _write_log("Skipped linked wall {} from '{}': outside active view crop or has no bounding box".format(_element_id(wall), linked_doc.Title))
                            continue
                    records.append((wall, link.Id, linked_doc.Title))
            except RegenerationFailedException:
                raise
            except Exception:
                _write_exception("Linked wall collection failed for link '{}'".format(getattr(link, "Name", "<unknown>")))
                logger.debug("Link wall collection skipped")
        _write_log("Collected {} walls from loaded, visible links".format(len(records)))
        return records

    def _refresh_wall_types(self, view_id=None):
        family_groups = {}
        self._wall_records = []
        target_view_id = int(view_id) if view_id is not None else int(doc.ActiveView.Id.IntegerValue)
        target_view_element_id = DB.ElementId(target_view_id)
        host_walls = FilteredElementCollector(doc, target_view_element_id).OfClass(DB.Wall).WhereElementIsNotElementType().ToElements()
        host_rated = 0

        def add_rated_wall(wall, transform, source_name, source_model=None, placement_candidate=True, link_id=None):
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
                try:
                    wall_id = wall.Id.IntegerValue
                except Exception:
                    wall_id = int(str(wall.Id))
                link_id_value = None
                if link_id is not None:
                    try:
                        link_id_value = link_id.IntegerValue
                    except Exception:
                        link_id_value = int(str(link_id))
                self._wall_records.append((wall_id, link_id_value, source_name))

        for wall in host_walls:
            if _is_rated_wall(wall):
                host_rated += 1
                add_rated_wall(wall, Transform.Identity, "host")

        for wall, link_id, source_name in self._linked_architecture_walls(target_view_id):
            if _is_rated_wall(wall):
                add_rated_wall(wall, None, "linked", source_name, link_id=link_id)

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
            "symbol": getattr(self.symbol_box.SelectedItem, "Name", ""),
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

    def _point_coordinates(self, point):
        return (float(point.X), float(point.Y), float(point.Z))

    def _within_duplicate_tolerance(self, point_coordinates, coordinates, tolerance=DUPLICATE_CROSSING_TOLERANCE):
        dx = float(point_coordinates[0]) - float(coordinates[0])
        dy = float(point_coordinates[1]) - float(coordinates[1])
        dz = float(point_coordinates[2]) - float(coordinates[2])
        return dx * dx + dy * dy + dz * dz <= tolerance * tolerance

    def _invalidate_duct_targets(self):
        self._picked_duct_ids = []
        self._picked_view_id = None
        self._set_duct_target_status()

    def _validate_run_context(self):
        try:
            if not doc or not doc.IsValidObject:
                return False, "The source Revit document is no longer available."
            active_uidoc = revit.uidoc
            if active_uidoc is None or active_uidoc.Document is None:
                return False, "There is no active Revit document."
            active_doc = active_uidoc.Document
            if not active_doc.IsValidObject or active_doc != doc:
                return False, "The active Revit document changed during placement. Reopen the tool in the target document."
            if self._placement_view_id is None or int(active_uidoc.ActiveView.Id.IntegerValue) != self._placement_view_id:
                return False, "The active view changed during placement. Select duct targets again in the target view."
            if self._picked_view_id != self._placement_view_id:
                return False, "The duct targets belong to a different view. Select them again in the active view."
            return True, ""
        except Exception as exc:
            return False, "Could not validate the active Revit context: {}".format(exc)

    def _geometry_solids(self, element):
        result = []
        element_id = _element_id(element)
        _write_log("GEOMETRY BEGIN: wall {}".format(element_id))
        try:
            geometry = element.get_Geometry(Options())
            for obj in geometry:
                if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                    result.append(obj)
                elif isinstance(obj, DB.GeometryInstance):
                    for solid in obj.GetInstanceGeometry():
                        if isinstance(solid, DB.Solid) and solid.Volume > 1e-9:
                            result.append(solid)
        except RegenerationFailedException:
            raise
        except Exception:
            _write_exception("Geometry extraction failed for element {}".format(element_id))
        if not result:
            _write_log("WARNING: element {} returned no solid geometry".format(element_id))
        _write_log("GEOMETRY END: wall {} | solids={}".format(element_id, len(result)))
        return result

    def _schedule_placement_callback(self, callback, error_context):
        def raise_callback():
            try:
                request = self._revit_event.raise_event(self._run_placement_callback, callback, error_context)
                if not _event_request_accepted(request):
                    self._handle_placement_queue_failure(error_context, "Revit rejected ExternalEvent request ({})".format(request))
            except Exception as exc:
                _write_exception(error_context)
                self._handle_placement_queue_failure(error_context, exc)

        try:
            continuation = Action(raise_callback)
            self.Dispatcher.BeginInvoke(continuation, DispatcherPriority.Background)
            return True
        except Exception as exc:
            _write_exception(error_context)
            self._handle_placement_queue_failure(error_context, exc)
            return False

    def _run_placement_callback(self, callback, error_context):
        try:
            callback()
        except RegenerationFailedException:
            raise
        except Exception as exc:
            _write_exception(error_context)
            self._finish_placement("Failed", "Placement callback failed: {}".format(exc))

    def _handle_placement_queue_failure(self, error_context, exc):
        self._placement_running = False
        self.cancelled = True
        self.cancel_button.IsEnabled = True
        for control in (self.family_box, self.symbol_box, self.wall_families_box, self.refresh_button, self.select_ducts_button, self.clear_ducts_button):
            control.IsEnabled = True
        self._set_duct_target_status()
        self.progress_text.Text = "Stopped; committed placements were kept"
        counts = getattr(self, "_placement_counts", {})
        message = "Could not continue the Revit event queue: {}\n{} selected ducts checked; {} dampers were committed and retained.".format(
            exc,
            getattr(self, "_placement_index", 0),
            counts.get("placed", 0),
        )
        if bool(self.isolate_box.IsChecked) and getattr(self, "_placed_elements", None):
            message += "\nTemporary isolation was not applied because Revit rejected the next callback."
        message += "\n\nFull diagnostic log:\n{}".format(LOG_PATH)
        _write_log("PLACEMENT QUEUE STOP: {} | {}".format(error_context, str(exc)))
        try:
            forms.alert(message, exitscript=False)
        except Exception:
            pass

    def _scan_duct_wall_batch(self):
        if self.cancelled:
            self._finish_placement("Cancelled")
            return
        context_valid, context_error = self._validate_run_context()
        if not context_valid:
            self._invalidate_duct_targets()
            self._finish_placement("Failed", context_error)
            return
        try:
            duct = doc.GetElement(DB.ElementId(int(self._current_duct_id)))
            if duct is None or not duct.IsValidObject:
                self._invalidate_duct_targets()
                self._finish_placement("Failed", "A selected duct is no longer available. Select duct targets again.")
                return
            location = getattr(duct.Location, "Curve", None)
            if location is None:
                _write_log("Duct {} cannot be tested: curve location is missing".format(self._current_duct_id))
                self._pending_crossings = []
                self._schedule_placement_callback(self._place_current_duct, "Could not continue after a duct without a curve")
                return

            end_index = min(self._wall_scan_index + 10, len(self._wall_records))
            intersection_options = SolidCurveIntersectionOptions()
            intersection_options.ResultType = SolidCurveIntersectionMode.CurveSegmentsInside
            for record_index in range(self._wall_scan_index, end_index):
                wall_id, link_id, source = self._wall_records[record_index]
                _write_log("WALL CHECK BEGIN: duct {} | wall {} | source {}".format(self._current_duct_id, wall_id, source))
                transform = Transform.Identity
                try:
                    if link_id is not None:
                        link = doc.GetElement(DB.ElementId(link_id))
                        linked_doc = link.GetLinkDocument() if link else None
                        if linked_doc is None:
                            _write_log("Skipped wall {} from '{}': link is no longer loaded".format(wall_id, source))
                            continue
                        wall = linked_doc.GetElement(DB.ElementId(wall_id))
                        transform = link.GetTotalTransform() if hasattr(link, "GetTotalTransform") else link.GetTransform()
                    else:
                        wall = doc.GetElement(DB.ElementId(wall_id))
                    if wall is None or not wall.IsValidObject:
                        _write_log("Skipped wall {} from '{}': element is no longer available".format(wall_id, source))
                        continue
                    wall_key = _wall_type_key(wall)
                except RegenerationFailedException:
                    raise
                except Exception:
                    _write_exception("Could not reacquire rated wall {} from '{}'".format(wall_id, source))
                    continue

                for wall_solid in self._geometry_solids(wall):
                    try:
                        transformed = wall_solid
                        if transform is not None and transform != Transform.Identity:
                            transformed = SolidUtils.CreateTransformed(wall_solid, transform)
                        intersections = transformed.IntersectWithCurve(location, intersection_options)
                        for segment_index in range(intersections.SegmentCount):
                            segment = intersections.GetCurveSegment(segment_index)
                            point = segment.Evaluate(0.5, True)
                            coordinates = self._point_coordinates(point)
                            if any(self._within_duplicate_tolerance(coordinates, item[1:4], 0.01) for item in self._pending_crossings):
                                continue
                            projection = location.Project(point)
                            parameter = float(projection.Parameter) if projection else 0.0
                            self._pending_crossings.append((parameter, coordinates[0], coordinates[1], coordinates[2], wall_id, source))
                            _write_log("CLASH: duct {} with wall type '{}' from '{}' at ({:.3f}, {:.3f}, {:.3f})".format(self._current_duct_id, wall_key, source, point.X, point.Y, point.Z))
                    except RegenerationFailedException:
                        raise
                    except Exception:
                        _write_exception("Curve/solid intersection failed for duct {} and wall {}".format(self._current_duct_id, wall_id))
                _write_log("WALL CHECK END: duct {} | wall {}".format(self._current_duct_id, wall_id))

            self._wall_scan_index = end_index
            self.progress_text.Text = "Duct {}/{} | rated walls {}/{}".format(self._placement_index + 1, len(self._placement_ducts), end_index, len(self._wall_records))
            if self._wall_scan_index < len(self._wall_records):
                self._schedule_placement_callback(self._scan_duct_wall_batch, "Could not continue wall intersection checks")
            else:
                self._pending_crossings.sort(key=lambda item: item[0])
                self._schedule_placement_callback(self._place_current_duct, "Could not continue selected duct placement")
        except RegenerationFailedException:
            raise
        except Exception as exc:
            _write_exception("Wall intersection scan failed for duct {}".format(self._current_duct_id))
            self._finish_placement("Failed", "Wall intersection checks stopped: {}".format(exc))

    def _place_current_duct(self):
        if self.cancelled:
            self._finish_placement("Cancelled")
            return
        context_valid, context_error = self._validate_run_context()
        if not context_valid:
            self._invalidate_duct_targets()
            self._finish_placement("Failed", context_error)
            return

        duct_id = self._current_duct_id
        transaction = None
        local_placed_ids = []
        local_isolation_ids = []
        local_points = []
        local_errors = []
        local_duplicates = 0
        local_skipped = 1 if not self._pending_crossings else 0
        placements = []
        for item in self._pending_crossings:
            coordinates = (item[1], item[2], item[3])
            wall_id = item[4]
            source = item[5]
            if any(self._within_duplicate_tolerance(coordinates, existing) for existing in self._existing_points + local_points):
                local_duplicates += 1
                _write_log("DUPLICATE: selected damper symbol already exists at this crossing (5 mm tolerance) on duct {}".format(duct_id))
            else:
                placements.append((coordinates, wall_id, source))

        try:
            duct = doc.GetElement(DB.ElementId(int(duct_id)))
            symbol = doc.GetElement(DB.ElementId(self._placement_symbol_id))
            if duct is None or symbol is None or not duct.IsValidObject or not symbol.IsValidObject:
                self._invalidate_duct_targets()
                self._finish_placement("Failed", "A selected duct or damper type is no longer available. Re-select the ducts and try again.")
                return
            if duct.Category is None or duct.Category.Id.IntegerValue != int(BuiltInCategory.OST_DuctCurves):
                self._invalidate_duct_targets()
                self._finish_placement("Failed", "A selected target is no longer a duct. Re-select the duct targets.")
                return

            if placements:
                transaction = Transaction(doc, "Place fire smoke dampers")
                try:
                    failure_options = transaction.GetFailureHandlingOptions()
                    failure_options.SetForcedModalHandling(True)
                    transaction.SetFailureHandlingOptions(failure_options)
                except RegenerationFailedException:
                    raise
                except Exception as exc:
                    _write_log("Could not force modal transaction failure handling: {}".format(exc))
                transaction.Start()
                if not symbol.IsActive:
                    symbol.Activate()
                    _write_log("Activated family symbol {}".format(self._placement_symbol_id))
                for coordinates, wall_id, source in placements:
                    location = DB.XYZ(coordinates[0], coordinates[1], coordinates[2])
                    instance = doc.Create.NewFamilyInstance(location, symbol, duct, RevitStructuralType.NonStructural)
                    if instance is None:
                        raise RuntimeError("Revit returned no instance for crossing wall {}".format(wall_id))
                    local_placed_ids.append(int(instance.Id.IntegerValue))
                    local_isolation_ids.append(int(duct.Id.IntegerValue))
                    if source == "host":
                        local_isolation_ids.append(int(wall_id))
                    local_points.append(coordinates)
                    _write_log("Placed damper: duct={}, instance={}".format(duct_id, int(instance.Id.IntegerValue)))
                commit_status = transaction.Commit()
                if commit_status == DB.TransactionStatus.Pending:
                    self._commit_pending = True
                    self._placement_running = False
                    self.place_button.IsEnabled = False
                    self.cancel_button.IsEnabled = True
                    self.cancel_button.Content = "Close"
                    self.progress_text.Text = "Revit is resolving transaction failures; this duct was not counted"
                    _write_log("TRANSACTION PENDING: selected duct {}; waiting for Revit failure resolution".format(duct_id))
                    return
                if commit_status != DB.TransactionStatus.Committed:
                    raise RuntimeError("Duct transaction did not commit (status: {})".format(commit_status))
                _write_log("Committed selected duct {}/{}".format(self._placement_index + 1, len(self._placement_ducts)))
        except RegenerationFailedException:
            _write_exception("Fatal Revit regeneration failure while placing duct {}".format(duct_id))
            raise
        except Exception as exc:
            _write_exception("Placement failed at selected duct {}".format(duct_id))
            try:
                if transaction is not None and transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                    _write_log("Failed transaction rolled back for selected duct {}".format(duct_id))
            except Exception:
                _write_exception("Could not roll back transaction for selected duct {}".format(duct_id))
            self._finish_placement("Failed", "Placement stopped after {} ducts: {}".format(self._placement_index, exc))
            return

        self._placement_counts["crossings"] += len(self._pending_crossings)
        self._placement_counts["duplicate"] += local_duplicates
        self._placement_counts["placed"] += len(local_placed_ids)
        self._placement_counts["skipped"] += local_skipped
        self._placed_elements.extend(local_placed_ids)
        self._isolation_ids.extend(local_isolation_ids)
        self._existing_points.extend(local_points)
        self._placement_errors.extend(local_errors)
        self._placement_index += 1
        self._pending_crossings = []
        self._complete_duct_progress()

    def _complete_duct_progress(self):
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

    def _place(self, sender, args):
        if self._placement_running or self._utility_action_running:
            return
        if not self._picked_duct_ids:
            self._set_duct_target_status()
            forms.alert("Select duct targets in the active view before placing dampers.", exitscript=False)
            return
        if self.family_box.SelectedItem is None or self.symbol_box.SelectedItem is None:
            _write_log("Placement aborted: no family or symbol selected")
            forms.alert("Select a damper family and symbol.", exitscript=False)
            return
        self._placement_symbol_id = int(self.symbol_box.SelectedItem.Id)
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
            request = self._revit_event.raise_event(self._run_placement_callback, self._begin_placement, "Could not start placement callback")
            if not _event_request_accepted(request):
                raise RuntimeError("Revit rejected the initial placement ExternalEvent ({})".format(request))
        except Exception as exc:
            _write_exception("Could not queue placement ExternalEvent")
            self._handle_placement_queue_failure("Could not queue placement ExternalEvent", exc)

    def _begin_placement(self):
        try:
            if self.cancelled:
                self._finish_placement("Cancelled")
                return
            self._placement_counts = {"placed": 0, "skipped": 0, "duplicate": 0, "crossings": 0}
            self._placement_errors = []
            self._placed_elements = []
            self._isolation_ids = []
            self._placement_view_id = int(doc.ActiveView.Id.IntegerValue)
            if self._picked_view_id is None or self._picked_view_id != self._placement_view_id:
                self._invalidate_duct_targets()
                self._finish_placement("Failed", "The active view changed after duct selection. Select the duct targets again in the current view.")
                return
            context_valid, context_error = self._validate_run_context()
            if not context_valid:
                self._invalidate_duct_targets()
                self._finish_placement("Failed", context_error)
                return
            self._save_state()
            self.progress_text.Text = "Scanning rated walls in the active view and linked models..."
            self._refresh_wall_types(self._placement_view_id)
            if not self._wall_records:
                self._finish_placement("Failed", "No explicitly rated walls were found in this view. Check the NWB_Material value and linked model visibility.")
                return
            self._schedule_placement_callback(self._collect_placement_targets, "Could not continue selected duct preparation")
        except RegenerationFailedException:
            raise
        except Exception as exc:
            _write_exception("Could not initialize placement run")
            self._finish_placement("Failed", "Placement initialization failed: {}".format(exc))

    def _collect_placement_targets(self):
        try:
            if self.cancelled:
                self._finish_placement("Cancelled")
                return
            context_valid, context_error = self._validate_run_context()
            if not context_valid:
                self._invalidate_duct_targets()
                self._finish_placement("Failed", context_error)
                return
            self.progress_text.Text = "Collecting selected duct targets..."
            picked_ids = set(self._picked_duct_ids)
            view_duct_ids = set(_element_id(duct) for duct in self._active_view_ducts(self._placement_view_id))
            self._placement_ducts = [duct_id for duct_id in self._picked_duct_ids if duct_id in view_duct_ids]
            if len(self._placement_ducts) != len(picked_ids):
                self._invalidate_duct_targets()
                self._finish_placement("Failed", "One or more selected duct targets are no longer available in this view. Select the targets again before placement.")
                return
            self._placement_index = 0
            self._existing_points = []
            symbol_id = self._placement_symbol_id
            accessories = FilteredElementCollector(doc, DB.ElementId(self._placement_view_id)).OfClass(DB.FamilyInstance).WhereElementIsNotElementType().ToElements()
            for accessory in accessories:
                try:
                    if accessory.Category is None or accessory.Category.Id.IntegerValue != int(BuiltInCategory.OST_DuctAccessory):
                        continue
                    location = accessory.Location
                    if int(accessory.Symbol.Id.IntegerValue) == symbol_id and hasattr(location, "Point"):
                        self._existing_points.append(self._point_coordinates(location.Point))
                except Exception:
                    continue
            _write_log("PLACEMENT START: document='{}', view='{}', family='{}', type='{}'".format(doc.Title, doc.ActiveView.Name, self._placement_family_name, self._placement_symbol_name))
            _write_log("Auto-detected rated wall families: {}".format(", ".join(item.Key for item in self.wall_families)))
            _write_log("Candidate wall records: {}; selected duct targets: {}; matching existing symbols: {}".format(len(self._wall_records), len(self._placement_ducts), len(self._existing_points)))
            if not self._placement_ducts:
                self._finish_placement("Completed")
                return
            self._schedule_placement_callback(self._process_placement_batch, "Could not queue first selected duct")
        except RegenerationFailedException:
            raise
        except Exception as exc:
            _write_exception("Could not collect selected duct targets")
            self._finish_placement("Failed", "Could not prepare selected duct targets: {}".format(exc))

    def _process_placement_batch(self):
        if self.cancelled:
            self._finish_placement("Cancelled")
            return
        context_valid, context_error = self._validate_run_context()
        if not context_valid:
            self._invalidate_duct_targets()
            self._finish_placement("Failed", context_error)
            return
        if self._placement_index >= len(self._placement_ducts):
            self._finish_placement("Completed")
            return
        self._current_duct_id = self._placement_ducts[self._placement_index]
        self._wall_scan_index = 0
        self._pending_crossings = []
        self._scan_duct_wall_batch()

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
            target_view_id = DB.ElementId(int(view_id)) if view_id is not None else doc.ActiveView.Id
            target_view = doc.GetElement(target_view_id)
            if target_view is None:
                return "the placement view is no longer available"
            unique_ids = List[DB.ElementId]()
            seen_ids = set()
            for element_id_value in element_ids:
                key = int(element_id_value)
                if key not in seen_ids:
                    seen_ids.add(key)
                    unique_ids.Add(DB.ElementId(key))
            if unique_ids.Count:
                target_view.IsolateElementsTemporary(unique_ids)
            return None
        except RegenerationFailedException:
            raise
        except Exception as exc:
            logger.debug("Temporary isolation unavailable: {}".format(exc))
            return str(exc)


if not doc:
    forms.alert("This tool requires an active Revit project.", exitscript=True)

_write_log("=" * 72)
_write_log("SCRIPT INVOCATION: document='{}'; log='{}'".format(doc.Title if doc else "<none>", LOG_PATH))
run_mutex = None
window = None
try:
    run_mutex = _acquire_run_mutex()
    if run_mutex is None:
        forms.alert("Quick Fire Damper is already open in this Revit session.", exitscript=True)
    initial_duct_ids, initial_view_id = _capture_preselected_duct_ids()
    window = QuickDamperWindow(initial_duct_ids, initial_view_id, run_mutex)
    window.Show()
except Exception as exc:
    if window is not None:
        window._release_run_mutex()
    else:
        _release_unassigned_mutex(run_mutex)
    _write_exception("Unhandled tool initialization/window exception: {}".format(exc))
    forms.alert("Quick Fire Damper failed to start: {}\n\nFull details saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
