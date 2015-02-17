# -*- coding: utf-8 -*-
# Copyright 2004-2013 Joe Wreschnig, Michael Urman, Iñigo Serna,
#                     Christoph Reiter, Steven Robertson, Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation


from gi.repository import Gtk, GLib

from quodlibet import config
from quodlibet import qltk

from quodlibet.browsers._base import Browser
from quodlibet.query import Query
from quodlibet.qltk.ccb import ConfigCheckMenuItem
from quodlibet.qltk.completion import LibraryTagCompletion
from quodlibet.qltk.menubutton import MenuButton
from quodlibet.qltk.songlist import SongList
from quodlibet.qltk.searchbar import LimitSearchBarBox
from quodlibet.qltk.x import Alignment, SymbolicIconImage


class PreferencesButton(Gtk.HBox):

    def __init__(self, search_bar_box):
        super(PreferencesButton, self).__init__()
        menu = Gtk.Menu()

        limit_item = ConfigCheckMenuItem(
            _("_Limit Results"), "browsers", "search_limit", True)
        limit_item.connect("toggled", search_bar_box.toggle_limit_widgets)
        menu.append(limit_item)
        menu.show_all()

        button = MenuButton(
            SymbolicIconImage("emblem-system", Gtk.IconSize.MENU),
            arrow=True)
        button.set_menu(menu)
        self.pack_start(button, True, True, 0)


class SearchBar(Gtk.VBox, Browser):
    """Like EmptyBar, but the user can also enter a query manually"""

    __gsignals__ = Browser.__gsignals__

    name = _("Search Library")
    accelerated_name = _("_Search Library")
    priority = 1
    in_menu = True

    def pack(self, songpane):
        container = Gtk.VBox(spacing=6)
        container.pack_start(self, False, True, 0)
        container.pack_start(songpane, True, True, 0)
        return container

    def unpack(self, container, songpane):
        container.remove(songpane)
        container.remove(self)

    def __init__(self, library):
        super(SearchBar, self).__init__()
        self.set_spacing(6)

        self._query = None
        self._library = library

        completion = LibraryTagCompletion(library.librarian)
        self.accelerators = Gtk.AccelGroup()

        show_limit = config.getboolean("browsers", "search_limit")
        sbb = LimitSearchBarBox(completion=completion,
                                accel_group=self.accelerators,
                                show_limit=show_limit)

        sbb.connect('query-changed', self.__text_parse)
        sbb.connect('focus-out', self.__focus)
        self._sb_box = sbb

        prefs = PreferencesButton(sbb)
        sbb.pack_start(prefs, False, True, 0)

        align = Alignment(sbb, left=6, right=6, top=6)
        self.pack_start(align, False, True, 0)
        self.connect('destroy', self.__destroy)
        self.show_all()

    def _get_text(self):
        return self._sb_box.get_text()

    def _set_text(self, text):
        self._sb_box.set_text(text)

    def __destroy(self, *args):
        self._sb_box = None

    def __focus(self, widget, *args):
        qltk.get_top_parent(widget).songlist.grab_focus()

    def _get_songs(self):
        text = self._get_text()
        try:
            self._query = Query(text, star=SongList.star)
        except Query.error:
            pass
        else:
            return self._query.filter(self._library)

    def activate(self):
        songs = self._get_songs()
        if songs is not None:
            songs = self._sb_box.limit(songs)
            GLib.idle_add(self.songs_selected, songs)

    def __text_parse(self, bar, text):
        self.activate()

    def save(self):
        config.set("browsers", "query_text", self._get_text())

    def restore(self):
        try:
            text = config.get("browsers", "query_text")
        except config.Error:
            return

        self._set_text(text)

    def finalize(self, restore):
        config.set("browsers", "query_text", "")

    def can_filter_text(self):
        return True

    def filter_text(self, text):
        self._set_text(text)
        self.activate()

    def unfilter(self):
        self.filter_text("")

    def active_filter(self, song):
        if self._query is not None:
            return self._query.search(song)
        else:
            return True


browsers = [SearchBar]
