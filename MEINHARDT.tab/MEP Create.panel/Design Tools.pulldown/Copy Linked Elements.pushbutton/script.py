# -*- coding: utf-8 -*-
from __future__ import print_function

from collections import defaultdict

from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from System.Collections.Generic import List
from pyrevit import DB, forms, revit, script


doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()


class _LoadedLinkedElementFilter(ISelectionFilter):
    def __init__(self, host_doc):
        self._host_doc = host_doc

    def AllowElement(self, element):
        try:
            return (isinstance(element, DB.RevitLinkInstance)
                    and element.GetLinkDocument() is not None)
        except Exception as ex:
            logger.debug("Ignoring unavailable Revit link during selection: %s", ex)
            return False

    def AllowReference(self, reference, point):
        try:
            link_instance = self._host_doc.GetElement(reference.ElementId)
            if not isinstance(link_instance, DB.RevitLinkInstance):
                return False
            link_doc = link_instance.GetLinkDocument()
            if link_doc is None:
                return False

            linked_id = reference.LinkedElementId
            if linked_id == DB.ElementId.InvalidElementId:
                return False
            linked_element = link_doc.GetElement(linked_id)
            return linked_element is not None and not isinstance(linked_element, DB.ElementType)
        except Exception as ex:
            logger.debug("Ignoring invalid linked-element pick: %s", ex)
            return False


class _UseDestinationTypesHandler(DB.IDuplicateTypeNamesHandler):
    def OnDuplicateTypeNamesFound(self, args):
        return DB.DuplicateTypeAction.UseDestinationTypes


def _is_linked_element_reference(reference):
    try:
        if reference.LinkedElementId == DB.ElementId.InvalidElementId:
            return False
        link_instance = doc.GetElement(reference.ElementId)
        if not isinstance(link_instance, DB.RevitLinkInstance):
            return False
        link_doc = link_instance.GetLinkDocument()
        if link_doc is None:
            return False
        linked_element = link_doc.GetElement(reference.LinkedElementId)
        return linked_element is not None and not isinstance(linked_element, DB.ElementType)
    except Exception as ex:
        logger.debug("Ignoring invalid linked-element reference: %s", ex)
        return False


def _collect_selected_references():
    selected_references = []
    try:
        selected_references = [
            reference for reference in uidoc.Selection.GetReferences()
            if _is_linked_element_reference(reference)
        ]
    except Exception as ex:
        logger.debug("Could not read the current linked-element selection: %s", ex)

    if selected_references:
        return selected_references

    try:
        return list(uidoc.Selection.PickObjects(
            ObjectType.LinkedElement,
            _LoadedLinkedElementFilter(doc),
            "Select linked elements to copy, then click Finish or press Esc."
        ))
    except OperationCanceledException:
        return []


def _group_element_ids(references):
    groups = {}
    seen = defaultdict(set)
    for reference in references:
        if not _is_linked_element_reference(reference):
            continue

        link_id = reference.ElementId
        linked_id = reference.LinkedElementId
        try:
            key = link_id.Value
        except AttributeError:
            key = link_id.IntegerValue
        try:
            linked_key = linked_id.Value
        except AttributeError:
            linked_key = linked_id.IntegerValue
        if linked_key in seen[key]:
            continue

        link_instance = doc.GetElement(link_id)
        link_doc = link_instance.GetLinkDocument()
        if key not in groups:
            groups[key] = {
                "instance": link_instance,
                "source_doc": link_doc,
                "ids": List[DB.ElementId]()
            }
        groups[key]["ids"].Add(linked_id)
        seen[key].add(linked_key)

    return list(groups.values())


def _copy_groups(groups):
    transaction = DB.Transaction(doc, "Copy Linked Elements")
    transaction.Start()
    copied_ids = []
    errors = []
    options = DB.CopyPasteOptions()
    options.SetDuplicateTypeNamesHandler(_UseDestinationTypesHandler())

    try:
        for group in groups:
            link_instance = group["instance"]
            link_name = getattr(link_instance, "Name", "Revit Link")
            subtransaction = DB.SubTransaction(doc)
            subtransaction.Start()
            try:
                transform = (link_instance.GetTotalTransform()
                             if hasattr(link_instance, "GetTotalTransform")
                             else link_instance.GetTransform())
                result_ids = DB.ElementTransformUtils.CopyElements(
                    group["source_doc"],
                    group["ids"],
                    doc,
                    transform,
                    options
                )
                subtransaction.Commit()
                copied_ids.extend(list(result_ids))
            except Exception as ex:
                if subtransaction.GetStatus() == DB.TransactionStatus.Started:
                    subtransaction.RollBack()
                logger.exception("Could not copy selected elements from link %s", link_name)
                errors.append("{}: {}".format(link_name, ex))
        transaction.Commit()
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise

    return copied_ids, errors


if doc is None or uidoc is None:
    forms.alert("Open a Revit project before running this tool.", exitscript=True)

references = _collect_selected_references()
if not references:
    script.exit()

groups = _group_element_ids(references)
if not groups:
    forms.alert("No valid linked elements were selected. Select elements from a loaded Revit link and try again.")
    script.exit()

copied_ids, errors = _copy_groups(groups)
if copied_ids:
    message = "Copied {} element(s) from linked model(s) into the current model.".format(len(copied_ids))
    if errors:
        message += "\n\nSome link selections could not be copied:\n" + "\n".join(errors[:5])
    forms.alert(message)
elif errors:
    forms.alert("No elements were copied.\n\n" + "\n".join(errors[:5]))
else:
    forms.alert("No elements were copied.")
