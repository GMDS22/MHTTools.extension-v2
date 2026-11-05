# -*- coding: utf-8 -*-
"""Select active-view elements created by or currently owned by the user."""

from pyrevit import DB, forms, revit
from System.Collections.Generic import List


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


if __name__ == "__main__":
    main()