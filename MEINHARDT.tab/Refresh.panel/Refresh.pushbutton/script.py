"""Reload pyRevit into new session.
Shows a native WPF Meinhardt animation window while reloading.
"""
# -*- coding: utf-8 -*-
#pylint: disable=import-error,invalid-name,broad-except

from pyrevit import script
from pyrevit.loader import sessionmgr
from pyrevit.loader import sessioninfo


logger = script.get_logger()
results = script.get_results()

w = None


def _close_existing_reload_windows(windows_ns):
    try:
        app = windows_ns.Application.Current
        if app is None:
            return
        for win in app.Windows:
            try:
                if getattr(win, "Tag", None) == "MHT_REFRESH_WINDOW":
                    win.Close()
            except Exception:
                pass
    except Exception:
        pass


def _flush_ui(dispatcher, ms=220):
    # Render at least one frame so the animation window is visible before reload blocks.
    try:
        from System import Action
        from System.Threading import Thread
        from System.Windows.Threading import DispatcherPriority

        dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Render)
        Thread.Sleep(ms)
        dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Render)
    except Exception as ex:
        logger.debug('Could not flush UI render cycle: {}'.format(ex))


try:
    xamlfile = script.get_bundle_file('ReloadingWindow.xaml')

    import wpf
    from System import Windows

    _close_existing_reload_windows(Windows)

    class ReloadingWindow(Windows.Window):
        def __init__(self):
            wpf.LoadComponent(self, xamlfile)
            self.Tag = "MHT_REFRESH_WINDOW"

    w = ReloadingWindow()
    w.WindowStartupLocation = Windows.WindowStartupLocation.CenterScreen
    w.Show()
    try:
        w.Activate()
        w.Topmost = True
    except Exception:
        pass

    _flush_ui(w.Dispatcher, 260)
except Exception as e:
    logger.warning('Could not display reloading animation window: {}'.format(e))
    import traceback
    logger.debug(traceback.format_exc())

logger.info('RELOADING CHANGES')
try:
    sessionmgr.reload_pyrevit()
finally:
    try:
        if w is not None:
            w.Close()
    except Exception as e:
        logger.debug('Could not close reloading window: {}'.format(e))

try:
    results.newsession = sessioninfo.get_session_uuid()
except Exception as e:
    logger.debug('Could not set newsession: {}'.format(e))
