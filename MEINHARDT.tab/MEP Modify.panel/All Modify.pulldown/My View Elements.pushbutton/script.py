# -*- coding: utf-8 -*-
"""Select active-view elements created by or currently owned by the user."""

from pyrevit import DB, forms, revit
from System.Collections.Generic import List


def _normalize_username(value):
    try:
        return (value or "").strip().lower()
    except Exception:
        return ""


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

    matches = List[DB.ElementId]()
    created_count = 0
    owned_count = 0
    unreadable_count = 0

    elements = DB.FilteredElementCollector(doc, active_view.Id).WhereElementIsNotElementType()
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
        "Created by you: {2}\n"
        "Currently owned by you: {3}"
    ).format(matches.Count, active_view.Name, created_count, owned_count)
    if unreadable_count:
        result += "\n\nCould not check worksharing data for {0} elements.".format(unreadable_count)

    forms.alert(result, title="My View Elements")


if __name__ == "__main__":
    main()