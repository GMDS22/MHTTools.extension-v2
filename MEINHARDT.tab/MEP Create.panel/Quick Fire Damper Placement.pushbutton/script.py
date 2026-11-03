# -*- coding: utf-8 -*-
"""Quickly place selected duct damper families at selected fire/smoke wall clashes."""

import clr
import codecs
import os
import json
import time
import traceback

clr.AddReference("System")
clr.AddReference("WindowsBase")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")

from Autodesk.Revit.DB import (
    BuiltInCategory, FilteredElementCollector, Transaction,
    Options, SolidUtils, Transform
)
from Autodesk.Revit.DB.Structure import StructuralType as RevitStructuralType
from pyrevit import DB, forms, revit, script
from System import Action
from System.Collections.Generic import List
from System.Windows.Threading import DispatcherPriority

TOOL_VERSION = "1.0"
THIS_DIR = os.path.dirname(__file__)
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
    try:
        param = element.LookupParameter(name)
        if not param:
            element_document = getattr(element, "Document", None) or doc
            element_type = element_document.GetElement(element.GetTypeId()) if hasattr(element, "GetTypeId") else None
            param = element_type.LookupParameter(name) if element_type else None
        if param:
            value = param.AsValueString() or param.AsString()
            if value:
                return value.strip()
            return str(param.AsInteger()) if param.StorageType == DB.StorageType.Integer else ""
    except Exception:
        pass
    return ""


def _is_rated_wall(wall):
    value = (_param_text(wall, "NWB_Material") + " " + _param_text(wall, "NWB_MATERIAL")).lower()
    return ("fire" in value or "smoke" in value or "frl" in value or "fr" in value.split())


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


