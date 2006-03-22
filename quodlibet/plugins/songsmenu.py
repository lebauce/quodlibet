# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

import os
import gtk
import qltk
import util

from traceback import print_exc
from plugins import ListWrapper, Manager

__all__ = [] # trick out old plugin manager

class SongsMenuPlugin(gtk.ImageMenuItem):
    """Plugins of this type are subclasses of gtk.ImageMenuItem.
    They will be added, in alphabetical order, to the "Plugins" menu
    that appears when songs or lists of songs are right-clicked.
    They provide one or more of the following instance methods:
    
        self.plugin_single_song(song)
        self.plugin_song(song)
        self.plugin_songs(songs)
        self.plugin_single_album(album)
        self.plugin_album(album)
        self.plugin_albums(albums)

    All matching provided callables on a single object are called in the
    above order if they match until one returns a true value. They are
    not called with true AudioFile objects, but rather wrappers that
    automatically detect metadata or disk changes, and save or reload
    the files as appropriate.

    The single_ variant is only called if a single song/album is selected.

    The singular tense is called once for each selected song/album, but the
    plural tense is called with a list of songs/albums.

    An album is a list of songs all with the same album, labelid, and
    musicbrainz_albumid tags (like in the Album List).

    To make your plugin insensitive if unsupported songs are selected,
    a method that takes a list of songs and returns True or False to set
    the sensitivity of the menu entry:
        self.plugin_handles(songs)

    When these functions are called, the self.plugin_window will be
    available. This is the gtk.Window the plugin was invoked from. This
    provides access to two important widgets, self.plugin_window.browser
    and self.plugin_window.songlist.

    All of this is managed by the constructor for SongsMenuPlugin, so
    make sure it gets called if you override it (you shouldn't have to).
    """

    plugin_single_song = None
    plugin_song = None
    plugin_songs = None
    plugin_single_album = None
    plugin_album = None
    plugin_albums = None

    def __init__(self, songs):
        super(SongsMenuPlugin, self).__init__(self.PLUGIN_NAME)
        try: i = gtk.image_new_from_stock(self.PLUGIN_ICON, gtk.ICON_SIZE_MENU)
        except AttributeError: pass
        else: self.set_image(i)
        self.set_sensitive(bool(self.plugin_handles(songs)))

    def plugin_handles(self, songs):
        return True

class SongsMenuPlugins(Manager):
    Kinds = [SongsMenuPlugin]

    def Menu(self, watcher, parent, songs):
        songs = ListWrapper(songs)
        parent = qltk.get_top_parent(parent)

        albums = {}
        for song in songs:
            key = (song.get("album"), song.get("labelid"),
                   song.get("musicbrainz_albumid"))
            if key not in albums:
                albums[key] = []
            albums[key].append(song)

        albums = albums.values()
        map(list.sort, albums)

        items = []
        kinds = self.find_subclasses(SongsMenuPlugin)
        kinds.sort(lambda a, b: cmp(a.PLUGIN_NAME, b.PLUGIN_NAME))
        for Kind in kinds:
            connected = False
            attrs = ['plugin_song', 'plugin_songs',
                     'plugin_album', 'plugin_albums']
            
            if len(songs) == 1: attrs.append('plugin_single_song')
            if len(albums) == 1: attrs.append('plugin_single_album')
            usable = max([callable(getattr(Kind, s)) for s in attrs])
            if usable: items.append(Kind(songs))

        if items:
            menu = gtk.Menu()
            for item in items:
                menu.append(item)
                item.connect(
                    'activate', self.__handle, watcher, parent, songs, albums)
        else: menu = None
        return menu

    def __handle(self, plugin, watcher, parent, songs, albums):
        plugin.plugin_window = parent

        if len(songs) == 1 and callable(plugin.plugin_single_song):
            try: plugin.plugin_single_song(songs[0])
            except Exception: print_exc()
        if len(albums) == 1 and callable(plugin.plugin_single_album):
            try: plugin.plugin_single_album(albums[0])
            except Exception: print_exc()

        if callable(plugin.plugin_songs):
            try: plugin.plugin_songs(songs)
            except Exception: print_exc()
        if callable(plugin.plugin_song):
            try: map(plugin.plugin_song, songs)
            except Exception: print_exc()

        if callable(plugin.plugin_albums):
            try: plugin.plugin_albums(albums)
            except Exception: print_exc()
        if callable(plugin.plugin_album):
            try: map(plugin.plugin_album, albums)
            except Exception: print_exc()

        del(plugin.plugin_window)

        self.__check_change(watcher, parent, filter(None, songs))

    def __check_change(self, watcher, parent, songs):
        needs_write = filter(lambda s: s._needs_write, songs)

        if needs_write:
            from qltk.wlw import WritingWindow
            win = WritingWindow(parent, len(needs_write))
            for song in needs_write:
                try: song._song.write()
                except Exception:
                    qltk.ErrorMessage(
                        None, _("Unable to edit song"),
                        _("Saving <b>%s</b> failed. The file "
                          "may be read-only, corrupted, or you "
                          "do not have permission to edit it.")%(
                        util.escape(song('~basename')))).run()
                win.step()
            win.destroy()
            while gtk.events_pending(): gtk.main_iteration()

        changed = []
        for song in songs:
            needs_reload = []
            if song._was_updated(): changed.append(song._song)
            elif not song.valid() and song.exists():
                watcher.reload(song._song)
        watcher.changed(changed)