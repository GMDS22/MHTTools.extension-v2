# -*- coding: utf-8 -*-
"""Select active-view elements created by or currently owned by the user."""

from pyrevit import DB, forms, revit
from System.Collections.Generic import List

_CLOUD_MARGIN_FEET = 100.0 / 304.8


def _normalize_username(value):
    try:
        return (value or "").strip().lower()
    except Exception:
        return ""


def _collect_category_options(doc, view):
    categories = {}
    elements = DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for element in elements:
        try:
            category = element.Category
            if category is not None:
                categories[category.Id.IntegerValue] = category
        except Exception:
            continue

    name_counts = {}
    for category in categories.values():
        name = category.Name or "Unnamed category"
        name_counts[name] = name_counts.get(name, 0) + 1

    options = {}
    for category_id, category in categories.items():
        name = category.Name or "Unnamed category"
        label = "{} [{}]".format(name, category_id) if name_counts[name] > 1 else name
        options[label] = category.Id
    return options


def _pick_revision(doc):
    revisions = []
    for revision in DB.FilteredElementCollector(doc).OfClass(DB.Revision):
        try:
            if not revision.Issued:
                revisions.append(revision)
        except Exception:
            continue

    if not revisions:
        forms.alert("There are no unissued revisions available for new clouds.", title="My View Elements")
        return None

    revisions.sort(key=lambda item: item.SequenceNumber)
    labels = {}
    for revision in revisions:
        description = (revision.Description or "").strip() or "No description"
        label = "Revision {} | {}".format(revision.SequenceNumber, description)
        if label in labels:
            label = "{} [ID {}]".format(label, revision.Id.IntegerValue)
        labels[label] = revision

    selected_label = forms.SelectFromList.show(
        sorted(labels.keys(), key=lambda value: value.lower()),
        multiselect=False,
        title="Choose an unissued revision",
        button_name="Create Clouds",
    )
    return labels.get(selected_label) if selected_label else None


def _view_coordinate(point, origin, direction):
    return (
        (point.X - origin.X) * direction.X
        + (point.Y - origin.Y) * direction.Y
        + (point.Z - origin.Z) * direction.Z
    )


def _point_on_view(view, x_coord, y_coord):
    return view.Origin.Add(view.RightDirection.Multiply(x_coord)).Add(
        view.UpDirection.Multiply(y_coord)
    )


def _revision_cloud_curves(element, view):
    bounding_box = None
    try:
        bounding_box = element.get_BoundingBox(view)
    except Exception:
        pass
    if bounding_box is None:
        try:
            bounding_box = element.get_BoundingBox(None)
        except Exception:
            return None
    if bounding_box is None:
        return None

    origin = view.Origin
    right = view.RightDirection.Normalize()
    up = view.UpDirection.Normalize()
    points = []
    for x_coord in (bounding_box.Min.X, bounding_box.Max.X):
        for y_coord in (bounding_box.Min.Y, bounding_box.Max.Y):
            for z_coord in (bounding_box.Min.Z, bounding_box.Max.Z):
                point = bounding_box.Transform.OfPoint(DB.XYZ(x_coord, y_coord, z_coord))
                points.append((
                    _view_coordinate(point, origin, right),
                    _view_coordinate(point, origin, up),
                ))

    margin = _CLOUD_MARGIN_FEET
    min_x = min(point[0] for point in points) - margin
    max_x = max(point[0] for point in points) + margin
    min_y = min(point[1] for point in points) - margin
    max_y = max(point[1] for point in points) + margin

    corners = [
        _point_on_view(view, min_x, min_y),
        _point_on_view(view, min_x, max_y),
        _point_on_view(view, max_x, max_y),
        _point_on_view(view, max_x, min_y),
    ]
    curves = List[DB.Curve]()
    for index in range(len(corners)):
        curves.Add(DB.Line.CreateBound(corners[index], corners[(index + 1) % len(corners)]))
    return curves