def _wall_family_key(wall):
    return _wall_family_name(wall).strip().lower()


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
    def __init__(self, key, family_name, type_keys, sources, is_checked=False):
        self.Key = key
        self.Name = family_name
        self.TypeKeys = set(type_keys)
        self.TypeCount = len(self.TypeKeys)
        self.Sources = set(sources)
        self.IsChecked = is_checked
        source_label = "host + linked" if len(self.Sources) > 1 else ("linked" if "linked" in self.Sources else "host")
        self.DisplayName = "{} ({} rated types, {})".format(family_name, self.TypeCount, source_label)


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
        _write_log("Window initialized for document '{}'".format(doc.Title if doc else "<none>"))
        self.wall_families = []
        self.families = []
        self._wall_records = []
        self.cancelled = False
        self._placement_running = False
        self.cancel_button.Click += self._cancel
        self.place_button.Click += self._place
        self.family_box.SelectionChanged += self._family_changed
        self.select_all_button.Click += lambda s, a: [setattr(item, "IsChecked", True) for item in (self.wall_families_box.ItemsSource or [])]
        self.clear_button.Click += lambda s, a: [setattr(item, "IsChecked", False) for item in (self.wall_families_box.ItemsSource or [])]
        self.refresh_button.Click += lambda s, a: self._refresh_wall_types()
        self.select_ducts_button.Click += self._select_active_view_ducts
        self._load_families()
        self._refresh_wall_types()
        self._restore_state()
        _write_log("Initial UI population complete: {} damper families, {} rated wall families".format(len(self.families), len(self.wall_families)))

    def _select_active_view_ducts(self, sender, args):
        try:
            ducts = FilteredElementCollector(doc, doc.ActiveView.Id).OfCategory(BuiltInCategory.OST_DuctCurves).WhereElementIsNotElementType().ToElements()
            duct_ids = [duct.Id for duct in ducts]
            uidoc.Selection.SetElementIds(List[DB.ElementId](duct_ids))
            self.status_text.Text = "Selected {} ducts in active view".format(len(duct_ids))
            _write_log("Selected {} duct curves from active view '{}'".format(len(duct_ids), doc.ActiveView.Name))
            if not duct_ids:
                forms.alert("No ducts were found in the active view.", exitscript=False)
        except Exception as exc:
            _write_exception("Could not select ducts in the active view")
            forms.alert("Could not select ducts: {}\n\nDetails saved to:\n{}".format(exc, LOG_PATH), exitscript=False)

    def _cancel(self, sender, args):
        self.cancelled = True
        if not getattr(self, "_placement_running", False):
            self.Close()
        else:
            self.progress_text.Text = "Cancelling... completed items will be kept"
            self.cancel_button.IsEnabled = False

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
        self.family_box.ItemsSource = [FamilyItem(f) for f in damper_families]
        _write_log("Loaded {} duct accessory families".format(len(damper_families)))
        if not damper_families:
            _write_log("WARNING: no Duct Accessory families were found in the active document")
        if damper_families:
            self.family_box.SelectedIndex = 0

    def _family_changed(self, sender, args):
        selected = self.family_box.SelectedItem
        if selected is None:
            self.symbol_box.ItemsSource = None
            return
        symbols = []
        family = selected.Family
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(SymbolItem(symbol))
        symbols.sort(key=lambda s: s.Name.lower())
        self.symbol_box.ItemsSource = symbols
        _write_log("Family '{}' has {} symbols".format(selected.Name, len(symbols)))
        if not symbols:
            _write_log("WARNING: selected family has no loadable symbols")
        if symbols:
            self.symbol_box.SelectedIndex = 0

    def _linked_architecture_walls(self):
        records = []
        links = FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements()
        _write_log("Checking {} Revit link instances for walls".format(len(links)))
        for link in links:
            try:
                if link.IsHidden(doc.ActiveView):
                    continue
                linked_doc = link.GetLinkDocument()
                if not linked_doc:
                    continue
                transform = link.GetTotalTransform() if hasattr(link, "GetTotalTransform") else link.GetTransform()
                walls = FilteredElementCollector(linked_doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
                for wall in walls:
                    records.append((wall, transform, linked_doc.Title))
            except Exception:
                _write_exception("Linked wall collection failed for link '{}'".format(getattr(link, "Name", "<unknown>")))
                logger.debug("Link wall collection skipped")
        _write_log("Collected {} walls from loaded, visible links".format(len(records)))
        return records

    def _refresh_wall_types(self):
        family_groups = {}
        self._wall_records = []
        view_id = doc.ActiveView.Id
        host_walls = FilteredElementCollector(doc, view_id).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
        host_rated = 0

        def add_rated_wall(wall, transform, source_name):
            family_name = _wall_family_name(wall)
            family_key = family_name.strip().lower()
            if not family_key:
                return
            type_key = _wall_type_key(wall)
            group = family_groups.setdefault(family_key, {"name": family_name, "types": set(), "sources": set()})
            if type_key:
                group["types"].add(type_key)
            group["sources"].add(source_name)
            self._wall_records.append((wall, transform, source_name))

        for wall in host_walls:
            if _is_rated_wall(wall):
                host_rated += 1
                add_rated_wall(wall, Transform.Identity, "host")

        for wall, transform, source_name in self._linked_architecture_walls():
            if _is_rated_wall(wall):
                add_rated_wall(wall, transform, "linked")
        saved_state = self._load_state().get(doc.Title if doc else "document", {})
        remembered_families = set(saved_state.get("wall_families", []))
        remembered_types = set(saved_state.get("wall_types", []))
        self.wall_families = []
        for family_key in sorted(family_groups):
            group = family_groups[family_key]
            is_checked = family_key in remembered_families or bool(group["types"].intersection(remembered_types))
            self.wall_families.append(WallFamilyItem(family_key, group["name"], group["types"], group["sources"], is_checked))
        self.wall_families_box.ItemsSource = self.wall_families
        self.status_text.Text = "{} rated wall families".format(len(self.wall_families))
        _write_log("Wall scan: {} host walls / {} rated; {} rated wall families; {} matching wall records".format(len(host_walls), host_rated, len(self.wall_families), len(self._wall_records)))
        if not self.wall_families:
            _write_log("WARNING: no rated walls found; check NWB_Material/NWB_MATERIAL values and active view visibility")

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
            "wall_families": [item.Key for item in (self.wall_families_box.ItemsSource or []) if getattr(item, "IsChecked", False)],
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

    def _bounds_overlap(self, a, b, tolerance=0.05):
        try:
            for axis in ("X", "Y", "Z"):
                if getattr(a.Max, axis) < getattr(b.Min, axis) - tolerance or getattr(b.Max, axis) < getattr(a.Min, axis) - tolerance:
                    return False
            return True
        except Exception:
            return True

    def _clash_point(self, duct, selected_families):
        duct_solids = self._geometry_solids(duct)
        location = getattr(duct.Location, "Curve", None)
        if not duct_solids or location is None:
            _write_log("Duct {} cannot be tested: solids={}, curve_location={}".format(_element_id(duct), len(duct_solids), location is not None))
            return None
        tested_walls = 0
        bounds_matches = 0
        for wall, transform, source in self._wall_records:
            key = _wall_type_key(wall)
            if _wall_family_key(wall) not in selected_families or not _is_rated_wall(wall):
                continue
            tested_walls += 1
            for wall_solid in self._geometry_solids(wall):
                transformed = wall_solid
                if transform is not None and transform != Transform.Identity:
                    try:
                        transformed = SolidUtils.CreateTransformed(wall_solid, transform)
                    except Exception:
                        _write_exception("Could not transform linked wall {} from '{}'".format(_element_id(wall), source))
                        continue
                for duct_solid in duct_solids:
                    if not self._bounds_overlap(duct_solid.GetBoundingBox(), transformed.GetBoundingBox(), 0.05):
                        continue
                    bounds_matches += 1
                    try:
                        if duct_solid.Intersect(transformed) != DB.SetComparisonResult.Disjoint:
                            wall_box = transformed.GetBoundingBox()
                            center = wall_box.Min.Add(wall_box.Max).Multiply(0.5)
                            start = location.GetEndPoint(0)
                            end = location.GetEndPoint(1)
                            direction = end.Subtract(start)
                            length = direction.GetLength()
                            if length <= 0.001:
                                continue
                            direction = direction.Normalize()
                            parameter = center.Subtract(start).DotProduct(direction)
                            parameter = max(0.0, min(length, parameter))
                            point = start.Add(direction.Multiply(parameter))
                            _write_log("CLASH: duct {} with wall type '{}' from '{}' at ({:.3f}, {:.3f}, {:.3f})".format(_element_id(duct), key, source, point.X, point.Y, point.Z))
                            return point
                    except Exception:
                        _write_exception("Solid intersection test failed for duct {} and wall {}".format(_element_id(duct), _element_id(wall)))
                        continue
        _write_log("Duct {}: no clash; selected rated walls tested={}, bounding-box candidates={}".format(_element_id(duct), tested_walls, bounds_matches))
        return None

    def _place(self, sender, args):
        if self.family_box.SelectedItem is None or self.symbol_box.SelectedItem is None:
            _write_log("Placement aborted: no family or symbol selected")
            forms.alert("Select a damper family and symbol.", exitscript=False)
            return
        selected_families = set(item.Key for item in (self.wall_families_box.ItemsSource or []) if getattr(item, "IsChecked", False))
        if not selected_families:
            _write_log("Placement aborted: no rated wall family checked")
            forms.alert("Select at least one rated wall family.", exitscript=False)
            return
        symbol = self.symbol_box.SelectedItem.Symbol
        _write_log("=" * 72)
        _write_log("PLACEMENT START: document='{}', view='{}', family='{}', type='{}'".format(doc.Title, doc.ActiveView.Name, self.family_box.SelectedItem.Name, self.symbol_box.SelectedItem.Name))
        _write_log("Selected wall family keys: {}".format(", ".join(sorted(selected_families))))
        _write_log("Candidate wall records: {}; selected symbol active={}".format(len(self._wall_records), symbol.IsActive))
        self._save_state()
        self._placement_running = True
        self.cancelled = False
        self.cancel_button.IsEnabled = True
        self.place_button.IsEnabled = False
        placed_elements = []
        paired_wall_elements = []
        placed = 0
        skipped = 0
        duplicate = 0
        placement_errors = []
        existing_points = []
        for accessory in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_DuctAccessory).WhereElementIsNotElementType().ToElements():
            try:
                loc = accessory.Location
                if hasattr(loc, "Point"):
                    existing_points.append(loc.Point)
            except Exception:
                pass
        transaction = Transaction(doc, "Quick place fire smoke dampers")
        try:
            transaction.Start()
            _write_log("Revit transaction started")
            if not symbol.IsActive:
                symbol.Activate()
                _write_log("Activated family symbol {}".format(_element_id(symbol)))
            ducts = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_DuctCurves).WhereElementIsNotElementType().ToElements())
            total = len(ducts)
            _write_log("Found {} host duct curves to inspect".format(total))
            if not total:
                _write_log("WARNING: no host duct curves found in the active document")
            for index, duct in enumerate(ducts, 1):
                if self.cancelled:
                    break
                if index % 10 == 0 or index == total:
                    percent = int(float(index) * 100.0 / float(total)) if total else 100
                    self.progress_bar.Value = percent
                    self.progress_text.Text = "{} / {} ducts".format(index, total)
                    self._pump_ui()
                location = self._clash_point(duct, selected_families)
                if location is None:
                    skipped += 1
                    continue
                if any(location.DistanceTo(point) <= 0.164042 for point in existing_points):
                    duplicate += 1
                    _write_log("DUPLICATE: duct {} clash point is within 50 mm of an existing duct accessory".format(_element_id(duct)))
                    continue
                try:
                    try:
                        instance = doc.Create.NewFamilyInstance(location, symbol, duct, RevitStructuralType.NonStructural)
                        _write_log("Placed on duct host using duct-hosted overload; duct={}, instance={}".format(_element_id(duct), _element_id(instance) if instance else "<none>"))
                    except Exception:
                        _write_exception("Duct-hosted NewFamilyInstance overload failed for duct {} and symbol {}".format(_element_id(duct), _element_id(symbol)))
                        level = doc.GetElement(duct.LevelId)
                        instance = doc.Create.NewFamilyInstance(location, symbol, duct, level, RevitStructuralType.NonStructural)
                        _write_log("Placed using level fallback overload; duct={}, instance={}".format(_element_id(duct), _element_id(instance) if instance else "<none>"))
                    if instance:
                        placed += 1
                        placed_elements.append(instance.Id)
                        paired_wall_elements.append(duct.Id)
                        existing_points.append(location)
                    else:
                        skipped += 1
                except Exception as exc:
                    skipped += 1
                    _write_exception("All placement overloads failed for duct {} and symbol {}: {}".format(_element_id(duct), _element_id(symbol), exc))
                    if len(placement_errors) < 3:
                        placement_errors.append("Duct {}: {}".format(_element_id(duct), str(exc)))
            transaction.Commit()
            _write_log("Revit transaction committed")
        except Exception as exc:
            _write_exception("Placement run aborted; transaction/model operation failed: {}".format(exc))
            if transaction.HasStarted():
                transaction.RollBack()
                _write_log("Revit transaction rolled back")
            self._placement_running = False
            self.place_button.IsEnabled = True
            self.cancel_button.IsEnabled = True
            self.progress_text.Text = "Failed"
            forms.alert("Damper placement failed: {}\n\nFull details saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
            return
        finally_state = "Cancelled" if self.cancelled else "Completed"
        self.progress_text.Text = finally_state
        self.progress_bar.Value = 100 if not self.cancelled else self.progress_bar.Value
        self._placement_running = False
        self.place_button.IsEnabled = True
        self.cancel_button.IsEnabled = True
        if bool(self.isolate_box.IsChecked) and placed_elements:
            ids = list(placed_elements) + list(paired_wall_elements)
            self._isolate_placed(ids)
        summary = "{}: placed {} dampers. Duplicate {}. Skipped {} incompatible ducts.".format(finally_state, placed, duplicate, skipped)
        if placement_errors:
            summary += "\nFirst placement error: {}".format(placement_errors[0])
        _write_log("PLACEMENT SUMMARY: {}; errors captured={}".format(summary.replace("\n", " | "), len(placement_errors)))
        summary += "\n\nFull diagnostic log:\n{}".format(LOG_PATH)
        forms.alert(summary, exitscript=False)
        self.Close()

    def _pump_ui(self):
        try:
            self.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)
        except Exception:
            pass

    def _isolate_placed(self, element_ids):
        if not element_ids:
            return
        try:
            doc.ActiveView.IsolateElementsTemporary(list(element_ids))
        except Exception as exc:
            logger.debug("Temporary isolation unavailable: {}".format(exc))


if not doc:
    forms.alert("This tool requires an active Revit project.", exitscript=True)

_write_log("=" * 72)
_write_log("SCRIPT INVOCATION: document='{}'; log='{}'".format(doc.Title if doc else "<none>", LOG_PATH))
try:
    window = QuickDamperWindow()
    window.ShowDialog()
except Exception as exc:
    _write_exception("Unhandled tool initialization/window exception: {}".format(exc))
    forms.alert("Quick Fire Damper failed to start: {}\n\nFull details saved to:\n{}".format(exc, LOG_PATH), exitscript=False)
