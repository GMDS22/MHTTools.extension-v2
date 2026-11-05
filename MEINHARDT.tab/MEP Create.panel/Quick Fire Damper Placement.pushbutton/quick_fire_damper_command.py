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
    SubTransaction,
    Transaction,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException, RegenerationFailedException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List

THIS_DIR = os.path.dirname(__file__)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from placement_rules import (
    DEFAULT_DUPLICATE_RADIUS_MM,
    DEFAULT_ELBOW_CLEARANCE_MM,
    bounded_curve_candidates,
    classify_instance_status,
    millimeters_to_feet,
    points_within_radius,
    closest_clear_point,
)
from wall_classification import classify_wall_descriptors

logger = script.get_logger()
RATED_CLASSIFICATIONS = ("FIRE", "SMOKE", "BOTH")
GEOMETRY_TOLERANCE_FEET = 0.01
BOUNDING_BOX_PADDING_FEET = 0.1
ELBOW_CLEARANCE_FEET = DEFAULT_ELBOW_CLEARANCE_MM / 304.8
FALLBACK_DISTANCE_FEET = millimeters_to_feet(DEFAULT_ELBOW_CLEARANCE_MM)
FALLBACK_STEP_FEET = millimeters_to_feet(10.0)


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


def _choose_wall_mode():
    return forms.CommandSwitchWindow.show(
        ["Rated walls only", "All actual wall crossings (force placement)"],
        message="Choose which actual duct/wall crossings to check:",
        title="Wall crossing mode",
    )


def _bbox_bounds(bounding_box, transform=None):
    if bounding_box is None:
        return None
    box_transform = bounding_box.Transform
    if transform is not None and box_transform is not None:
        box_transform = transform.Multiply(box_transform)
    elif transform is not None:
        box_transform = transform
    points = []
    for x_value in (bounding_box.Min.X, bounding_box.Max.X):
        for y_value in (bounding_box.Min.Y, bounding_box.Max.Y):
            for z_value in (bounding_box.Min.Z, bounding_box.Max.Z):
                point = DB.XYZ(x_value, y_value, z_value)
                points.append(box_transform.OfPoint(point) if box_transform is not None else point)
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


