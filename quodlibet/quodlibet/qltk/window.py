# Copyright 2012,2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, GObject, Gdk

from quodlibet import config
from quodlibet.qltk import get_top_parent, is_wayland
from quodlibet.util import DeferredSignal


class Window(Gtk.Window):
    """Base window class the keeps track of all window instances.

    All active instances can be accessed through Window.windows.
    By defining dialog=True as a kwarg binds Escape to close, otherwise
    ^W will close the window.
    """

    windows = []
    _preven_inital_show = False

    __gsignals__ = {
        "close-accel": (GObject.SIGNAL_RUN_LAST | GObject.SIGNAL_ACTION,
                        GObject.TYPE_NONE, ())
    }

    def __init__(self, *args, **kwargs):
        dialog = kwargs.pop("dialog", True)
        super(Window, self).__init__(*args, **kwargs)
        type(self).windows.append(self)
        self.__accels = Gtk.AccelGroup()
        if dialog:
            self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_destroy_with_parent(True)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.add_accel_group(self.__accels)
        if not dialog:
            self.add_accelerator('close-accel', self.__accels,
                                 ord('w'), Gdk.ModifierType.CONTROL_MASK, 0)
        else:
            esc, mod = Gtk.accelerator_parse("Escape")
            self.add_accelerator('close-accel', self.__accels, esc, mod, 0)
        self.connect_object('destroy', type(self).windows.remove, self)

    def set_transient_for(self, parent):
        """Set a parent for the window.

        In case parent=None, fall back to the main window.

        """

        is_toplevel = parent and parent.props.type == Gtk.WindowType.TOPLEVEL

        if parent is None or not is_toplevel:
            if parent:
                print_w("Not a toplevel window set for: %r" % self)
            from quodlibet import app
            parent = app.window
        super(Window, self).set_transient_for(parent)

    def do_close_accel(self):
        #Do not close the window if we edit a Gtk.CellRendererText.
        #Focus the treeview instead.
        if isinstance(self.get_focus(), Gtk.Entry) and \
            isinstance(self.get_focus().get_parent(), Gtk.TreeView):
            self.get_focus().get_parent().grab_focus()
            return
        if not self.emit('delete-event', Gdk.Event.new(Gdk.EventType.DELETE)):
            self.destroy()

    @classmethod
    def prevent_inital_show(cls, value):
        cls._preven_inital_show = bool(value)

    def show_maybe(self):
        """Show the window, except if prevent_inital_show() was called and
        this is the first time
        """

        if not self._preven_inital_show:
            self.show()


class PersistentWindowMixin(object):
    """A mixin for saving/restoring window size/position/maximized state"""

    def enable_window_tracking(self, config_prefix, size_suffix=""):
        """Enable tracking/saving of changes and restore size/pos/maximized

        config_prefix -- prefix for the config key
                         (prefix_size, prefix_position, prefix_maximized)
        size_suffix -- optional suffix for saving the size. For cases where the
                       window has multiple states with different content sizes.
                       (example: edit tags with one song or multiple)

        """

        self.__state = 0
        self.__name = config_prefix
        self.__size_suffix = size_suffix
        self.__save_size_deferred = DeferredSignal(
            self.__do_save_size, timeout=50, owner=self)
        self.connect('configure-event', self.__configure_event)
        self.connect('window-state-event', self.__window_state_changed)
        self.connect('notify::visible', self.__visible_changed)
        self.__restore_window_state()

    def __visible_changed(self, *args):
        if not self.get_visible():
            # https://bugzilla.gnome.org/show_bug.cgi?id=731287
            # if we restore after hide, mutter will remember for the next show
            # hurray!
            self.__restore_window_state()

    def __restore_window_state(self):
        if not is_wayland():
            self.__restore_state()
            self.__restore_position()
        self.__restore_size()

    def __conf(self, name):
        if name == "size":
            name += "_" + self.__size_suffix
        return "%s_%s" % (self.__name, name)

    def __restore_state(self):
        print_d("Restore state")
        if config.getint("memory", self.__conf("maximized"), 0):
            self.maximize()
        else:
            self.unmaximize()

    def __restore_position(self):
        print_d("Restore position")
        pos = config.get('memory', self.__conf("position"), "-1 -1")
        x, y = map(int, pos.split())
        if x >= 0 and y >= 0:
            self.move(x, y)

    def __restore_size(self):
        print_d("Restore size")
        value = config.get('memory', self.__conf("size"), "-1 -1")
        x, y = map(int, value.split())
        screen = self.get_screen()
        x = min(x, screen.get_width())
        y = min(y, screen.get_height())
        if x >= 1 and y >= 1:
            self.resize(x, y)

    def __configure_event(self, window, event):
        # xfwm4 resized the window before it maximizes it, which leads
        # to QL remembering the wrong size. Work around that by waiting
        # until configure-event settles down, at which point the maximized
        # state should be set
        # WARNING: we can't keep the event, because PyGObject doesn't
        # keep it alive; so extract width/height before returning here.

        self.__save_size_deferred(event.width, event.height)
        return False

    def __do_save_size(self, width, height):
        if self.__state & Gdk.WindowState.MAXIMIZED:
            return

        value = "%d %d" % (width, height)
        config.set("memory", self.__conf("size"), value)
        if self.get_property("visible"):
            pos_value = '%s %s' % self.get_position()
            config.set('memory', self.__conf("position"), pos_value)

    def __window_state_changed(self, window, event):
        self.__state = event.new_window_state
        if self.__state & Gdk.WindowState.WITHDRAWN:
            return
        maximized = int(self.__state & Gdk.WindowState.MAXIMIZED)
        config.set("memory", self.__conf("maximized"), maximized)


class UniqueWindow(Window):
    """A wrapper for the window class to get a one instance per class window.
    The is_not_unique method will return True if the window
    is already there."""

    __window = None

    def __new__(klass, *args, **kwargs):
        window = klass.__window
        if window is None:
            return super(UniqueWindow, klass).__new__(klass, *args, **kwargs)
        #Look for widgets in the args, if there is one and it has
        #a new top level window, reparent and reposition the window.
        widgets = filter(lambda x: isinstance(x, Gtk.Widget), args)
        if widgets:
            parent = window.get_transient_for()
            new_parent = get_top_parent(widgets[0])
            if parent and new_parent and parent is not new_parent:
                window.set_transient_for(new_parent)
                window.hide()
                window.show()
        window.present()
        return window

    @classmethod
    def is_not_unique(klass):
        if klass.__window:
            return True

    def __init__(self, *args, **kwargs):
        if type(self).__window:
            return
        else:
            type(self).__window = self
        super(UniqueWindow, self).__init__(*args, **kwargs)
        self.connect_object('destroy', self.__destroy, self)

    def __destroy(self, *args):
        type(self).__window = None
