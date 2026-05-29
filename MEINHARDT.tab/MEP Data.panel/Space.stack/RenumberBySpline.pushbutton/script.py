# -*- coding: utf-8 -*-
from __future__ import division, print_function

import ctypes
import os

import clr
import System
clr.AddReference("WindowsBase")
from Autodesk.Revit.DB import BuiltInCategory, CategoryType, FilteredElementCollector, StorageType, XYZ
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import TaskDialog
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, script, revit


__title__ = "Renumber by Spline"


def _activate_revit():
    """Bring Revit's main window to the foreground after hiding the WPF dialog."""
    try:
        hwnd = int(__revit__.MainWindowHandle)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
__author__ = "GM"
__doc__ = "Sort selected elements along a curve and renumber them with fixed-width leading zeros."
_ALL_CATEGORIES_LABEL = "All categories"


uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document if uidoc else None


class _PreviewRow(object):
    def __init__(self, order, element_label, current_value, new_value):
        self.Order = order
        self.ElementLabel = element_label
        self.CurrentValue = current_value
        self.NewValue = new_value


class _CurveFilter(ISelectionFilter):
    def AllowElement(self, element):
        try:
            return (
                element is not None
                and element.Category is not None
                and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Lines)
                and _get_curve_from_element(element) is not None
            )
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return True


class _TargetFilter(ISelectionFilter):
    def __init__(self, allowed_category_id=None):
        self.allowed_category_id = allowed_category_id

    def AllowElement(self, element):
        if _get_curve_from_element(element) is not None:
            return False
        if self.allowed_category_id is None:
            return True
        try:
            return element.Category is not None and element.Category.Id.IntegerValue == self.allowed_category_id
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return True


def _to_int(value, default_value):
    try:
        return int(str(value).strip())
    except Exception:
        return int(default_value)


def _to_text(value):
    return ("" if value is None else str(value)).strip()


def _safe_alert(message, title=None):
    forms.alert(message, title=title or __title__)


def _add_category_pair(categories, category):
    try:
        if category is None:
            return
        if category.Parent is not None:
            return
    except Exception:
        pass

    try:
        category_id = category.Id.IntegerValue
        category_name = _to_text(category.Name)
    except Exception:
        return

    if category_id is None or not category_name:
        return

    if category_name in categories and categories[category_name] != category_id:
        categories["{} ({})".format(category_name, category_id)] = category_id
        return

    categories[category_name] = category_id


def _collect_categories_from_elements(elements, categories):
    for element in elements or []:
        try:
            if element is None or element.Category is None:
                continue
            if _get_curve_from_element(element) is not None:
                continue
            _add_category_pair(categories, element.Category)
        except Exception:
            continue


def _collect_visible_categories():
    categories = {}

    try:
        selected_elements = [doc.GetElement(element_id) for element_id in uidoc.Selection.GetElementIds()]
        _collect_categories_from_elements(selected_elements, categories)
    except Exception:
        pass

    try:
        active_view_id = uidoc.ActiveView.Id
        collector = FilteredElementCollector(doc, active_view_id).WhereElementIsNotElementType()
        _collect_categories_from_elements(collector, categories)
    except Exception:
        pass

    # Always supplement with ALL document model categories so the list is never incomplete
    try:
        for category in doc.Settings.Categories:
            try:
                if category is None:
                    continue
                if category.CategoryType != CategoryType.Model:
                    continue
                _add_category_pair(categories, category)
            except Exception:
                continue
    except Exception:
        pass

    return sorted(categories.items(), key=lambda item: item[0].lower())


def _get_curve_from_element(element):
    if element is None:
        return None

    for attr_name in ("GeometryCurve", "Curve"):
        try:
            curve = getattr(element, attr_name, None)
            if curve is not None:
                return curve
        except Exception:
            pass

    try:
        location = element.Location
        if location is not None and hasattr(location, "Curve"):
            return location.Curve
    except Exception:
        pass

    return None