def _bounds_overlap(first, second):
    if first is None or second is None:
        return False
    return all(
        first[0][axis] < second[1][axis] and second[0][axis] < first[1][axis]
        for axis in range(3)
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


def _structural_material_text(wall_type, source_document):
    try:
        parameter_id = getattr(DB.BuiltInParameter, "STRUCTURAL_MATERIAL_PARAM", None)
        parameter = wall_type.get_Parameter(parameter_id) if parameter_id is not None else None
        if parameter is None:
            parameter = wall_type.LookupParameter("Structural Material")
        if parameter is None:
            return ""
        values = []
        try:
            if parameter.StorageType == DB.StorageType.ElementId:
                material = source_document.GetElement(parameter.AsElementId())
                if material is not None:
                    values.append(material.Name)
        except Exception:
            pass
        try:
            value = parameter.AsString() or parameter.AsValueString()
            if value:
                values.append(value)
        except Exception:
            pass
        return " ".join(values)
    except Exception:
        return ""


def _wall_rating(wall, document):
    try:
        wall_type = document.GetElement(wall.GetTypeId())
    except Exception:
        wall_type = None
    values = []
    if wall_type is not None:
        try:
            if wall_type.Name:
                values.append(wall_type.Name)
        except Exception:
            pass
        material_text = _structural_material_text(wall_type, document)
        if material_text:
            values.append(material_text)
    for name in ("NWB_Material", "NWB_MATERIAL"):
        for element in (wall, wall_type):
            if element is None:
                continue
            value = _parameter_text(element, name)
            if value:
                values.append(value)
    return classify_wall_descriptors(values)


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


def _connected_elbow_points(duct):
    points = []
    seen = set()
    try:
        connectors = duct.ConnectorManager.Connectors
    except Exception:
        return points
    for connector in connectors:
        try:
            references = connector.AllRefs
        except Exception:
            continue
        for reference in references:
            try:
                fitting = reference.Owner
                fitting_id = _id_value(fitting.Id)
                if fitting_id in seen or fitting_id == _id_value(duct.Id):
                    continue
                if not _category_is(fitting, BuiltInCategory.OST_DuctFitting):
                    continue
                part_type = fitting.MEPModel.PartType
                if str(part_type).lower().split(".")[-1] != "elbow":
                    continue
                try:
                    points.append(_point_tuple(reference.Origin))
                    seen.add(fitting_id)
                    continue
                except Exception:
                    pass
                location = fitting.Location
                if hasattr(location, "Point"):
                    points.append(_point_tuple(location.Point))
                    seen.add(fitting_id)
                    continue
                fitting_connectors = fitting.MEPModel.ConnectorManager.Connectors
                origins = [_point_tuple(item.Origin) for item in fitting_connectors]
                if origins:
                    points.append(tuple(sum(point[index] for point in origins) / len(origins) for index in range(3)))
                    seen.add(fitting_id)
            except Exception:
                continue
    return points


def _scan_duct(document, view, duct, curve, duct_bounds, force_all_walls=False, elbow_skips=None):
    candidates = []
    host_outline = _outline(duct_bounds, BOUNDING_BOX_PADDING_FEET)
    for wall in _collect_walls(document, view.Id, host_outline):
        rating = _wall_rating(wall, document) if not force_all_walls else None
        if force_all_walls or rating in RATED_CLASSIFICATIONS:
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
                rating = _wall_rating(wall, linked_document) if not force_all_walls else None
                if force_all_walls or rating in RATED_CLASSIFICATIONS:
                    candidates.append((wall, link_transform, linked_document, "linked"))
        except RegenerationFailedException:
            raise
        except Exception as exc:
            logger.warning("Could not scan nearby walls in linked model: {}".format(exc))

    options = SolidCurveIntersectionOptions()
    options.ResultType = SolidCurveIntersectionMode.CurveSegmentsInside
    crossings = []
    elbow_points = _connected_elbow_points(duct)
    for wall, transform, wall_document, source in candidates:
        try:
            wall_bounds = _bbox_bounds(wall.get_BoundingBox(None), transform)
        except RegenerationFailedException:
            raise
        except Exception:
            wall_bounds = None
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
                    segment = intersections.GetCurveSegment(segment_index)
                    midpoint = segment.Evaluate(0.5, True)
                    candidates_for_crossing = []
                    if elbow_points:
                        curve_samples = [
                            _point_tuple(segment.Evaluate(sample_index / 100.0, True))
                            for sample_index in range(101)
                        ]
                        coordinates = closest_clear_point(
                            curve_samples,
                            elbow_points,
                            ELBOW_CLEARANCE_FEET,
                        )
                        if coordinates is None:
                            curve_length = float(curve.Length)
                            start_projection = curve.Project(segment.Evaluate(0.0, True))
                            end_projection = curve.Project(segment.Evaluate(1.0, True))
                            if curve_length > 0 and start_projection is not None and end_projection is not None:
                                start_distance = (
                                    float(curve.ComputeNormalizedParameter(start_projection.Parameter))
                                    * curve_length
                                )
                                end_distance = (
                                    float(curve.ComputeNormalizedParameter(end_projection.Parameter))
                                    * curve_length
                                )
                                fallback_points = bounded_curve_candidates(
                                    lambda distance: _point_tuple(
                                        curve.Evaluate(distance / curve_length, True)
                                    ),
                                    start_distance,
                                    end_distance,
                                    curve_length,
                                    elbow_points,
                                    ELBOW_CLEARANCE_FEET,
                                    FALLBACK_DISTANCE_FEET,
                                    FALLBACK_STEP_FEET,
                                )
                                candidates_for_crossing = [
                                    {"point": candidate[0], "adjusted": True}
                                    for candidate in fallback_points
                                ]
                            if elbow_skips is not None:
                                if not candidates_for_crossing:
                                    try:
                                        skipped_label = wall_document.GetElement(wall.GetTypeId()).Name
                                    except Exception:
                                        skipped_label = str(_id_value(wall.Id))
                                    elbow_skips.append(
                                        "Duct {} crossing wall '{}' skipped: no point within the wall or within {} mm beyond it clears every connected elbow.".format(
                                            _id_value(duct.Id),
                                            skipped_label,
                                            int(DEFAULT_ELBOW_CLEARANCE_MM),
                                        )
                                    )
                            if not candidates_for_crossing:
                                continue
                        else:
                            candidates_for_crossing = [{"point": coordinates, "adjusted": False}]
                    else:
                        coordinates = _point_tuple(midpoint)
                        candidates_for_crossing = [{"point": coordinates, "adjusted": False}]
                    coordinates = candidates_for_crossing[0]["point"]
                    if any(
                        points_within_radius(
                            coordinates, crossing["point"], GEOMETRY_TOLERANCE_FEET
                        )
                        for crossing in crossings
                    ):
                        continue
                    point = DB.XYZ(coordinates[0], coordinates[1], coordinates[2])
                    projection = curve.Project(point)
                    parameter = float(projection.Parameter) if projection is not None else 0.0
                    try:
                        wall_label = wall_document.GetElement(wall.GetTypeId()).Name
                    except Exception:
                        wall_label = str(_id_value(wall.Id))
                    crossings.append({
                        "point": coordinates,
                        "parameter": parameter,
                        "wall_label": wall_label,
                        "source": source,
                        "wall_bounds": wall_bounds,
                        "candidates": candidates_for_crossing,
                    })
            except RegenerationFailedException:
                raise
            except Exception as exc:
                logger.warning("Curve/solid intersection failed for duct {} and wall {}: {}".format(
                    _id_value(duct.Id), _id_value(wall.Id), exc
                ))
    crossings.sort(key=lambda crossing: crossing["parameter"])
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
    except Exception as exc:
        logger.warning("Could not verify the active Revit project and view: {}".format(exc))
        return False


def _instance_connected_to_duct(instance, duct_id):
    try:
        connectors = instance.MEPModel.ConnectorManager.Connectors
    except Exception:
        return False
    for connector in connectors:
        try:
            if not connector.IsConnected:
                continue
            for reference in connector.AllRefs:
                try:
                    if str(reference.ConnectorType).lower().endswith("logical"):
                        continue
                    if _id_value(reference.Owner.Id) == duct_id:
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _inspect_instance_persistence(document, record):
    element_id = record["element_id"]
    duct_id = record["duct_id"]
    diagnostic = {
        "element_id": _id_value(element_id),
        "duct_id": duct_id,
        "host_id": None,
        "connected": False,
        "status": "missing",
    }
    try:
        instance = document.GetElement(element_id)
    except Exception as exc:
        diagnostic["status"] = "lookup-error"
        diagnostic["detail"] = str(exc)
        return diagnostic
    exists = instance is not None
    is_valid = False
    is_family_instance = False
    is_accessory = False
    hosted_on_duct = False
    connected_to_duct = False
    if exists:
        try:
            is_valid = bool(instance.IsValidObject)
        except Exception:
            pass
        is_family_instance = isinstance(instance, DB.FamilyInstance)
        is_accessory = _category_is(instance, BuiltInCategory.OST_DuctAccessory)
        if is_valid and is_family_instance:
            try:
                host = instance.Host
                if host is not None:
                    diagnostic["host_id"] = _id_value(host.Id)
                    hosted_on_duct = diagnostic["host_id"] == duct_id
            except Exception:
                pass
            connected_to_duct = _instance_connected_to_duct(instance, duct_id)
    diagnostic["connected"] = connected_to_duct
    diagnostic["status"] = classify_instance_status(
        exists,
        is_valid,
        is_family_instance,
        is_accessory,
        hosted_on_duct,
        connected_to_duct,
    )
    return diagnostic


def _format_instance_diagnostic(diagnostic):
    return "Instance {}: status={}, intended duct={}, host={}, connected={}".format(
        diagnostic["element_id"],
        diagnostic["status"],
        diagnostic["duct_id"],
        diagnostic["host_id"] if diagnostic["host_id"] is not None else "none",
        diagnostic["connected"],
    )


def _log_post_summary_diagnostics(document, records):
    diagnostics = [_inspect_instance_persistence(document, record) for record in records]
    if not diagnostics:
        return diagnostics
    lines = [_format_instance_diagnostic(item) for item in diagnostics]
    for line in lines:
        logger.info("Post-summary persistence: {}".format(line))
    try:
        script.get_output().print_md("### Post-summary persistence check\n\n" + "\n\n".join(lines))
    except Exception as exc:
        logger.warning("Could not print persistence diagnostics to the pyRevit output: {}".format(exc))
    return diagnostics


def _select_placed_instances(document, view_id, placed_ids):
    if not placed_ids:
        return None
    if not _current_context_matches(document, view_id):
        return "The active project or view changed; placed instances were not selected."

    selection_ids = List[DB.ElementId]()
    for element_id in placed_ids:
        try:
            instance = document.GetElement(element_id)
            if (
                instance is not None
                and instance.IsValidObject
                and isinstance(instance, DB.FamilyInstance)
            ):
                selection_ids.Add(instance.Id)
        except Exception:
            continue
    if selection_ids.Count == 0:
        return "Committed instances could not be reacquired for selection."
    try:
        uidocument = revit.uidoc
        if uidocument is None or not _current_context_matches(document, view_id):
            return "The active project or view changed; placed instances were not selected."
        uidocument.Selection.SetElementIds(selection_ids)
    except Exception as exc:
        logger.warning("Could not select committed damper instances: {}".format(exc))
        return "Committed instances were placed, but Revit could not select them."
    return None


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


def _rollback_subtransaction(subtransaction):
    try:
        if subtransaction is None:
            return False
        status = subtransaction.GetStatus()
        if status == DB.TransactionStatus.Started:
            subtransaction.RollBack()
            status = subtransaction.GetStatus()
        return status == DB.TransactionStatus.RolledBack
    except Exception as exc:
        logger.error("Could not confirm rollback of a damper candidate: {}".format(exc))
    return False


def _place_on_duct(document, duct_id, crossings, symbol_id, radius_feet, view_id):
    duct = document.GetElement(DB.ElementId(duct_id))
    symbol = document.GetElement(DB.ElementId(symbol_id))
    if duct is None or symbol is None or not _category_is(duct, BuiltInCategory.OST_DuctCurves):
        raise RuntimeError("The selected duct or accessory type is no longer available.")

    existing_points = _existing_symbol_points(document, duct, symbol_id, radius_feet)
    if not any(
        not any(points_within_radius(candidate["point"], existing, radius_feet) for existing in existing_points)
        for crossing in crossings
        for candidate in crossing["candidates"]
    ):
        return [], len(crossings), [], []

    transaction = Transaction(document, "Place dampers on duct {}".format(duct_id))
    duplicate_count = 0
    placement_skips = []
    created_records = []
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
        placed_points = []
        for crossing in crossings:
            accepted = False
            all_duplicate = True
            candidate_errors = []
            for candidate in crossing["candidates"]:
                coordinates = candidate["point"]
                if any(
                    points_within_radius(coordinates, existing, radius_feet)
                    for existing in existing_points + placed_points
                ):
                    continue
                all_duplicate = False
                subtransaction = SubTransaction(document)
                sub_status = subtransaction.Start()
                if sub_status != DB.TransactionStatus.Started:
                    raise RuntimeError(
                        "Revit did not start a damper candidate subtransaction ({})".format(sub_status)
                    )
                try:
                    location = DB.XYZ(coordinates[0], coordinates[1], coordinates[2])
                    instance = document.Create.NewFamilyInstance(
                        location,
                        symbol,
                        duct,
                        StructuralType.NonStructural,
                    )
                    document.Regenerate()
                    orientation_note = (
                        "Instance {} retained Revit's host orientation; family-specific roll data is unavailable."
                    ).format(_id_value(instance.Id))
                    if candidate["adjusted"]:
                        instance_bounds = _bbox_bounds(instance.get_BoundingBox(None))
                        if not _bounds_overlap(instance_bounds, crossing["wall_bounds"]):
                            if not _rollback_subtransaction(subtransaction):
                                raise _TransactionRecoveryError(
                                    "The damper candidate outside the wall could not be confirmed rolled back."
                                )
                            candidate_errors.append("the family bounding box did not overlap the wall")
                            continue
                    sub_status = subtransaction.Commit()
                    if sub_status == DB.TransactionStatus.Pending:
                        raise _TransactionPendingError(
                            "Revit is still resolving transaction failures for duct {}.".format(duct_id)
                        )
                    if sub_status != DB.TransactionStatus.Committed:
                        raise RuntimeError(
                            "Revit did not commit a damper candidate ({})".format(sub_status)
                        )
                    placed_points.append(coordinates)
                    created_records.append({
                        "element_id": instance.Id,
                        "adjusted": candidate["adjusted"],
                        "orientation_note": orientation_note,
                    })
                    accepted = True
                    break
                except _TransactionPendingError:
                    raise
                except RegenerationFailedException:
                    raise
                except _TransactionRecoveryError:
                    raise
                except Exception as exc:
                    if not _rollback_subtransaction(subtransaction):
                        raise _TransactionRecoveryError(
                            "A failed damper candidate could not be confirmed rolled back: {}".format(exc)
                        )
                    candidate_errors.append(str(exc))
            if not accepted:
                if all_duplicate:
                    duplicate_count += 1
                else:
                    reason = candidate_errors[0] if candidate_errors else "no safe candidate could be committed"
                    placement_skips.append(
                        "Duct {} crossing wall '{}' skipped: {}.".format(
                            duct_id, crossing["wall_label"], reason
                        )
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

        orientation_notes = []
        for record in created_records:
            if record["orientation_note"]:
                orientation_notes.append(record["orientation_note"])
        return (
            created_records,
            duplicate_count,
            placement_skips,
            orientation_notes,
        )
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
    wall_mode = _choose_wall_mode()
    if wall_mode is None:
        return
    force_all_walls = wall_mode == "All actual wall crossings (force placement)"

    if not _current_context_matches(document, view_id):
        forms.alert("The active project or view changed. Run the tool again in the target view.", exitscript=False)
        return

    duct_runs = []
    scan_errors = []
    elbow_skips = []
    for duct in ducts:
        try:
            location = duct.Location
            curve = getattr(location, "Curve", None)
            bounds = _bbox_bounds(duct.get_BoundingBox(None))
            if curve is None or bounds is None:
                scan_errors.append("Duct {} has no usable curve or bounding box.".format(_id_value(duct.Id)))
                duct_runs.append((_id_value(duct.Id), []))
                continue
            crossings = _scan_duct(
                document,
                view,
                duct,
                curve,
                bounds,
                force_all_walls=force_all_walls,
                elbow_skips=elbow_skips,
            )
            duct_runs.append((_id_value(duct.Id), crossings))
        except RegenerationFailedException:
            raise
        except Exception as exc:
            scan_errors.append("Duct {} scan failed: {}".format(_id_value(duct.Id), exc))
            logger.warning(scan_errors[-1])
            duct_runs.append((_id_value(duct.Id), []))

    total_crossings = sum(len(crossings) for duct_id, crossings in duct_runs)
    committed_records = []
    duplicates = 0
    adjusted = 0
    failed_ducts = len(scan_errors)
    placement_skips = []
    orientation_notes = []
    stopped = False
    for duct_id, crossings in duct_runs:
        if not _current_context_matches(document, view_id):
            scan_errors.append("The active project or view changed; remaining ducts were not modified.")
            stopped = True
            break
        if not crossings:
            continue
        try:
            created_records, duplicate_count, skipped, orientation = _place_on_duct(
                document,
                duct_id,
                crossings,
                _id_value(choice.Symbol.Id),
                radius_feet,
                view_id,
            )
            for record in created_records:
                committed_record = dict(record)
                committed_record["duct_id"] = duct_id
                committed_records.append(committed_record)
            duplicates += duplicate_count
            placement_skips.extend(skipped)
            orientation_notes.extend(orientation)
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

    if committed_records:
        forms.alert(
            "Duct transactions returned Committed for {} instance(s). Click OK to run the persistence check; no placement count is final yet.".format(
                len(committed_records)
            ),
            title="Quick Fire Damper Placement",
            exitscript=False,
        )
    pre_summary_diagnostics = [
        _inspect_instance_persistence(document, record) for record in committed_records
    ]
    persisted_statuses = ("hosted", "connected")
    persisted_ids = [
        item["element_id"]
        for item in pre_summary_diagnostics
        if item["status"] in persisted_statuses
    ]
    adjusted = sum(
        1
        for record, diagnostic in zip(committed_records, pre_summary_diagnostics)
        if record["adjusted"] and diagnostic["status"] in persisted_statuses
    )
    selection_warning = _select_placed_instances(
        document,
        view_id,
        [DB.ElementId(element_id) for element_id in persisted_ids],
    )
    placed_ids_text = ", ".join(str(element_id) for element_id in persisted_ids)
    summary = (
        "Checked {} ducts; found {} {} crossings; placed {} dampers; "
        "skipped {} duplicates and {} crossings without elbow-safe fit; "
        "adjusted {} placements by up to {} mm; {} crossings had no valid candidate placement; "
        "{} ducts had errors.\nPlaced instance IDs: {}."
    ).format(
        len(duct_runs),
        total_crossings,
        "actual wall" if force_all_walls else "rated-wall",
        len(persisted_ids),
        duplicates,
        len(elbow_skips),
        adjusted,
        int(DEFAULT_ELBOW_CLEARANCE_MM),
        len(placement_skips),
        failed_ducts,
        placed_ids_text or "none persisted on or connected to the intended duct",
    )
    if elbow_skips:
        summary += "\n\nFirst elbow clearance skip: {}".format(elbow_skips[0])
        if len(elbow_skips) > 1:
            summary += "\n{} additional elbow-related crossing(s) were skipped.".format(len(elbow_skips) - 1)
    if placement_skips:
        summary += "\n\nFirst adjusted-placement skip: {}".format(placement_skips[0])
        if len(placement_skips) > 1:
            summary += "\n{} additional adjusted candidate(s) were skipped.".format(len(placement_skips) - 1)
    if orientation_notes and persisted_ids:
        summary += (
            "\n\nOrientation note: Revit's host orientation was retained. No family-specific roll data "
            "is available, so non-square family orientation must be checked in Revit."
        )
    if pre_summary_diagnostics:
        summary += "\n\nPersistence status after the verification prompt:\n{}".format(
            "\n".join(_format_instance_diagnostic(item) for item in pre_summary_diagnostics)
        )
    if selection_warning:
        summary += "\n\n{}".format(selection_warning)
    if stopped:
        summary += "\nProcessing stopped because the active project or view changed."
    if scan_errors:
        summary += "\n\nFirst issue: {}".format(scan_errors[0])
        if len(scan_errors) > 1:
            summary += "\n{} additional issue(s) were written to the pyRevit log.".format(len(scan_errors) - 1)
    forms.alert(summary, title="Quick Fire Damper Placement", exitscript=False)
    post_summary_diagnostics = _log_post_summary_diagnostics(document, committed_records)
    changed_diagnostics = [
        (before, after)
        for before, after in zip(pre_summary_diagnostics, post_summary_diagnostics)
        if before["status"] != after["status"]
        or before["host_id"] != after["host_id"]
        or before["connected"] != after["connected"]
    ]
    if changed_diagnostics:
        changed_lines = [
            "{} -> {}".format(
                _format_instance_diagnostic(before),
                _format_instance_diagnostic(after),
            )
            for before, after in changed_diagnostics
        ]
        forms.alert(
            "Instance state changed after the summary was dismissed. See the pyRevit output for the full post-summary check.\n\n{}".format(
                "\n".join(changed_lines)
            ),
            title="Quick Fire Damper Placement Diagnostics",
            exitscript=False,
        )


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
