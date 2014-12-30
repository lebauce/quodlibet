# Copyright 2012 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

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
import sys
import warnings

import quodlibet.const
import quodlibet.util

from quodlibet.util import load_library
from quodlibet.util.path import mkdir, unexpand
from quodlibet.util.i18n import GlibTranslations
from quodlibet.util.dprint import print_, print_d, print_w, print_e
from quodlibet.const import MinVersions, Version

PLUGIN_DIRS = ["editing", "events", "playorder", "songsmenu", "playlist",
               "gstreamer", "covers"]


class Application(object):
    """A main application class for controlling the application as a whole
    and accessing sub-modules.

    window    - The main window which is present as long as QL is running
    library   - The main library (see library.SongFileLibrary)
    librarian - The main (and atm only) librarian (see library.SongLibrarian)
    player    - see player._base

    quit()    - Quit the application

    """

    window = None
    library = None
    player = None

    @property
    def librarian(self):
        return self.library.librarian

    @property
    def browser(self):
        return self.window.browser

    def quit(self):
        from gi.repository import GLib

        def idle_quit():
            if self.window:
                self.window.destroy()

        # so this can be called from a signal handler and before
        # the main loop starts
        GLib.idle_add(idle_quit, priority=GLib.PRIORITY_HIGH)

    def show(self):
        from quodlibet.qltk import Window
        for window in Window.windows:
            window.show()

    def present(self):
        # deiconify is needed if the window is on another workspace
        from quodlibet.qltk import Window
        for window in Window.windows:
            window.deiconify()
            window.present()

    def hide(self):
        from quodlibet.qltk import Window
        for window in Window.windows:
            window.hide()

app = Application()


def fix_gst_leaks():
    """gst_element_add_pad and gst_bin_add are wrongly annotated and lead
    to PyGObject refing the passed element.

    Work around by adding a wrapper that unrefs afterwards.
    Can be called multiple times.

    https://bugzilla.gnome.org/show_bug.cgi?id=741390
    https://bugzilla.gnome.org/show_bug.cgi?id=702960
    """

    from gi.repository import Gst

    assert Gst.is_initialized()

    def do_wrap(func):
        def wrap(self, obj):
            result = func(self, obj)
            obj.unref()
            return result
        return wrap

    parent = Gst.Bin()
    elm = Gst.Bin()
    parent.add(elm)
    if elm.__grefcount__ == 3:
        elm.unref()
        Gst.Bin.add = do_wrap(Gst.Bin.add)

    pad = Gst.Pad.new("foo", Gst.PadDirection.SRC)
    parent.add_pad(pad)
    if pad.__grefcount__ == 3:
        pad.unref()
        Gst.Element.add_pad = do_wrap(Gst.Element.add_pad)