def _get_element_point(element):
    if element is None:
        return None

    try:
        location = element.Location
        if location is not None:
            if hasattr(location, "Point") and location.Point is not None:
                return location.Point
            if hasattr(location, "Curve") and location.Curve is not None:
                return location.Curve.Evaluate(0.5, True)
    except Exception:
        pass

    try:
        bbox = element.get_BoundingBox(None)
        if bbox is not None:
            return XYZ(
                (bbox.Min.X + bbox.Max.X) / 2.0,
                (bbox.Min.Y + bbox.Max.Y) / 2.0,
                (bbox.Min.Z + bbox.Max.Z) / 2.0,
            )
    except Exception:
        pass

    return None


def _project_curve_position(curve, point):
    if curve is None or point is None:
        return None

    try:
        projection = curve.Project(point)
        if projection is not None:
            try:
                return float(curve.ComputeNormalizedParameter(projection.Parameter))
            except Exception:
                return float(projection.Parameter)
    except Exception:
        pass

    try:
        start = curve.GetEndPoint(0)
        return (point - start).GetLength()
    except Exception:
        return None


def _format_number(number_value, zero_count):
    text = str(int(number_value))
    requested_zeros = max(0, _to_int(zero_count, 2))
    minimum_width = requested_zeros + 1
    return text.zfill(max(len(text), minimum_width))


def _parameter_text(element, parameter_name):
    if element is None or not parameter_name:
        return ""

    try:
        param = element.LookupParameter(parameter_name)
    except Exception:
        return ""

    if param is None:
        return ""

    try:
        if param.StorageType == StorageType.String:
            return param.AsString() or ""
        return param.AsValueString() or ""
    except Exception:
        return ""


def _set_parameter_text(element, parameter_name, value_text):
    param = element.LookupParameter(parameter_name)
    if param is None:
        raise RuntimeError("Parameter '{}' was not found on element {}.".format(parameter_name, element.Id.IntegerValue))
    if param.IsReadOnly:
        raise RuntimeError("Parameter '{}' is read-only on element {}.".format(parameter_name, element.Id.IntegerValue))
    if param.StorageType != StorageType.String:
        raise RuntimeError("Parameter '{}' must be a text parameter.".format(parameter_name))
    param.Set(value_text)


def _validate_parameter_for_elements(elements, parameter_name):
    missing = []
    readonly = []
    non_text = []

    for element in elements:
        param = element.LookupParameter(parameter_name)
        if param is None:
            missing.append(element.Id.IntegerValue)
            continue
        if param.IsReadOnly:
            readonly.append(element.Id.IntegerValue)
            continue
        if param.StorageType != StorageType.String:
            non_text.append(element.Id.IntegerValue)

    if missing or readonly or non_text:
        parts = []
        if missing:
            parts.append("missing on {} element(s)".format(len(missing)))
        if readonly:
            parts.append("read-only on {} element(s)".format(len(readonly)))
        if non_text:
            parts.append("not a text parameter on {} element(s)".format(len(non_text)))
        raise RuntimeError("Target parameter '{}' is not writable for the current selection: {}.".format(parameter_name, ", ".join(parts)))


def _collect_common_text_parameters(elements):
    collected = set()
    counts = {}
    for element in elements:
        try:
            for param in element.Parameters:
                try:
                    if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
                        continue
                    definition = param.Definition
                    if definition is None:
                        continue
                    name = _to_text(definition.Name)
                    if name:
                        collected.add(name)
                        counts[name] = counts.get(name, 0) + 1
                except Exception:
                    continue
        except Exception:
            continue

    choices = sorted(collected)
    preferred = ["Mark", "Number", "Comments", "Type Mark"]
    ordered = [name for name in preferred if name in choices]
    ordered.extend(sorted([name for name in choices if name not in ordered], key=lambda item: (-counts.get(item, 0), item.lower())))
    return ordered