def _create_revision_clouds(doc, view, revision, elements):
    view_type = ""
    try:
        view_type = str(view.ViewType)
    except Exception:
        pass
    if view_type in ("ThreeD", "Schedule", "ColumnSchedule"):
        forms.alert(
            "Revision clouds are not supported in this view type. No clouds were created.",
            title="My View Elements",
        )
        return

    cloud_specs = []
    for element in elements:
        try:
            curves = _revision_cloud_curves(element, view)
            if curves:
                cloud_specs.append((element, curves))
        except Exception:
            continue

    geometry_skipped = len(elements) - len(cloud_specs)
    if not cloud_specs:
        forms.alert(
            "No revision clouds could be generated from the matched elements in this view.",
            title="My View Elements",
        )
        return

    created = 0
    failed = 0
    failure_samples = []
    try:
        with revit.Transaction("Create revision clouds for My View Elements", doc):
            for element, curves in cloud_specs:
                sub_transaction = DB.SubTransaction(doc)
                try:
                    sub_transaction.Start()
                    DB.RevisionCloud.Create(doc, view, revision.Id, curves)
                    status = sub_transaction.Commit()
                    if status == DB.TransactionStatus.Committed:
                        created += 1
                    else:
                        failed += 1
                except Exception as ex:
                    failed += 1
                    try:
                        sub_transaction.RollBack()
                    except Exception:
                        pass
                    if len(failure_samples) < 3:
                        failure_samples.append(str(ex))
    except Exception as ex:
        forms.alert(
            "Revision cloud creation failed and the transaction was rolled back.\n\n{}".format(ex),
            title="My View Elements",
        )
        return

    result = "Revision clouds created: {} of {}.".format(created, len(elements))
    skipped = geometry_skipped + failed
    if skipped:
        result += "\nSkipped: {} ({} without usable view bounds, {} creation failures).".format(
            skipped, geometry_skipped, failed
        )
    if failure_samples:
        result += "\n\nFirst error: {}".format(failure_samples[0])
    forms.alert(result, title="My View Elements")


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    if doc is None or uidoc is None:
        forms.alert("Open a Revit project before running this tool.", title="My View Elements")
        return

    if not doc.IsWorkshared:
        forms.alert(
            "This project is not workshared, so Revit has no creator or owner data to search.",
            title="My View Elements",
        )
        return

    active_view = doc.ActiveView
    username = _normalize_username(doc.Application.Username)
    if not username:
        forms.alert("Revit did not provide a current username.", title="My View Elements")
        return

    category_options = _collect_category_options(doc, active_view)
    if not category_options:
        forms.alert("No categorized elements were found in the active view.", title="My View Elements")
        return

    selected_categories = forms.SelectFromList.show(
        sorted(category_options.keys(), key=lambda value: value.lower()),
        multiselect=True,
        title="Select categories to scan",
    )
    if not selected_categories:
        return

    category_ids = List[DB.ElementId]()
    for category_label in selected_categories:
        category_ids.Add(category_options[category_label])

    matches = List[DB.ElementId]()
    matched_elements = []
    created_count = 0
    owned_count = 0
    unreadable_count = 0

    category_filter = DB.ElementMulticategoryFilter(category_ids)
    elements = (
        DB.FilteredElementCollector(doc, active_view.Id)
        .WherePasses(category_filter)
        .WhereElementIsNotElementType()
    )
    for element in elements:
        try:
            info = DB.WorksharingUtils.GetWorksharingTooltipInfo(doc, element.Id)
            creator_match = _normalize_username(info.Creator) == username
            owner_match = _normalize_username(info.Owner) == username
            if creator_match:
                created_count += 1
            if owner_match:
                owned_count += 1
            if creator_match or owner_match:
                matches.Add(element.Id)
                matched_elements.append(element)
        except Exception:
            unreadable_count += 1

    uidoc.Selection.SetElementIds(matches)

    result = (
        "Selected {0} elements in '{1}'.\n\n"
        "Categories scanned: {2}\n"
        "Created by you: {3}\n"
        "Currently owned by you: {4}"
    ).format(matches.Count, active_view.Name, len(selected_categories), created_count, owned_count)
    if unreadable_count:
        result += "\n\nCould not check worksharing data for {0} elements.".format(unreadable_count)

    forms.alert(result, title="My View Elements")

    if not matched_elements:
        return
    if not forms.alert(
        "Create one revision cloud around each of the {} matched element(s)?".format(len(matched_elements)),
        title="My View Elements",
        yes=True,
        no=True,
    ):
        return

    revision = _pick_revision(doc)
    if revision is None:
        return
    _create_revision_clouds(doc, active_view, revision, matched_elements)


if __name__ == "__main__":
    main()