def _gtk_init(icon=None):
    import gi

    # make sure GdkX11 doesn't get used under Windows
    if os.name == "nt":
        sys.modules["gi.repository.GdkX11"] = None

    try:
        # not sure if this is available under Windows
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        GdkX11
    except (ValueError, ImportError):
        pass

    gi.require_version("GLib", "2.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GObject", "2.0")
    gi.require_version("Pango", "1.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gio", "2.0")

    from gi.repository import Gtk, GObject, GLib, Gdk, GdkPixbuf

    # add Gtk.TreePath.__getitem__/__len__ for PyGObject 3.2
    try:
        Gtk.TreePath()[0]
    except TypeError:
        Gtk.TreePath.__getitem__ = lambda self, index: list(self)[index]
        Gtk.TreePath.__len__ = lambda self: self.get_depth()

    # GTK+ 3.4+ constants
    if not hasattr(Gdk, "BUTTON_PRIMARY"):
        Gdk.BUTTON_PRIMARY = 1
        Gdk.BUTTON_MIDDLE = 2
        Gdk.BUTTON_SECONDARY = 3

    if not hasattr(Gdk, "EVENT_PROPAGATE"):
        Gdk.EVENT_PROPAGATE = 0
        Gdk.EVENT_STOP = 1

    # On windows the default variants only do ANSI paths, so replace them.
    # In some typelibs they are replaced by default, in some don't..
    if os.name == "nt":
        for name in ["new_from_file_at_scale", "new_from_file_at_size",
                     "new_from_file"]:
            cls = GdkPixbuf.Pixbuf
            setattr(cls, name, getattr(cls, name + "_utf8", name))

    # https://bugzilla.gnome.org/show_bug.cgi?id=670372
    if not hasattr(GdkPixbuf.Pixbuf, "savev"):
        GdkPixbuf.Pixbuf.savev = GdkPixbuf.Pixbuf.save

    # Force menu/button image related settings. We might show too many atm
    # but this makes sure we don't miss cases where we forgot to force them
    # per widget.
    # https://bugzilla.gnome.org/show_bug.cgi?id=708676
    warnings.filterwarnings('ignore', '.*g_value_get_int.*', Warning)

    # some day... but not now
    warnings.filterwarnings(
        'ignore', '.*Stock items are deprecated.*', Warning)
    warnings.filterwarnings(
        'ignore', '.*:use-stock.*', Warning)

    settings = Gtk.Settings.get_default()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings.set_property("gtk-button-images", True)
        settings.set_property("gtk-menu-images", True)
    if hasattr(settings.props, "gtk_primary_button_warps_slider"):
        settings.set_property("gtk-primary-button-warps-slider", True)

    # Make sure PyGObject includes support for foreign cairo structs
    try:
        gi.require_foreign("cairo")
    except AttributeError:
        # older pygobject
        pass
    except ImportError:
        print_e("PyGObject is missing cairo support")
        exit(1)

    # CSS overrides
    if os.name == "nt":
        # somehow borders are missing under Windows & Gtk+3.14
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data("""
            .menu {
                border: 1px solid @borders;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    if sys.platform == "darwin":
        # fix duplicated shadows for popups with Gtk+3.14
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data("""
            GtkWindow {
                box-shadow: none;
            }
            .tooltip {
                border-radius: 0;
                padding: 0;
            }
            .tooltip.background {
                background-clip: border-box;
            }
            """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # https://bugzilla.gnome.org/show_bug.cgi?id=708676
    warnings.filterwarnings('ignore', '.*g_value_get_int.*', Warning)

    # We don't want python-gst, it changes API..
    assert "gi.overrides.Gst" not in sys.modules
    sys.modules["gi.overrides.Gst"] = None

    # We don't depend on Gst overrides, so make sure it's initialized.
    try:
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ValueError, ImportError):
        pass
    else:
        if not Gst.is_initialized():
            try:
                ok, argv = Gst.init_check(sys.argv)
            except GLib.GError:
                print_e("Failed to initialize GStreamer")
                # Uninited Gst segfaults: make sure no one can use it
                sys.modules["gi.repository.Gst"] = None
            else:
                sys.argv = argv

                # monkey patching ahead
                fix_gst_leaks()

                # https://bugzilla.gnome.org/show_bug.cgi?id=710447
                import threading
                threading.Thread(target=lambda: None).start()

    # some code depends on utf-8 default encoding (pygtk used to set it)
    reload(sys)
    sys.setdefaultencoding("utf-8")

    # blacklist some modules, simply loading can cause segfaults
    sys.modules["gtk"] = None
    sys.modules["gpod"] = None
    sys.modules["glib"] = None
    sys.modules["gobject"] = None
    sys.modules["gnome"] = None

    from quodlibet.qltk import pygobject_version
    if pygobject_version < (3, 9):
        GObject.threads_init()

    theme = Gtk.IconTheme.get_default()
    theme.append_search_path(quodlibet.const.IMAGEDIR)

    if icon:
        Gtk.Window.set_default_icon_name(icon)


def _dbus_init():
    try:
        from dbus.mainloop.glib import DBusGMainLoop, threads_init
    except ImportError:
        try:
            import dbus.glib
            dbus.glib
        except ImportError:
            return
    else:
        threads_init()
        DBusGMainLoop(set_as_default=True)


def _gettext_init():
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error:
        pass

    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        langs = filter(None, map(locale.windows_locale.get,
                                 [k32.GetUserDefaultUILanguage(),
                                  k32.GetSystemDefaultUILanguage()]))
        os.environ.setdefault('LANG', ":".join(langs))

    # Use the locale dir in ../build/share/locale if there is one
    localedir = os.path.dirname(quodlibet.const.BASEDIR)
    localedir = os.path.join(localedir, "build", "share", "locale")
    if not os.path.isdir(localedir) and os.name == "nt":
        # py2exe case
        localedir = os.path.join(
            quodlibet.const.BASEDIR, "..", "..", "share", "locale")

    if os.path.isdir(localedir):
        print_d("Using local localedir: %r" % unexpand(localedir))
    else:
        localedir = gettext.bindtextdomain("quodlibet")

    try:
        t = gettext.translation("quodlibet", localedir,
            class_=GlibTranslations)
    except IOError:
        print_d("No translation found in %r" % unexpand(localedir))
        t = GlibTranslations()
    else:
        print_d("Translations loaded: %r" % unexpand(t.path))

    t.install(unicode=True)


def set_process_title(title):
    """Sets process name as visible in ps or top. Requires ctypes libc
    and is almost certainly *nix-only. See issue 736"""

    if os.name == "nt":
        return

    try:
        libc = load_library(["libc.so.6", "c"])[0]
        # 15 = PR_SET_NAME, apparently
        libc.prctl(15, title, 0, 0, 0)
    except (OSError, AttributeError):
        print_d("Couldn't find module libc.so.6 (ctypes). "
                "Not setting process title.")


def _python_init():

    import sys
    if sys.version_info < MinVersions.PYTHON:
        actual = Version(sys.version_info[:3])
        print_w("Python %s required. %s found." % (MinVersions.PYTHON, actual))

    __builtin__.__dict__["print_"] = print_
    __builtin__.__dict__["print_d"] = print_d
    __builtin__.__dict__["print_e"] = print_e
    __builtin__.__dict__["print_w"] = print_w

del(_dummy_gettext)
del(_dummy_ngettext)

_python_init()
_gettext_init()


def init(library=None, icon=None, title=None, name=None):
    print_d("Entering quodlibet.init")

    _gtk_init(icon)
    _dbus_init()

    from gi.repository import GLib

    if title:
        GLib.set_prgname(title)
        set_process_title(title)
        # Issue 736 - set after main loop has started (gtk seems to reset it)
        GLib.idle_add(set_process_title, title)

    if name:
        GLib.set_application_name(name)

    # We already imported this, but Python is dumb and thinks we're rebinding
    # a local when we import it later.
    import quodlibet.util
    mkdir(quodlibet.const.USERDIR, 0750)

    if library:
        print_d("Initializing main library (%s)" % (
            quodlibet.util.path.unexpand(library)))

    import quodlibet.library
    library = quodlibet.library.init(library)

    _init_debug()

    print_d("Finished initialization.")

    return library


def init_plugins(no_plugins=False):
    print_d("Starting plugin manager")

    from quodlibet import plugins
    folders = [os.path.join(quodlibet.const.BASEDIR, "ext", kind)
               for kind in PLUGIN_DIRS]
    folders.append(os.path.join(quodlibet.const.USERDIR, "plugins"))
    print_d("Scanning folders: %s" % folders)
    pm = plugins.init(folders, no_plugins)
    pm.rescan()

    from quodlibet.qltk.edittags import EditTags
    from quodlibet.qltk.renamefiles import RenameFiles
    from quodlibet.qltk.tagsfrompath import TagsFromPath
    EditTags.init_plugins()
    RenameFiles.init_plugins()
    TagsFromPath.init_plugins()

    return pm


def init_backend(backend, librarian):
    import quodlibet.player
    print_d("Initializing audio backend (%s)" % backend)
    backend = quodlibet.player.init(backend)
    device = backend.init(librarian)
    return device


def enable_periodic_save(save_library):
    import quodlibet.library
    from quodlibet.util import copool
    from quodlibet import config

    timeout = 5 * 60 * 1000  # 5 minutes

    def periodic_config_save():
        while 1:
            config.save(quodlibet.const.CONFIG)
            yield

    copool.add(periodic_config_save, timeout=timeout)

    if not save_library:
        return

    def periodic_library_save():
        while 1:
            quodlibet.library.save()
            yield

    copool.add(periodic_library_save, timeout=timeout)


def is_first_session(app_name):
    """Returns True if the current session is the first one to e.g.
    show a wizard/setup dialog etc.

    Will return True after each upgrade as well.

    app_name: e.g. 'quodlibet'
    """

    from quodlibet import config
    from quodlibet import const

    value = config.get("memory", "%s_last_active_version" % app_name, "")

    if value != const.VERSION:
        return True

    return False


def finish_first_session(app_name):
    """Call on shutdown so that is_first_session() works"""

    from quodlibet import config
    from quodlibet import const

    config.set("memory", "%s_last_active_version" % app_name, const.VERSION)


def _init_debug():
    from gi.repository import GLib
    from quodlibet.qltk.debugwindow import ExceptionDialog

    print_d("Initializing debugging extensions")

    def _override_exceptions():
        print_d("Enabling custom exception handler.")
        sys.excepthook = ExceptionDialog.excepthook
    GLib.idle_add(_override_exceptions)

    # faulthandler gives a python stacktrace on segfaults..
    try:
        import faulthandler
    except ImportError:
        pass
    else:
        faulthandler.enable()


def _init_osx(window):
    from AppKit import NSObject, NSApplication
    import objc

    try:
        from gi.repository import GtkosxApplication
        osx_app = GtkosxApplication.Application()
    except ImportError:
        print_d("importing GtkosxApplication failed, no native menus")
    else:
        window.set_as_osx_window(osx_app)
        osx_app.ready()

    # Instead of quitting when the main window gets closed just hide it.
    # If the dock icon gets clicked we get
    # applicationShouldHandleReopen_hasVisibleWindows_ and show everything.
    class Delegate(NSObject):

        @objc.signature('B@:#B')
        def applicationShouldHandleReopen_hasVisibleWindows_(
                self, ns_app, flag):
            print_d("osx: handle reopen")
            app.present()
            return True

        def applicationShouldTerminate_(self, sender):
            print_d("osx: block termination")
            # FIXME: figure out why idle_add is needed here
            from gi.repository import GLib
            GLib.idle_add(app.quit)
            return False

    shared_app = NSApplication.sharedApplication()
    delegate = Delegate.alloc().init()
    delegate.retain()
    shared_app.setDelegate_(delegate)
    window.connect(
        "delete-event", lambda window, event: window.hide() or True)


def main(window, before_quit=None):
    print_d("Entering quodlibet.main")
    from gi.repository import Gtk

    def quit_gtk(window):

        if before_quit is not None:
            before_quit()

        # disable plugins
        import quodlibet.plugins
        quodlibet.plugins.quit()

        # for debug: this will list active copools
        from quodlibet.util import copool
        copool.pause_all()

        # See which browser windows are open and save their names
        # so we can restore them on start
        from quodlibet.qltk.browser import LibraryBrowser
        LibraryBrowser.save()

        # destroy all open windows so they hide immediately on close:
        # destroying all top level windows doesn't work (weird errors),
        # so we hide them all and only destroy our tracked instances
        # (browser windows, tag editors, pref window etc.)
        from quodlibet.qltk import Window
        for toplevel in Gtk.Window.list_toplevels():
            toplevel.hide()

        for window in Window.windows:
            window.destroy()

        Gtk.main_quit()

        print_d("Quit GTK: done.")

    window.connect('destroy', quit_gtk)

    if sys.platform == "darwin":
        _init_osx(window)

    window.show_maybe()

    Gtk.main()
    print_d("Gtk.main() done.")
