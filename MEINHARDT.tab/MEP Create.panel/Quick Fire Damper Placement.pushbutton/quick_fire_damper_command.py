# -*- coding: utf-8 -*-
"""Synchronous Quick Fire Damper Placement command implementation."""

import os
import sys

from pyrevit import DB, forms, revit, script
from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    Options,
    SolidCurveIntersectionMode,
    SolidCurveIntersectionOptions,
    SolidUtils,
    Transaction,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException, RegenerationFailedException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

THIS_DIR = os.path.dirname(__file__)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from placement_rules import (
    DEFAULT_DUPLICATE_RADIUS_MM,
    millimeters_to_feet,
    points_within_radius,
)
from wall_classification import classify_wall_material

logger = script.get_logger()
RATED_CLASSIFICATIONS = ("FIRE", "SMOKE", "BOTH")
GEOMETRY_TOLERANCE_FEET = 0.01
BOUNDING_BOX_PADDING_FEET = 0.1


def _id_value(element_id):
    try:
        return int(element_id.IntegerValue)
    except Exception:
        return int(str(element_id))


def _category_is(element, category):
    try:
        return element.Category is not None and _id_value(element.Category.Id) == int(category)
    except Exception:
        return False


class _DuctSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return _category_is(element, BuiltInCategory.OST_DuctCurves)

    def AllowReference(self, reference, position):
        return False


class _SymbolChoice(object):
    def __init__(self, symbol):
        self.Symbol = symbol
        try:
            family_name = symbol.Family.Name
        except Exception:
            family_name = "Duct Accessory"
        try:
            type_name = symbol.Name
        except Exception:
            type_name = str(_id_value(symbol.Id))
        self.DisplayName = "{} : {}".format(family_name, type_name)


class _TransactionRecoveryError(RuntimeError):
    pass


class _TransactionPendingError(RuntimeError):
    pass


