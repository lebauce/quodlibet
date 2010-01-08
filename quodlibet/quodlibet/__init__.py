import __builtin__

_dummy_gettext = lambda value: value
_dummy_ngettext = lambda v1, v2, count: (count == 1) and v1 or v2
__builtin__.__dict__["_"] = _dummy_gettext
__builtin__.__dict__["Q_"] = _dummy_gettext
__builtin__.__dict__["N_"] = _dummy_gettext
__builtin__.__dict__["ngettext"] = _dummy_ngettext

import gettext
import locale
import os
import re
import signal
import sys
import time
import traceback
import warnings

import quodlibet.const
import quodlibet.util
import quodlibet.util.logging

from quodlibet.const import ENCODING
from quodlibet.util.i18n import GlibTranslations

def _gtk_init(icon=None):
    import pygtk
    pygtk.require('2.0')
    import gtk
    import gobject

    # http://bugzilla.gnome.org/show_bug.cgi?id=318953
    if gtk.gtk_version < (2, 8, 8):
        class TVProxy(gtk.TreeView):
            def set_search_equal_func(self, func, *args): pass
        gtk.TreeView = TVProxy

    import quodlibet.stock
    quodlibet.stock.init()

    gobject.set_application_name(_("Quod Libet").encode('utf-8'))
    os.environ["PULSE_PROP_media.role"] = "music"
    os.environ["PULSE_PROP_application.icon_name"] = quodlibet.stock.QL_ICON

    if icon:
        icon = os.path.join(quodlibet.const.IMAGEDIR, icon)
        try: gtk.window_set_default_icon_from_file(icon + ".svg")
        except: gtk.window_set_default_icon_from_file(icon + ".png")

def _gettext_init():
    try: locale.setlocale(locale.LC_ALL, '')
    except locale.Error: pass
    try:
        t = gettext.translation("quodlibet", class_=GlibTranslations)
    except IOError:
        t = GlibTranslations()
    t.install(unicode=True)

def print_(string, frm="utf-8", prefix="", output=sys.stdout, log=None):
    if prefix:
        string = prefix + ("\n" + prefix).join(string.splitlines())

    quodlibet.util.logging.log(string, log)

    if os.name == 'nt':
        return

    if output:
        if isinstance(string, unicode):
            string = string.encode(ENCODING, "replace")
        else:
            string = string.decode(frm).encode(ENCODING, "replace")
        try:
            print >>output, string
        except IOError, e:
            pass

def print_d(string, context=""):
    """Print debugging information."""
    if quodlibet.const.DEBUG:
        output = sys.stderr
    else:
        output = None

    if context and not isinstance(context, str):
        try:
            context = type(context).__name__
            context += "." + traceback.extract_stack()[-2][2] + ": "
        except AttributeError:
            context = "Unknown Context"

    timestr = "%0.2f" % time.time()
    string = "%s: %s%s" % (timestr[-6:], context, string)
    print_(string, prefix="D: ", log="Debug", output=output)

def print_w(string):
    """Print warnings."""
    # Translators: "W" as in "Warning". It is prepended to
    # terminal output. APT uses a similar output format.
    print_(string, prefix=_("W: "), log=_("Warnings"), output=sys.stderr)

def print_e(string):
    """Print errors."""
    # Translators: "E" as in "Error". It is prepended to
    # terminal output. APT uses a similar output format.
    print_(string, prefix=_("E: "), log=_("Errors"), output=sys.stderr)

def _python_init():
    # The default regex escaping function doesn't work for non-ASCII.
    # Use a blacklist of regex-specific characters instead.
    def re_esc(str, BAD="/.^$*+?{,\\[]|()<>#=!:"):
        needs_escape = lambda c: (c in BAD and "\\" + c) or c
        return "".join(map(needs_escape, str))
    re.escape = re_esc

    # Set up import wrappers for Quod Libet 1.x compatibility.
    old_import = __import__
    def import_ql(module, *args, **kwargs):
        try: return old_import(module, *args, **kwargs)
        except ImportError:
            # If it looks like a plugin import error, forgive it, and
            # try prepending quodlibet to the module name.
            tb = traceback.extract_stack()
            for (filename, linenum, func, text) in tb:
                if "plugins" in filename:
                    # warn() causes errors when running from py2exe
                    if not (os.name == 'nt' and 'library.zip' in __file__):
                        warnings.warn(
                            "enabling legacy plugin API", DeprecationWarning)
                    old_import("quodlibet." + module, *args, **kwargs)
                    return sys.modules["quodlibet." + module]
            else:
                raise
    __builtin__.__dict__["__import__"] = import_ql
    __builtin__.__dict__["print_"] = print_
    __builtin__.__dict__["print_d"] = print_d
    __builtin__.__dict__["print_e"] = print_e
    __builtin__.__dict__["print_w"] = print_w

del(_dummy_gettext)
del(_dummy_ngettext)

_python_init()
_gettext_init()

def init(gtk=True, backend=None, library=None, icon=None):
    print_d("Entering quodlibet.init")
    if gtk:
        _gtk_init(icon)

    # We already imported this, but Python is dumb and thinks we're rebinding
    # a local when we import it later.
    import quodlibet.util
    quodlibet.util.mkdir(quodlibet.const.USERDIR)

    if backend:
        import quodlibet.player
        print_(_("Initializing audio backend (%s)") % backend)
        backend = quodlibet.player.init(backend)
    if library:
        print_(_("Initializing main library (%s)") % (
            quodlibet.util.unexpand(library)))

    import quodlibet.library
    library = quodlibet.library.init(library)

    if backend:
        device = quodlibet.player.init_device(library.librarian)
    else:
        device = None

    print_d("Initializing debugging extensions")
    import quodlibet.debug
    quodlibet.debug.init()

    print_d("Finished initialization.")
    return (backend, library, device)

def quit((backend, library, device), save=False):
    print_d("Entering quodlibet.quit")
    if device is not None:
        print_d("Shutting down player device %r." % device.version_info)
        quodlibet.player.quit(device)

    if library is not None:
        if save:
            try: library.save()
            except EnvironmentError, err:
                from quodlibet.qltk.msg import ErrorMessage
                err = str(err).decode('utf-8', 'replace')
                ErrorMessage(None, _("Unable to save library"), err).run()
            else:
                library.destroy()
    print_d("Finished shutdown.")

def main(window):
    print_d("Entering quodlibet.main")
    import gtk

    SIGS = [getattr(signal, s, None) for s in "SIGINT SIGTERM SIGHUP".split()]
    for sig in filter(None, SIGS):
        signal.signal(sig, window.destroy)

    window.connect('destroy', gtk.main_quit)
    window.show()

    # This has been known to cause segmentation faults in some Python,
    # GTK+, and GStreamer versions.
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

def error_and_quit(error):
    from quodlibet.qltk.msg import ErrorMessage
    ErrorMessage(None, error.short_desc, error.long_desc).run()
