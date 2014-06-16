# -*- coding: utf-8 -*-
# Copyright 2010-2011 Christoph Reiter, Steven Robertson
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

from gi.repository import Gtk, GObject, GLib

from quodlibet import config
from quodlibet import const

from quodlibet.parse import Query
from quodlibet.qltk.cbes import ComboBoxEntrySave
from quodlibet.qltk.ccb import ConfigCheckMenuItem
from quodlibet.qltk.x import SeparatorMenuItem
from quodlibet.util import limit_songs, DeferredSignal


class SearchBarBox(Gtk.HBox):
    """
        A search bar widget for inputting queries.

        signals:
            query-changed - a parsable query string
            focus-out - If the widget gets focused while being focused
                (usually for focusing the songlist)
    """

    __gsignals__ = {
        'query-changed': (
            GObject.SignalFlags.RUN_LAST, None, (object,)),
        'focus-out': (GObject.SignalFlags.RUN_LAST, None, ()),
        }

    timeout = 400

    def __init__(self, filename=None, completion=None, accel_group=None):
        super(SearchBarBox, self).__init__(spacing=6)

        if filename is None:
            filename = os.path.join(const.USERDIR, "lists", "queries")

        combo = ComboBoxEntrySave(filename, count=8,
                validator=Query.is_valid_color, title=_("Saved Searches"),
                edit_title=_("Edit saved searches..."))

        self.__deferred_changed = DeferredSignal(
            self.__filter_changed, timeout=self.timeout, owner=self)

        self.__combo = combo
        entry = combo.get_child()
        self.__entry = entry
        if completion:
            entry.set_completion(completion)

        self.__sig = combo.connect('text-changed', self.__text_changed)

        entry.connect('clear', self.__filter_changed)
        entry.connect('backspace', self.__text_changed)
        entry.connect('populate-popup', self.__menu)
        entry.connect('activate', self.__filter_changed)
        entry.connect('activate', self.__save_search)
        entry.connect('focus-out-event', self.__save_search)

        entry.set_placeholder_text(_("Search"))
        entry.set_tooltip_text(_("Search your library, "
                                 "using free text or QL queries"))

        combo.enable_clear_button()
        self.pack_start(combo, True, True, 0)

        if accel_group:
            key, mod = Gtk.accelerator_parse("<ctrl>L")
            accel_group.connect(key, mod, 0,
                    lambda *x: entry.mnemonic_activate(True))

        for child in self.get_children():
            child.show_all()

    def set_text(self, text):
        """Set the text without firing any signals"""

        self.__deferred_changed.abort()

        # deactivate all signals and change the entry text
        self.__inhibit()
        self.__entry.set_text(text)
        self.__uninhibit()

    def get_text(self):
        """Get the active text as unicode"""

        return self.__entry.get_text().decode("utf-8")

    def changed(self):
        """Triggers a filter-changed signal if the current text
        is a parsable query
        """

        self.__filter_changed()

    def __inhibit(self):
        self.__combo.handler_block(self.__sig)

    def __uninhibit(self):
        self.__combo.handler_unblock(self.__sig)

    def __menu(self, entry, menu):
        sep = SeparatorMenuItem()
        sep.show()
        menu.prepend(sep)

        cb = ConfigCheckMenuItem(
            _("Search after _typing"), 'settings', 'eager_search',
            populate=True)
        cb.set_tooltip_text(
            _("Show search results after the user stops typing."))
        cb.show()
        menu.prepend(cb)

    def __mnemonic_activate(self, label, group_cycling):
        widget = label.get_mnemonic_widget()
        if widget.is_focus():
            self.emit('focus-out')
            return True

    def __save_search(self, entry, *args):
        # only save the query on focus-out if eager_search is turned on
        if args and not config.getboolean('settings', 'eager_search'):
            return

        text = self.get_text().strip()
        if text and Query.is_parsable(text):
            # Adding the active text to the model triggers a changed signal
            # (get_active is no longer -1), so inhibit
            self.__inhibit()
            self.__combo.prepend_text(text)
            self.__combo.write()
            self.__uninhibit()

    def __filter_changed(self, *args):
        self.__deferred_changed.abort()
        text = self.get_text()
        if Query.is_parsable(text):
            GLib.idle_add(self.emit, 'query-changed', text)

    def __text_changed(self, *args):
        # the combobox has an active entry selected -> no timeout
        # todo: we need a timeout when the selection changed because
        # of keyboard input (up/down arrows)
        if self.__combo.get_active() != -1:
            self.__filter_changed()
            return

        if not config.getboolean('settings', 'eager_search'):
            return

        self.__deferred_changed()


class LimitSearchBarBox(SearchBarBox):
    """A version of `SearchBarBox` that allows specifying the limiting and
    weighting of a search."""

    class Limit(Gtk.HBox):
        __gsignals__ = {
            'changed': (GObject.SignalFlags.RUN_LAST, None, ()),
        }

        def __init__(self):
            super(LimitSearchBarBox.Limit, self).__init__(spacing=3)
            label = Gtk.Label(label=_("_Limit:"))
            self.pack_start(label, True, True, 0)

            self.__limit = limit = Gtk.SpinButton()
            self.__limit.connect("value-changed", self.__changed)
            limit.set_numeric(True)
            limit.set_range(0, 9999)
            limit.set_increments(5, 100)
            label.set_mnemonic_widget(limit)
            label.set_use_underline(True)
            self.pack_start(limit, True, True, 0)

            self.__weight = Gtk.CheckButton(
                label=_("_Weight"), use_underline=True)
            self.__weight.connect("toggled", self.__changed)
            self.pack_start(self.__weight, True, True, 0)

            for child in self.get_children():
                child.show()

        def __changed(self, *args):
            self.emit("changed")

        @property
        def value(self):
            return self.__limit.get_value_as_int()

        @property
        def weighted(self):
            return self.__weight.get_active()

    def __init__(self, show_limit=False, *args, **kwargs):
        super(LimitSearchBarBox, self).__init__(*args, **kwargs)
        self.__limit = self.Limit()
        self.pack_start(self.__limit, False, True, 0)
        self.__limit.set_no_show_all(not show_limit)
        self.__limit.connect("changed", self.__limit_changed)

    def __limit_changed(self, *args):
        self.changed()

    def limit(self, songs):
        if self.__limit.get_visible():
            return limit_songs(songs, self.__limit.value,
                               self.__limit.weighted)
        else:
            return songs

    def toggle_limit_widgets(self, button):
        """Toggles the visibility of the limit widget according to `button`"""
        if button.get_active():
            self.__limit.show()
        else:
            self.__limit.hide()
        self.changed()
