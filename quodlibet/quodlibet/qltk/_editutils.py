# -*- coding: utf-8 -*-
# Copyright 2004-2006 Joe Wreschnig, Michael Urman, Iñigo Serna
#                2014 Nick Boultbee
#                2014 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, GObject

from quodlibet import config
from quodlibet import util

from quodlibet.plugins import PluginHandler
from quodlibet.qltk.ccb import ConfigCheckButton
from quodlibet.qltk.msg import WarningMessage, ErrorMessage
from quodlibet.qltk.x import Button
from quodlibet.util.path import fsdecode
from quodlibet.util import connect_obj


class OverwriteWarning(WarningMessage):

    RESPONSE_SAVE = 1

    def __init__(self, parent, song):
        title = _("Tag may not be accurate")

        fn_format = "<b>%s</b>" % util.escape(fsdecode(song("~basename")))
        description = _("%(file-name)s changed while the program was running. "
            "Saving without refreshing your library may "
            "overwrite other changes to the song.") % {"file-name": fn_format}

        super(OverwriteWarning, self).__init__(
            parent, title, description, buttons=Gtk.ButtonsType.NONE)

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        save_button = Button(_("_Save"), "document-save")
        save_button.show()
        self.add_action_widget(save_button, self.RESPONSE_SAVE)
        self.set_default_response(Gtk.ResponseType.CANCEL)


class WriteFailedError(ErrorMessage):

    def __init__(self, parent, song):
        title = _("Unable to save song")

        fn_format = "<b>%s</b>" % util.escape(fsdecode(song("~basename")))
        description = _("Saving %(file-name)s failed. The file may be "
            "read-only, corrupted, or you do not have "
            "permission to edit it.") % {"file-name": fn_format}

        super(WriteFailedError, self).__init__(
            parent, title, description)


class EditingPluginHandler(GObject.GObject, PluginHandler):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ())
    }

    Kind = None

    def __init__(self):
        super(EditingPluginHandler, self).__init__()
        self.__plugins = []

    @property
    def plugins(self):
        return list(self.__plugins)

    def plugin_handle(self, plugin):
        return issubclass(plugin.cls, self.Kind)

    def plugin_enable(self, plugin):
        self.__plugins.append(plugin.cls)
        self.changed()

    def plugin_disable(self, plugin):
        self.__plugins.remove(plugin.cls)
        self.changed()

    def changed(self):
        self.emit("changed")


class FilterCheckButton(ConfigCheckButton):
    __gsignals__ = {
        "preview": (GObject.SignalFlags.RUN_LAST, None, ())
        }

    def __init__(self):
        super(FilterCheckButton, self).__init__(
            self._label, self._section, self._key)
        try:
            self.set_active(config.getboolean(self._section, self._key))
        except:
            pass
        connect_obj(self, 'toggled', self.emit, 'preview')

    @property
    def active(self):
        return self.get_active()

    def filter(self, original, filename):
        raise NotImplementedError

    def filter_list(self, origs, names):
        return map(self.filter, origs, names)

    def __lt__(self, other):
        return (self._order, type(self).__name__) < \
            (other._order, type(other).__name__)


class FilterPluginBox(Gtk.VBox):

    __gsignals__ = {
        # the list should be updated
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
        # the preview button should be made sensitive
        "preview": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, plugin_handler, filter_types=None):
        super(FilterPluginBox, self).__init__()

        # static filters
        if filter_types is None:
            filter_types = []

        filters = [Kind() for Kind in filter_types]
        filters.sort()
        for f in filters:
            self.pack_start(f, True, True, 0)
        self.__filters = filters

        # plugins
        self.__plugins = []
        hb = Gtk.HBox()
        expander = Gtk.Expander(label=_(u"_More options…"))
        expander.set_use_underline(True)
        hb.pack_start(expander, True, True, 0)
        self.pack_start(hb, False, True, 0)

        for filt in filters:
            filt.connect('preview', lambda *x: self.emit("preview"))

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.VBox()

        plugin_handler.connect(
            "changed", self.__refresh_plugins, vbox, expander)

        sw.add_with_viewport(vbox)
        self.pack_start(sw, False, True, 0)

        sw.set_no_show_all(True)
        expander.connect("notify::expanded", self.__notify_expanded, sw)
        expander.set_expanded(False)

        for child in self.get_children():
            child.show()

        plugin_handler.changed()
        sw.hide()

    def __notify_expanded(self, expander, event, vbox):
        vbox.set_property('visible', expander.get_property('expanded'))

    def __refresh_plugins(self, handler, vbox, expander):
        instances = []
        for Kind in handler.plugins:
            try:
                f = Kind()
            except:
                util.print_exc()
                continue
            else:
                instances.append(f)
        instances.sort()

        for child in vbox.get_children():
            child.destroy()
        del self.__plugins[:]

        for f in instances:
            try:
                vbox.pack_start(f, True, True, 0)
            except:
                util.print_exc()
                f.destroy()
                continue

            try:
                f.connect('preview', lambda *x: self.emit('preview'))
            except:
                try:
                    f.connect('changed', lambda *x: self.emit('changed'))
                except:
                    util.print_exc()
                    continue

            self.__plugins.append(f)

        vbox.show_all()

        # Don't display the expander if there aren't any plugins.
        if not self.__plugins:
            expander.set_expanded(False)
            expander.hide()
        else:
            expander.show()

    @property
    def filters(self):
        return self.__filters + self.__plugins
