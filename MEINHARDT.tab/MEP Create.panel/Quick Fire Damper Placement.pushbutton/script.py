# -*- coding: utf-8 -*-
"""Quickly place selected duct damper families at selected fire/smoke wall clashes."""

import clr
import os
import json

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

TOOL_VERSION = "1.0"
THIS_DIR = os.path.dirname(__file__)
doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

STATE_PATH = os.path.join(os.path.dirname(doc.PathName) if doc and doc.PathName else os.path.expanduser("~"), "MHT_QuickDamperState.json") if doc else None


def _element_id(element):
    try:
        return str(element.Id.IntegerValue)
    except Exception:
        return str(element.Id)


def _param_text(element, name):
    try:
        param = element.LookupParameter(name)
        if not param:
            element_type = doc.GetElement(element.GetTypeId()) if hasattr(element, "GetTypeId") else None
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


class WallTypeItem(object):
    def __init__(self, key, source, description="", is_checked=False):
        self.Key = key
        self.Source = source
        self.Description = description
        self.IsChecked = is_checked
        label = key
        if description:
            label += " - " + description
        if source == "linked":
            label += " (linked)"
        self.DisplayName = label


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
        self.wall_types = []
        self.families = []
        self._wall_records = []
        self.cancelled = False
        self.family_box.SelectionChanged += self._family_changed
        self.select_all_button.Click += lambda s, a: [setattr(item, "IsChecked", True) for item in (self.wall_types_box.ItemsSource or [])]
        self.clear_button.Click += lambda s, a: [setattr(item, "IsChecked", False) for item in (self.wall_types_box.ItemsSource or [])]
        self.refresh_button.Click += lambda s, a: self._refresh_wall_types()
        self.cancel_button.Click += self._cancel
        self.place_button.Click += self._place
        self._load_families()
        self._refresh_wall_types()
        self._restore_state()

    def _cancel(self, sender, args):
        self.cancelled = True
        self.Close()

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
        if symbols:
            self.symbol_box.SelectedIndex = 0

    def _linked_architecture_walls(self):
        records = []
        for link in FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements():
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
                logger.debug("Link wall collection skipped")
        return records

    def _refresh_wall_types(self):
        keys = {}
        source_names = {}
        descriptions = {}
        self._wall_records = []
        view_id = doc.ActiveView.Id
        host_walls = FilteredElementCollector(doc, view_id).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
        for wall in host_walls:
            if _is_rated_wall(wall):
                key = _wall_type_key(wall)
                if key:
                    keys[key] = None
                    source_names[key] = "host"
                    descriptions[key] = _wall_type_description(wall)
                    self._wall_records.append((wall, Transform.Identity, doc.Title))

        for wall, transform, source_name in self._linked_architecture_walls():
            if _is_rated_wall(wall):
                key = _wall_type_key(wall)
                if key:
                    keys[key] = None
                    source_names[key] = "linked"
                    try:
                        wall_type = wall.Document.GetElement(wall.GetTypeId())
                    except Exception:
                        wall_type = None
                    descriptions[key] = _wall_type_description(wall_type)
                    self._wall_records.append((wall, transform, source_name))
        remembered = set(self._load_state().get(doc.Title if doc else "document", {}).get("wall_types", []))
        self.wall_types = [WallTypeItem(key, source_names[key], descriptions.get(key, ""), key in remembered) for key in sorted(keys, key=lambda k: k.lower())]
        self.wall_types_box.ItemsSource = self.wall_types
        self.status_text.Text = "{} rated wall types in active view".format(len(self.wall_types))

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
            "wall_types": [item.Key for item in (self.wall_types_box.ItemsSource or []) if getattr(item, "IsChecked", False)],
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
        selected_keys = set(state.get("wall_types", []))
        for item in (self.wall_types_box.ItemsSource or []):
            item.IsChecked = item.Key in selected_keys

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
            pass
        return result

    def _bounds_overlap(self, a, b, tolerance=0.05):
        try:
            for axis in ("X", "Y", "Z"):
                if getattr(a.Max, axis) < getattr(b.Min, axis) - tolerance or getattr(b.Max, axis) < getattr(a.Min, axis) - tolerance:
                    return False
            return True
        except Exception:
            return True

    def _clash_point(self, duct, selected_types):
        duct_solids = self._geometry_solids(duct)
        location = getattr(duct.Location, "Curve", None)
        if not duct_solids or location is None:
            return None
        for wall, transform, source in self._wall_records:
            key = _wall_type_key(wall)
            if key not in selected_types or not _is_rated_wall(wall):
                continue
            for wall_solid in self._geometry_solids(wall):
                transformed = wall_solid
                if transform is not None and transform != Transform.Identity:
                    try:
                        transformed = SolidUtils.CreateTransformed(wall_solid, transform)
                    except Exception:
                        continue
                for duct_solid in duct_solids:
                    if not self._bounds_overlap(duct_solid.GetBoundingBox(), transformed.GetBoundingBox(), 0.05):
                        continue
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
                            return start.Add(direction.Multiply(parameter))
                    except Exception:
                        continue
        return None

    def _place(self, sender, args):
        if self.family_box.SelectedItem is None or self.symbol_box.SelectedItem is None:
            forms.alert("Select a damper family and symbol.", exitscript=False)
            return
        selected_types = set(item.Key for item in (self.wall_types_box.ItemsSource or []) if getattr(item, "IsChecked", False))
        if not selected_types:
            forms.alert("Select at least one wall type.", exitscript=False)
            return
        symbol = self.symbol_box.SelectedItem.Symbol
        if not symbol.IsActive:
            try:
                symbol.Activate()
            except Exception as exc:
                forms.alert("Could not activate damper symbol: {}".format(exc), exitscript=False)
                return

        self._save_state()
        placed = 0
        skipped = 0
        duplicate = 0
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
            ducts = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_DuctCurves).WhereElementIsNotElementType().ToElements())
            for duct in ducts:
                if self.cancelled:
                    break
                location = self._clash_point(duct, selected_types)
                if location is None:
                    skipped += 1
                    continue
                if any(location.DistanceTo(point) <= 0.164042 for point in existing_points):
                    duplicate += 1
                    continue
                try:
                    try:
                        instance = doc.Create.NewFamilyInstance(location, symbol, duct, RevitStructuralType.NonStructural)
                    except Exception:
                        level = doc.GetElement(duct.LevelId)
                        instance = doc.Create.NewFamilyInstance(location, symbol, duct, level, RevitStructuralType.NonStructural)
                    if instance:
                        placed += 1
                        existing_points.append(location)
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
            transaction.Commit()
        except Exception as exc:
            if transaction.HasStarted():
                transaction.RollBack()
            forms.alert("Damper placement failed: {}".format(exc), exitscript=False)
            return
        forms.alert("Placed {} dampers. Duplicate {}. Skipped {} incompatible ducts.".format(placed, duplicate, skipped), exitscript=False)
        self.Close()


if not doc:
    forms.alert("This tool requires an active Revit project.", exitscript=True)

window = QuickDamperWindow()
window.ShowDialog()