def _active_view_duct_ids(document, view):
    elements = (
        FilteredElementCollector(document, view.Id)
        .OfCategory(BuiltInCategory.OST_DuctCurves)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    return set(_id_value(element.Id) for element in elements)


def _ducts_from_ids(document, ids, view):
    visible_ids = _active_view_duct_ids(document, view)
    ducts = []
    seen = set()
    for element_id in ids:
        try:
            duct = document.GetElement(element_id)
            key = _id_value(duct.Id) if duct is not None else None
            if duct is None or key in seen or key not in visible_ids:
                continue
            if _category_is(duct, BuiltInCategory.OST_DuctCurves):
                ducts.append(duct)
                seen.add(key)
        except Exception:
            continue
    return ducts


def _choose_ducts(document, uidocument, view):
    try:
        selected_ids = list(uidocument.Selection.GetElementIds())
        preselected = _ducts_from_ids(document, selected_ids, view)
        if preselected:
            return preselected
    except Exception as exc:
        logger.warning("Could not read the current selection: {}".format(exc))

    try:
        references = uidocument.Selection.PickObjects(
            ObjectType.Element,
            _DuctSelectionFilter(),
            "Select duct curves, then click Finish.",
        )
    except OperationCanceledException:
        return []
    return _ducts_from_ids(document, [reference.ElementId for reference in references], view)


def _choose_symbol(document):
    symbols = (
        FilteredElementCollector(document)
        .OfCategory(BuiltInCategory.OST_DuctAccessory)
        .WhereElementIsElementType()
        .ToElements()
    )
    choices = []
    for symbol in symbols:
        try:
            if isinstance(symbol, DB.FamilySymbol):
                choices.append(_SymbolChoice(symbol))
        except Exception:
            continue
    choices.sort(key=lambda choice: choice.DisplayName.lower())
    if not choices:
        forms.alert("No loaded Duct Accessory family types were found in this project.", exitscript=False)
        return None
    return forms.SelectFromList.show(
        choices,
        name_attr="DisplayName",
        title="Choose damper type",
        button_name="Place dampers",
        multiselect=False,
    )


def _choose_duplicate_radius():
    while True:
        value = forms.ask_for_string(
            default=str(DEFAULT_DUPLICATE_RADIUS_MM),
            prompt="Skip this damper type when it is already on the same duct within this distance (mm).",
            title="Duplicate spacing",
        )
        if value is None:
            return None
        try:
            return millimeters_to_feet(value)
        except (TypeError, ValueError):
            forms.alert("Enter a positive, finite distance in millimeters.", exitscript=False)


def _bbox_bounds(bounding_box, transform=None):
    if bounding_box is None:
        return None
    if transform is None:
        transform = bounding_box.Transform
    points = []
    for x_value in (bounding_box.Min.X, bounding_box.Max.X):
        for y_value in (bounding_box.Min.Y, bounding_box.Max.Y):
            for z_value in (bounding_box.Min.Z, bounding_box.Max.Z):
                point = DB.XYZ(x_value, y_value, z_value)
                points.append(transform.OfPoint(point) if transform is not None else point)
    return (
        (
            min(point.X for point in points),
            min(point.Y for point in points),
            min(point.Z for point in points),
        ),
        (
            max(point.X for point in points),
            max(point.Y for point in points),
            max(point.Z for point in points),
        ),
    )


def _outline(bounds, padding=0.0):
    minimum = DB.XYZ(
        bounds[0][0] - padding,
        bounds[0][1] - padding,
        bounds[0][2] - padding,
    )
    maximum = DB.XYZ(
        bounds[1][0] + padding,
        bounds[1][1] + padding,
        bounds[1][2] + padding,
    )
    return DB.Outline(minimum, maximum)


def _transform_bounds(bounds, transform):
    points = []
    for x_value in (bounds[0][0], bounds[1][0]):
        for y_value in (bounds[0][1], bounds[1][1]):
            for z_value in (bounds[0][2], bounds[1][2]):
                points.append(transform.OfPoint(DB.XYZ(x_value, y_value, z_value)))
    return (
        (
            min(point.X for point in points),
            min(point.Y for point in points),
            min(point.Z for point in points),
        ),
        (
            max(point.X for point in points),
            max(point.Y for point in points),
            max(point.Z for point in points),
        ),
    )


def _parameter_text(element, parameter_name):
    try:
        parameter = element.LookupParameter(parameter_name)
        if parameter is None:
            return ""
        value = parameter.AsString() or parameter.AsValueString()
        return value.strip() if value else ""
    except Exception:
        return ""


def _wall_rating(wall, document):
    try:
        wall_type = document.GetElement(wall.GetTypeId())
    except Exception:
        wall_type = None
    values = []
    for name in ("NWB_Material", "NWB_MATERIAL"):
        value = _parameter_text(wall, name)
        if not value and wall_type is not None:
            value = _parameter_text(wall_type, name)
        if value:
            values.append(value)
    return classify_wall_material(" ".join(values))


def _collect_walls(document, view_id, outline):
    if view_id is None:
        collector = FilteredElementCollector(document)
    else:
        collector = FilteredElementCollector(document, view_id)
    return (
        collector.OfCategory(BuiltInCategory.OST_Walls)
        .WhereElementIsNotElementType()
        .WherePasses(DB.BoundingBoxIntersectsFilter(outline))
        .ToElements()
    )


def _visible_links(document, view):
    links = (
        FilteredElementCollector(document, view.Id)
        .OfCategory(BuiltInCategory.OST_RvtLinks)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for link in links:
        if not isinstance(link, DB.RevitLinkInstance):
            continue
        try:
            if link.IsHidden(view):
                continue
            linked_document = link.GetLinkDocument()
            if linked_document is not None and linked_document.IsValidObject:
                yield linked_document, link.GetTotalTransform()
        except RegenerationFailedException:
            raise
        except Exception as exc:
            logger.warning("Skipping unavailable Revit link: {}".format(exc))


def _geometry_solids(element):
    options = Options()
    options.ComputeReferences = False
    geometry = element.get_Geometry(options)
    solids = []
    for item in geometry or []:
        if isinstance(item, DB.Solid):
            if item.Volume > 1e-9:
                solids.append(item)
        elif isinstance(item, DB.GeometryInstance):
            for instance_item in item.GetInstanceGeometry():
                if isinstance(instance_item, DB.Solid) and instance_item.Volume > 1e-9:
                    solids.append(instance_item)
    return solids


def _point_tuple(point):
    return (float(point.X), float(point.Y), float(point.Z))


def _scan_duct(document, view, duct, curve, duct_bounds):
    candidates = []
    host_outline = _outline(duct_bounds, BOUNDING_BOX_PADDING_FEET)
    for wall in _collect_walls(document, view.Id, host_outline):
        rating = _wall_rating(wall, document)
        if rating in RATED_CLASSIFICATIONS:
            candidates.append((wall, None, document, "host"))

    for linked_document, link_transform in _visible_links(document, view):
        try:
            link_bounds = _transform_bounds(duct_bounds, link_transform.Inverse)
            link_walls = _collect_walls(
                linked_document,
                None,
                _outline(link_bounds, BOUNDING_BOX_PADDING_FEET),
            )
            for wall in link_walls:
                rating = _wall_rating(wall, linked_document)
                if rating in RATED_CLASSIFICATIONS:
                    candidates.append((wall, link_transform, linked_document, "linked"))
        except RegenerationFailedException:
            raise
        except Exception as exc:
            logger.warning("Could not scan nearby walls in linked model: {}".format(exc))

    options = SolidCurveIntersectionOptions()
    options.ResultType = SolidCurveIntersectionMode.CurveSegmentsInside
    crossings = []
    for wall, transform, wall_document, source in candidates:
        try:
            solids = _geometry_solids(wall)
        except RegenerationFailedException:
            raise
        except Exception as exc:
            logger.warning("Could not read geometry for rated {} wall {}: {}".format(
                source, _id_value(wall.Id), exc
            ))
            continue
        for solid in solids:
            try:
                host_solid = SolidUtils.CreateTransformed(solid, transform) if transform is not None else solid
                intersections = host_solid.IntersectWithCurve(curve, options)
                for segment_index in range(intersections.SegmentCount):
                    point = intersections.GetCurveSegment(segment_index).Evaluate(0.5, True)
                    coordinates = _point_tuple(point)
                    if any(
                        points_within_radius(coordinates, crossing[0], GEOMETRY_TOLERANCE_FEET)
                        for crossing in crossings
                    ):
                        continue
                    projection = curve.Project(point)
                    parameter = float(projection.Parameter) if projection is not None else 0.0
                    try:
                        wall_label = wall_document.GetElement(wall.GetTypeId()).Name
                    except Exception:
                        wall_label = str(_id_value(wall.Id))
                    crossings.append((coordinates, parameter, wall_label, source))
            except RegenerationFailedException:
                raise
            except Exception as exc:
                logger.warning("Curve/solid intersection failed for duct {} and wall {}: {}".format(
                    _id_value(duct.Id), _id_value(wall.Id), exc
                ))
    crossings.sort(key=lambda crossing: crossing[1])
    return crossings


def _existing_symbol_points(document, duct, symbol_id, radius_feet):
    try:
        bounds = _bbox_bounds(duct.get_BoundingBox(None))
    except Exception:
        bounds = None
    if bounds is not None:
        accessory_filter = DB.ElementCategoryFilter(
            DB.ElementId(int(BuiltInCategory.OST_DuctAccessory))
        )
        accessories = (
            FilteredElementCollector(document)
            .WherePasses(accessory_filter)
            .WherePasses(DB.BoundingBoxIntersectsFilter(_outline(bounds, radius_feet)))
            .WhereElementIsNotElementType()
            .ToElements()
        )
    else:
        accessory_filter = DB.ElementCategoryFilter(
            DB.ElementId(int(BuiltInCategory.OST_DuctAccessory))
        )
        accessories = [
            document.GetElement(element_id)
            for element_id in duct.GetDependentElements(accessory_filter)
        ]

    points = []
    for accessory in accessories:
        try:
            if not isinstance(accessory, DB.FamilyInstance):
                continue
            host = accessory.Host
            if host is None or _id_value(host.Id) != _id_value(duct.Id):
                continue
            if _id_value(accessory.Symbol.Id) != symbol_id:
                continue
            location = accessory.Location
            if hasattr(location, "Point"):
                points.append(_point_tuple(location.Point))
        except Exception:
            continue
    return points


def _current_context_matches(expected_document, expected_view_id):
    try:
        current_uidocument = revit.uidoc
        current_document = current_uidocument.Document if current_uidocument else None
        if current_document is None or not current_document.IsValidObject:
            return False
        if current_document != expected_document or not expected_document.IsValidObject:
            return False
        return _id_value(current_uidocument.ActiveView.Id) == expected_view_id
    except Exception:
        return False


def _rollback(transaction):
    try:
        if transaction is None:
            return False
        status = transaction.GetStatus()
        if status == DB.TransactionStatus.Started:
            transaction.RollBack()
            status = transaction.GetStatus()
        return status == DB.TransactionStatus.RolledBack
    except Exception as exc:
        logger.error("Could not roll back a failed duct transaction: {}".format(exc))
    return False


def _place_on_duct(document, duct_id, crossings, symbol_id, radius_feet, view_id):
    duct = document.GetElement(DB.ElementId(duct_id))
    symbol = document.GetElement(DB.ElementId(symbol_id))
    if duct is None or symbol is None or not _category_is(duct, BuiltInCategory.OST_DuctCurves):
        raise RuntimeError("The selected duct or accessory type is no longer available.")

    existing_points = _existing_symbol_points(document, duct, symbol_id, radius_feet)
    planned_points = []
    for crossing in crossings:
        point = crossing[0]
        if any(
            points_within_radius(point, existing, radius_feet)
            for existing in existing_points + planned_points
        ):
            continue
        planned_points.append(point)
    if not planned_points:
        return 0

    transaction = Transaction(document, "Place dampers on duct {}".format(duct_id))
    try:
        failure_options = transaction.GetFailureHandlingOptions()
        failure_options.SetForcedModalHandling(True)
        transaction.SetFailureHandlingOptions(failure_options)
        status = transaction.Start()
        if status != DB.TransactionStatus.Started:
            raise RuntimeError("Revit did not start the duct transaction ({})".format(status))
        if not symbol.IsActive:
            symbol.Activate()
            document.Regenerate()
        for coordinates in planned_points:
            location = DB.XYZ(coordinates[0], coordinates[1], coordinates[2])
            document.Create.NewFamilyInstance(
                location,
                symbol,
                duct,
                StructuralType.NonStructural,
            )
        if not _current_context_matches(document, view_id):
            raise RuntimeError("The active project or view changed before this duct could be committed.")
        status = transaction.Commit()
        if status == DB.TransactionStatus.Pending:
            raise _TransactionPendingError(
                "Revit is still resolving transaction failures for duct {}.".format(duct_id)
            )
        if status != DB.TransactionStatus.Committed:
            raise RuntimeError("Revit did not commit this duct transaction ({})".format(status))
        return len(planned_points)
    except _TransactionPendingError:
        raise
    except RegenerationFailedException:
        raise
    except Exception as exc:
        if not _rollback(transaction):
            raise _TransactionRecoveryError(
                "The failed duct transaction could not be confirmed rolled back: {}".format(exc)
            )
        raise


def main():
    document = revit.doc
    uidocument = revit.uidoc
    if document is None or uidocument is None:
        forms.alert("Open a Revit project before running Quick Fire Damper Placement.", exitscript=False)
        return

    view = uidocument.ActiveView
    view_id = _id_value(view.Id)
    ducts = _choose_ducts(document, uidocument, view)
    if not ducts:
        return

    choice = _choose_symbol(document)
    if choice is None:
        return
    radius_feet = _choose_duplicate_radius()
    if radius_feet is None:
        return

    if not _current_context_matches(document, view_id):
        forms.alert("The active project or view changed. Run the tool again in the target view.", exitscript=False)
        return

    duct_runs = []
    scan_errors = []
    for duct in ducts:
        try:
            location = duct.Location
            curve = getattr(location, "Curve", None)
            bounds = _bbox_bounds(duct.get_BoundingBox(None))
            if curve is None or bounds is None:
                scan_errors.append("Duct {} has no usable curve or bounding box.".format(_id_value(duct.Id)))
                duct_runs.append((_id_value(duct.Id), []))
                continue
            crossings = _scan_duct(document, view, duct, curve, bounds)
            duct_runs.append((_id_value(duct.Id), crossings))
        except RegenerationFailedException:
            raise
        except Exception as exc:
            scan_errors.append("Duct {} scan failed: {}".format(_id_value(duct.Id), exc))
            logger.warning(scan_errors[-1])
            duct_runs.append((_id_value(duct.Id), []))

    total_crossings = sum(len(crossings) for duct_id, crossings in duct_runs)
    placed = 0
    duplicates = 0
    failed_ducts = len(scan_errors)
    stopped = False
    for duct_id, crossings in duct_runs:
        if not _current_context_matches(document, view_id):
            scan_errors.append("The active project or view changed; remaining ducts were not modified.")
            stopped = True
            break
        if not crossings:
            continue
        try:
            count = _place_on_duct(
                document,
                duct_id,
                crossings,
                _id_value(choice.Symbol.Id),
                radius_feet,
                view_id,
            )
            placed += count
            duplicates += len(crossings) - count
        except _TransactionPendingError:
            return
        except RegenerationFailedException:
            raise
        except Exception as exc:
            failed_ducts += 1
            scan_errors.append("Duct {} placement failed and was rolled back: {}".format(duct_id, exc))
            logger.warning(scan_errors[-1])
            if isinstance(exc, _TransactionRecoveryError):
                stopped = True
                break
            if not _current_context_matches(document, view_id):
                stopped = True
                break

    summary = (
        "Checked {} ducts; found {} rated-wall crossings; placed {} dampers; "
        "skipped {} duplicates; {} ducts had errors."
    ).format(len(duct_runs), total_crossings, placed, duplicates, failed_ducts)
    if stopped:
        summary += "\nProcessing stopped because the active project or view changed."
    if scan_errors:
        summary += "\n\nFirst issue: {}".format(scan_errors[0])
        if len(scan_errors) > 1:
            summary += "\n{} additional issue(s) were written to the pyRevit log.".format(len(scan_errors) - 1)
    forms.alert(summary, title="Quick Fire Damper Placement", exitscript=False)


def run():
    try:
        main()
    except RegenerationFailedException:
        raise
    except Exception as exc:
        logger.exception("Quick Fire Damper Placement stopped unexpectedly.")
        forms.alert(
            "Quick Fire Damper Placement could not complete: {}".format(exc),
            title="Quick Fire Damper Placement",
            exitscript=False,
        )
