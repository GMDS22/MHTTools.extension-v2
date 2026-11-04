# coding: utf8

# noinspection PyUnresolvedReferences
import System
from Autodesk.Revit.Exceptions import (
    InvalidOperationException,
    RegenerationFailedException,
)

# noinspection PyUnresolvedReferences
from pyrevit import UI


class CustomizableEvent:
    def __init__(self):
        """An instance of this class need to be created before any modeless operation.
        You can then call the raise_event method to perform any modeless operation.
        Any modification to Revit DB need to be performed inside a valid Transaction.
        This Transaction needs to be open inside the function_or_method, NOT before calling raise_event.
        >>> customizable_event = CustomizableEvent()
        >>> customizable_event.raise_event(rename_views, views_and_names)
        """
        # Create an handler instance and his associated ExternalEvent
        custom_handler = _CustomHandler()
        custom_handler.customizable_event = self
        self.custom_event = UI.ExternalEvent.Create(custom_handler)

        # Initialise raise_event variables
        self.function_or_method = None
        self.args = ()
        self.kwargs = {}
        self._request_pending = False

        # Optional logger
        self.logger = None

    def _raised_method(self):
        """!!! DO NOT USE THIS METHOD IN YOUR SCRIPT !!!
        Method executed by IExternalEventHandler.Execute when ExternalEvent is raised by ExternalEvent.Raise.
        """
        self.function_or_method(*self.args, **self.kwargs)

    def raise_event(self, function_or_method, *args, **kwargs):
        """
        Method used to raise an external event with custom function and parameters
        Example :
        >>> customizable_event = CustomizableEvent()
        >>> customizable_event.raise_event(rename_views, views_and_names)
        """
        if self._request_pending:
            return False

        previous_function = self.function_or_method
        previous_args = self.args
        previous_kwargs = self.kwargs
        self.args = args
        self.kwargs = kwargs
        self.function_or_method = function_or_method
        try:
            request = self.custom_event.Raise()
        except Exception:
            self.function_or_method = previous_function
            self.args = previous_args
            self.kwargs = previous_kwargs
            raise
        try:
            accepted = request.ToString() == "Accepted"
        except Exception:
            accepted = str(request) == "Accepted"
        if accepted:
            self._request_pending = True
        else:
            self.function_or_method = previous_function
            self.args = previous_args
            self.kwargs = previous_kwargs
        return request


class _CustomHandler(UI.IExternalEventHandler):
    """Subclass of IExternalEventHandler intended to be used in CustomizableEvent class
    Input : function or method. Execute input in a IExternalEventHandler"""

    def __init__(self):
        self.customizable_event = None

    # Execute method run in Revit API environment.
    # noinspection PyPep8Naming, PyUnusedLocal
    def Execute(self, application):
        try:
            self.customizable_event._raised_method()
        except RegenerationFailedException:
            logger = self.customizable_event.logger
            if logger:
                logger.exception("Fatal Revit regeneration failure in customizable event")
            raise
        except (InvalidOperationException, Exception, System.Exception):
            # If you don't catch exeptions Revit may crash. All exceptions inherit from python Exception or System.Exception
            logger = self.customizable_event.logger
            if logger:
                logger.exception("Failed to executer customizable event")
        finally:
            self.customizable_event._request_pending = False

    # noinspection PyMethodMayBeStatic, PyPep8Naming
    def GetName(self):
        return "Execute an function or method in a IExternalHandler"
