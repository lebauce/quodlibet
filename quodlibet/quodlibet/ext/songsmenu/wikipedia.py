# Copyright 2005 Inigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from urllib import quote

from gi.repository import Gtk

from quodlibet import config
from quodlibet.util import website
from quodlibet.plugins.songsmenu import SongsMenuPlugin

WIKI_URL = "http://%s.wikipedia.org/wiki/"
try:
    config.get("plugins", __name__)
except:
    config.set("plugins", __name__, "en")


class WikiSearch(object):
    PLUGIN_ICON = Gtk.STOCK_OPEN
    PLUGIN_VERSION = '0.14'

    def changed(self, e):
        config.set("plugins", __name__, e.get_text())
    changed = classmethod(changed)

    def PluginPreferences(self, parent):
        hb = Gtk.HBox(spacing=3)
        hb.set_border_width(6)
        e = Gtk.Entry(max_length=2)
        e.set_width_chars(3)
        e.set_text(config.get('plugins', __name__))
        e.connect('changed', self.changed)
        hb.pack_start(Gtk.Label("Search at http://"), False, True, 0)
        hb.pack_start(e, False, True, 0)
        hb.pack_start(Gtk.Label(".wikipedia.org"), False, True, 0)
        hb.show_all()
        return hb
    PluginPreferences = classmethod(PluginPreferences)

    def plugin_songs(self, songs):
        l = dict.fromkeys([song(self.k) for song in songs]).keys()
        for a in l:
            a = quote(str(a).title().replace(' ', '_'))
            website(WIKI_URL % config.get('plugins', __name__) + a)


class WikiArtist(WikiSearch, SongsMenuPlugin):
    PLUGIN_ID = 'Search artist in Wikipedia'
    PLUGIN_NAME = _('Search artist in Wikipedia')
    k = 'artist'


class WikiAlbum(WikiSearch, SongsMenuPlugin):
    PLUGIN_ID = 'Search album in Wikipedia'
    PLUGIN_NAME = _('Search album in Wikipedia')
    k = 'album'