class RenumberBySplineWindow(forms.WPFWindow):
    def __init__(self, xaml_path):
        forms.WPFWindow.__init__(self, xaml_path)
        self._curve = None
        self._elements = []
        self._preview_rows = []
        self._seed_defaults()
        self._bootstrap_from_current_selection()

    def _seed_defaults(self):
        self.PreviewGrid.ItemsSource = []
        self._category_ids_by_name = {}
        self._refresh_categories()
        self.CmbParameter.ItemsSource = ["Mark"]
        self.CmbParameter.Text = "Mark"
        self.TxtStatus.Text = "Choose a category, pick the spline, pick the elements, then renumber."
        self._refresh_selection_summary()
        self._refresh_curve_summary()

    def _refresh_categories(self):
        current_category_id = self._selected_category_id()
        category_pairs = _collect_visible_categories()
        choices = [_ALL_CATEGORIES_LABEL]
        self._category_ids_by_name = {_ALL_CATEGORIES_LABEL: None}
        for category_name, category_id in category_pairs:  # dict is {name: id} so items() = (name, id)
            if category_name not in self._category_ids_by_name:
                choices.append(category_name)
                self._category_ids_by_name[category_name] = category_id

        self.CmbCategory.ItemsSource = choices

        # restore previously selected category if still present
        if current_category_id is not None:
            for index, name in enumerate(choices):
                if self._category_ids_by_name.get(name) == current_category_id:
                    self.CmbCategory.SelectedIndex = index
                    return

        self.CmbCategory.SelectedIndex = 0

    def _selected_category_id(self):
        selected_item = getattr(self.CmbCategory, 'SelectedItem', None)
        selected_name = _to_text(selected_item)
        if not selected_name:
            selected_name = _to_text(getattr(self.CmbCategory, 'Text', None))
        if not selected_name:
            return None
        return self._category_ids_by_name.get(selected_name)

    def _selected_category_name(self):
        selected_item = getattr(self.CmbCategory, 'SelectedItem', None)
        selected_name = _to_text(selected_item)
        if not selected_name:
            selected_name = _to_text(getattr(self.CmbCategory, 'Text', None))
        return selected_name

    def _category_allows_element(self, element):
        selected_category_id = self._selected_category_id()
        if selected_category_id is None:
            return True
        try:
            return element is not None and element.Category is not None and element.Category.Id.IntegerValue == selected_category_id
        except Exception:
            return False

    def _bootstrap_from_current_selection(self):
        curve, elements = self._resolve_selection()
        if curve is None and not elements:
            self._refresh_categories()
            return

        self._apply_selection(curve, elements)
        if curve is not None and elements:
            self._set_status("Detected current selection: curve and {} element(s).".format(len(elements)))
        elif elements:
            self._set_status("Detected current selection: {} element(s).".format(len(elements)))
        elif curve is not None:
            self._set_status("Detected current selection: curve only.")

    def _refresh_selection_summary(self):
        self.TxtSelectionCount.Text = "{} element(s) selected".format(len(self._elements))

    def _refresh_curve_summary(self):
        if self._curve is None:
            self.TxtCurve.Text = "No spline selected"
            return
        try:
            curve_name = self._curve.Name
        except Exception:
            curve_name = self._curve.GetType().Name
        self.TxtCurve.Text = curve_name

    def _set_status(self, text):
        self.TxtStatus.Text = _to_text(text)

    def _current_selection_ids(self):
        try:
            return list(uidoc.Selection.GetElementIds())
        except Exception:
            return []

    def _resolve_selection(self):
        curve = None
        elements = []
        for element_id in self._current_selection_ids():
            element = doc.GetElement(element_id)
            if element is None:
                continue
            if curve is None and _get_curve_from_element(element) is not None:
                curve = element
                continue
            if _get_element_point(element) is not None and self._category_allows_element(element):
                elements.append(element)
        return curve, elements

    def _load_common_parameters(self):
        if not self._elements:
            return
        choices = _collect_common_text_parameters(self._elements)
        if not choices:
            choices = ["Mark"]
        self.CmbParameter.ItemsSource = choices
        if self.CmbParameter.Text not in choices:
            self.CmbParameter.Text = choices[0]
        self._set_status("Loaded {} target parameter(s).".format(len(choices)))

    def _apply_selection(self, curve, elements):
        self._curve = curve
        self._elements = [element for element in list(elements or []) if self._category_allows_element(element)]
        self._refresh_curve_summary()
        self._refresh_selection_summary()
        self._refresh_categories()
        self._load_common_parameters()
        self._refresh_preview_panel()

    def _refresh_preview_panel(self):
        try:
            if not self._elements:
                self._preview_rows = []
                self.PreviewGrid.ItemsSource = []
                return

            rows, _, _ = self._build_preview()
            self._preview_rows = rows
            self.PreviewGrid.ItemsSource = rows
            self._set_status("Preview ready for {} element(s).".format(len(rows)))
        except Exception:
            self._preview_rows = []
            self.PreviewGrid.ItemsSource = []

    def _collect_ordered_elements(self, reverse=False, allow_curveless=False):
        if self._curve is None and not allow_curveless:
            raise RuntimeError("Pick a spline or curve first.")
        if not self._elements:
            raise RuntimeError("Pick one or more elements first.")

        curve = _get_curve_from_element(self._curve) if self._curve is not None else None
        if curve is None and not allow_curveless:
            raise RuntimeError("The selected path is not a curve element.")

        if curve is None and allow_curveless:
            ordered = [(element.Id.IntegerValue, element.Id.IntegerValue, element) for element in self._elements]
            ordered.sort(key=lambda item: (item[0], item[1]), reverse=reverse)
            return [item[2] for item in ordered]

        ordered = []
        for element in self._elements:
            point = _get_element_point(element)
            position = _project_curve_position(curve, point)
            if position is None:
                continue
            ordered.append((position, element.Id.IntegerValue, element))

        if not ordered:
            raise RuntimeError("None of the selected elements could be projected onto the spline.")

        ordered.sort(key=lambda item: (item[0], item[1]), reverse=reverse)
        return [item[2] for item in ordered]

    def _build_preview(self):
        parameter_name = _to_text(self.CmbParameter.Text)
        if not parameter_name:
            raise RuntimeError("Choose a target text parameter.")

        start_number = _to_int(self.TxtStart.Text, 1)
        step = _to_int(self.TxtStep.Text, 1)
        zero_count = max(0, _to_int(self.TxtZeros.Text, 2))
        prefix = _to_text(self.TxtPrefix.Text)
        suffix = _to_text(self.TxtSuffix.Text)
        reverse = bool(self.ChkReverse.IsChecked)

        ordered_elements = self._collect_ordered_elements(reverse=reverse, allow_curveless=False)
        rows = []
        for index, element in enumerate(ordered_elements):
            number_value = start_number + (index * step)
            number_text = _format_number(number_value, zero_count)
            new_value = "{}{}{}".format(prefix, number_text, suffix)
            current_value = _parameter_text(element, parameter_name)
            label = "{} | {}".format(element.Id.IntegerValue, element.Category.Name if element.Category else element.GetType().Name)
            rows.append(_PreviewRow(index + 1, label, current_value, new_value))
        return rows, parameter_name, ordered_elements

    def pick_curve_click(self, sender, args):
        try:
            TaskDialog.Show("Select Spline", "Select a spline or line. The start of the spline defines the first element.")
        except Exception:
            pass
        curve_element = None

        try:
            with self.conceal():
                _activate_revit()
                reference = uidoc.Selection.PickObject(
                    ObjectType.Element,
                    _CurveFilter(),
                    "Select spline"
                )
            curve_element = doc.GetElement(reference.ElementId) if reference is not None else None
        except OperationCanceledException:
            self._set_status("Spline pick canceled.")
            return
        except Exception as ex:
            forms.alert("Spline pick failed: {}".format(ex), title=__title__)
            self._set_status("Spline pick failed.")
            return

        if curve_element is None:
            self._set_status("No spline was selected.")
            return

        self._apply_selection(curve_element, self._elements)
        self._set_status("Spline selected.")

    def pick_elements_click(self, sender, args):
        selected_category_name = self._selected_category_name()
        if not selected_category_name or selected_category_name == _ALL_CATEGORIES_LABEL:
            forms.alert("Choose a specific category from the dropdown first, then pick the elements.")
            return

        try:
            TaskDialog.Show("Select Elements", "Select all elements you want to renumber, then press Finish in the Revit ribbon.")
        except Exception:
            pass
        refs = None

        try:
            with self.conceal():
                _activate_revit()
                refs = uidoc.Selection.PickObjects(
                    ObjectType.Element,
                    _TargetFilter(self._selected_category_id()),
                    "Select elements"
                )
        except OperationCanceledException:
            self._set_status("Selection canceled.")
            return
        except Exception as ex:
            forms.alert("Pick failed: {}".format(ex), title=__title__)
            self._set_status("Element pick failed.")
            return

        elements = []
        for ref in (refs or []):
            if ref is None:
                continue
            element = doc.GetElement(ref.ElementId)
            if element is not None and self._category_allows_element(element):
                elements.append(element)

        self._apply_selection(self._curve, elements)
        if not elements:
            forms.alert(
                "No '{}' elements were found in the selection.".format(selected_category_name),
                title=__title__
            )
            self._set_status("No elements loaded.")
            return

        self._set_status("Loaded {} '{}' element(s).".format(len(elements), selected_category_name))

    def category_changed(self, sender, args):
        self._elements = [element for element in self._elements if self._category_allows_element(element)]
        self._refresh_selection_summary()
        self._load_common_parameters()
        self._refresh_preview_panel()
        selected_name = _to_text(getattr(self.CmbCategory, 'SelectedItem', None))
        if not selected_name or selected_name == _ALL_CATEGORIES_LABEL:
            self._set_status("Category filter cleared. All visible categories can be selected.")
        else:
            self._set_status("Category filter set to {}.".format(selected_name))

    def refresh_categories_click(self, sender, args):
        self._refresh_categories()
        choices = list(getattr(self.CmbCategory, 'ItemsSource', []) or [])
        if len(choices) <= 1:
            self._set_status("No target categories were detected from the current selection or active view.")
        else:
            self._set_status("Loaded {} target categor{}.".format(len(choices) - 1, 'y' if len(choices) == 2 else 'ies'))

    def use_selection_click(self, sender, args):
        try:
            curve, elements = self._resolve_selection()
            if curve is None and not elements:
                raise RuntimeError("Select one curve and one or more elements in Revit first.")
            if curve is None:
                raise RuntimeError("Current selection did not contain a spline or curve.")
            if not elements:
                raise RuntimeError("Current selection did not contain any target elements.")
            self._apply_selection(curve, elements)
            self._set_status("Current selection loaded.")
        except Exception as ex:
            _safe_alert(str(ex))

    def clear_click(self, sender, args):
        self._curve = None
        self._elements = []
        self._preview_rows = []
        self._refresh_categories()
        self.CmbCategory.SelectedItem = _ALL_CATEGORIES_LABEL
        self.CmbCategory.Text = _ALL_CATEGORIES_LABEL
        self.CmbParameter.ItemsSource = ["Mark"]
        self.CmbParameter.Text = "Mark"
        self.TxtStart.Text = "1"
        self.TxtStep.Text = "1"
        self.TxtZeros.Text = "2"
        self.TxtPrefix.Text = ""
        self.TxtSuffix.Text = ""
        self.ChkReverse.IsChecked = False
        self.PreviewGrid.ItemsSource = []
        self._refresh_curve_summary()
        self._refresh_selection_summary()
        self._set_status("Cleared.")

    def preview_click(self, sender, args):
        try:
            if not self._elements:
                self._set_status("Pick the spline and elements first.")
                return
            self._refresh_preview_panel()
        except Exception as ex:
            _safe_alert(str(ex))

    def renumber_click(self, sender, args):
        try:
            if not self._elements:
                forms.alert("Pick elements first: choose a category, then click Pick Elements.", title=__title__)
                return
            if self._curve is None:
                forms.alert("Pick a spline first using Pick Spline / Curve.", title=__title__)
                return

            rows, parameter_name, ordered_elements = self._build_preview()
            _validate_parameter_for_elements(ordered_elements, parameter_name)

            with revit.Transaction(doc=doc, name="Renumber by Spline"):
                for row, element in zip(rows, ordered_elements):
                    _set_parameter_text(element, parameter_name, row.NewValue)

            self._preview_rows = rows
            self.PreviewGrid.ItemsSource = rows
            self._set_status("Renumbered {} element(s).".format(len(rows)))
        except Exception as ex:
            _safe_alert("Renumbering failed.\n\n{}".format(ex))


def main():
    if not doc:
        forms.alert("Open a Revit document first.", title=__title__, exitscript=True)

    xaml_path = script.get_bundle_file("RenumberBySpline.xaml")
    if not xaml_path:
        forms.alert("Renumber by Spline UI file was not found.", title=__title__, exitscript=True)

    try:
        window = RenumberBySplineWindow(xaml_path)
        window.ShowDialog()
    except Exception as ex:
        forms.alert("Renumber by Spline could not be opened.\n\n{}".format(ex), title=__title__, exitscript=True)


if __name__ == "__main__":
    main()