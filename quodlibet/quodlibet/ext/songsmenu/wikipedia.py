# -*- coding: utf-8 -*-
# Copyright 2005 Inigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from urllib import quote

from gi.repository import Gtk

from quodlibet import config
from quodlibet.util import website
from quodlibet.qltk.entry import Entry
from quodlibet.plugins.songsmenu import SongsMenuPlugin

WIKI_URL = "http://%s.wikipedia.org/wiki/"


def get_lang():
    return config.get("plugins", __name__, "en")


def set_lang(value):
    config.set("plugins", __name__, value)


class WikiSearch(object):
    PLUGIN_ICON = Gtk.STOCK_OPEN

    @classmethod
    def changed(self, e):
        set_lang(e.get_text())

    @classmethod
    def PluginPreferences(self, parent):
        hb = Gtk.HBox(spacing=3)
        hb.set_border_width(6)
        e = Entry(max_length=2)
        e.set_width_chars(3)
        e.set_max_width_chars(3)
        e.set_text(get_lang())
        e.connect('changed', self.changed)
        hb.pack_start(
            Gtk.Label(label=_("Search at %(website)s") % {
                "website": "http://"}),
            False, True, 0)
        hb.pack_start(e, False, True, 0)
        hb.pack_start(Gtk.Label(label=".wikipedia.org"), False, True, 0)
        hb.show_all()
        return hb

    def plugin_songs(self, songs):
        l = dict.fromkeys([song(self.k) for song in songs]).keys()
        for a in l:
            a = quote(str(a).title().replace(' ', '_'))
            website(WIKI_URL % get_lang() + a)


class WikiArtist(WikiSearch, SongsMenuPlugin):
    PLUGIN_ID = 'Search artist in Wikipedia'
    PLUGIN_NAME = _('Search Artist in Wikipedia')
    PLUGIN_DESC = _('Opens a browser window with Wikipedia article '
                    'on the playing song artist.')
    k = 'artist'


class WikiAlbum(WikiSearch, SongsMenuPlugin):
    PLUGIN_ID = 'Search album in Wikipedia'
    PLUGIN_NAME = _('Search Album in Wikipedia')
    PLUGIN_DESC = _('Opens a browser window with Wikipedia article '
                    'on the playing song album.')
    k = 'album'
