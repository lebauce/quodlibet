# -*- coding: utf-8 -*-
# Copyright 2006 Joe Wreschnig
#      2013-2014 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk

from quodlibet import qltk

from quodlibet.util import print_exc
from quodlibet.qltk.msg import WarningMessage
from quodlibet.qltk.delete import TrashMenuItem, trash_songs
from quodlibet.qltk.information import Information
from quodlibet.qltk.properties import SongProperties
from quodlibet.qltk.x import SeparatorMenuItem, Button
from quodlibet.qltk.ratingsmenu import RatingsMenuItem
from quodlibet.qltk import get_top_parent, get_menu_item_top_parent
from quodlibet.plugins import PluginManager, PluginHandler
from quodlibet.plugins.songsmenu import SongsMenuPlugin
from quodlibet.util.songwrapper import ListWrapper, check_wrapper_changed


class ConfirmMultiSongInvoke(WarningMessage):
    """Dialog to confirm invoking a plugin with X songs in case X is high"""

    RESPONSE_INVOKE = 1

    def __init__(self, parent, plugin_name, count):
        title = ngettext("Run the plugin \"%(name)s\" on %(count)d song?",
                         "Run the plugin \"%(name)s\" on %(count)d songs?",
                         count) % {"name": plugin_name, "count": count}

        super(ConfirmMultiSongInvoke, self).__init__(
            get_top_parent(parent),
            title, "",
            buttons=Gtk.ButtonsType.NONE)

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        delete_button = Button(_("_Run Plugin"), Gtk.STOCK_EXECUTE)
        delete_button.show()
        self.add_action_widget(delete_button, self.RESPONSE_INVOKE)
        self.set_default_response(Gtk.ResponseType.CANCEL)

    @classmethod
    def confirm(cls, parent, plugin_name, count):
        """Returns if the action was confirmed"""

        resp = cls(parent, plugin_name, count).run()
        return resp == cls.RESPONSE_INVOKE


class ConfirmMultiAlbumInvoke(WarningMessage):
    """Dialog to confirm invoking a plugin with X albums in case X is high"""

    RESPONSE_INVOKE = 1

    def __init__(self, parent, plugin_name, count):
        title = ngettext("Run the plugin \"%(name)s\" on %(count)d album?",
                         "Run the plugin \"%(name)s\" on %(count)d albums?",
                         count) % (plugin_name, count)

        super(ConfirmMultiAlbumInvoke, self).__init__(
            get_top_parent(parent),
            title, "",
            buttons=Gtk.ButtonsType.NONE)

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        delete_button = Button(_("_Run Plugin"), Gtk.STOCK_EXECUTE)
        delete_button.show()
        self.add_action_widget(delete_button, self.RESPONSE_INVOKE)
        self.set_default_response(Gtk.ResponseType.CANCEL)

    @classmethod
    def confirm(cls, parent, plugin_name, count):
        """Returns if the action was confirmed"""

        resp = cls(parent, plugin_name, count).run()
        return resp == cls.RESPONSE_INVOKE


class SongsMenuPluginHandler(PluginHandler):

    def __init__(self, song_confirmer=None, album_confirmer=None):
        """custom confirmers for testing"""

        self.__plugins = []

        self._confirm_multiple_songs = ConfirmMultiSongInvoke.confirm
        if song_confirmer is not None:
            self._confirm_multiple_songs = song_confirmer

        self._confirm_multiple_albums = ConfirmMultiAlbumInvoke.confirm
        if album_confirmer is not None:
            self._confirm_multiple_albums = album_confirmer

    def Menu(self, library, songs):
        songs = ListWrapper(songs)

        attrs = ['plugin_song', 'plugin_songs',
                 'plugin_album', 'plugin_albums']

        if len(songs) == 1:
            attrs.append('plugin_single_song')

        last = (songs and songs[-1]) or None
        for song in songs:
            if song.album_key != last.album_key:
                break
            last = song
        else:
            attrs.append('plugin_single_album')

        items = []
        kinds = self.__plugins
        kinds.sort(key=lambda plugin: plugin.PLUGIN_ID)
        for Kind in kinds:
            usable = max([callable(getattr(Kind, s)) for s in attrs])
            if usable:
                try:
                    items.append(Kind(songs, library))
                except:
                    print_e("Couldn't initialise song plugin %s. Stack trace:"
                            % Kind)
                    print_exc()
        items = filter(lambda i: i.initialized, items)

        if items:
            menu = Gtk.Menu()
            for item in items:
                try:
                    menu.append(item)
                    args = (library, songs)
                    if item.get_submenu():
                        for subitem in item.get_submenu().get_children():
                            subitem.connect(
                                'activate', self.__on_activate, item, *args)
                    else:
                        item.connect(
                            'activate', self.__on_activate, item, *args)
                except:
                    print_exc()
                    item.destroy()

        else:
            menu = None
        return menu

    def __get_albums(self, songs):
        albums = {}
        for song in songs:
            key = song.album_key
            if key not in albums:
                albums[key] = []
            albums[key].append(song)

        albums = albums.values()
        for album in albums:
            album.sort()
        return albums

    def handle(self, plugin_id, library, parent, songs):
        """Start a song menu plugin directly without a menu"""

        parent = get_top_parent(parent)

        for plugin in self.__plugins:
            if plugin.PLUGIN_ID == plugin_id:
                songs = ListWrapper(songs)
                try:
                    plugin = plugin(songs, library)
                except Exception:
                    print_exc()
                else:
                    self.__handle(plugin, plugin, library, songs, parent)
                return

    def __on_activate(self, item, plugin, library, songs):
        parent = get_menu_item_top_parent(item)
        self.__handle(item, plugin, library, songs, parent)

    def __handle(self, item, plugin, library, songs, parent):
        if len(songs) == 0:
            return

        try:
            if len(songs) == 1 and callable(plugin.plugin_single_song):
                try:
                    ret = plugin.plugin_single_song(songs[0])
                except Exception:
                    print_exc()
                else:
                    if ret:
                        return
            if callable(plugin.plugin_song):
                total = len(songs)
                if total > plugin.MAX_INVOCATIONS:
                    if not self._confirm_multiple_songs(
                            parent, plugin.PLUGIN_NAME, total):
                        return

                try:
                    ret = map(plugin.plugin_song, songs)
                except Exception:
                    print_exc()
                else:
                    if max(ret):
                        return
            if callable(plugin.plugin_songs):
                try:
                    ret = plugin.plugin_songs(songs)
                except Exception:
                    print_exc()
                else:
                    if ret:
                        return

            if plugin.handles_albums:
                albums = self.__get_albums(songs)
                total = len(albums)
                if total > plugin.MAX_INVOCATIONS:
                    if not self._confirm_multiple_albums(
                            parent, plugin.PLUGIN_NAME, total):
                        return

            if callable(plugin.plugin_single_album) and len(albums) == 1:
                try:
                    ret = plugin.plugin_single_album(albums[0])
                except Exception:
                    print_exc()
                else:
                    if ret:
                        return
            if callable(plugin.plugin_album):
                try:
                    ret = map(plugin.plugin_album, albums)
                except Exception:
                    print_exc()
                else:
                    if max(ret):
                        return
            if callable(plugin.plugin_albums):
                try:
                    ret = plugin.plugin_albums(albums)
                except Exception:
                    print_exc()
                else:
                    if ret:
                        return

        finally:
            check_wrapper_changed(library, parent, filter(None, songs))

    def plugin_handle(self, plugin):
        return issubclass(plugin.cls, SongsMenuPlugin)

    def plugin_enable(self, plugin):
        self.__plugins.append(plugin.cls)

    def plugin_disable(self, plugin):
        self.__plugins.remove(plugin.cls)


class SongsMenu(Gtk.Menu):
    plugins = SongsMenuPluginHandler()

    @classmethod
    def init_plugins(cls):
        PluginManager.instance.register_handler(cls.plugins)

    def __init__(self, library, songs, plugins=True, playlists=True,
                 queue=True, devices=True, remove=True, delete=False,
                 edit=True, ratings=True, items=None, accels=True):
        super(SongsMenu, self).__init__()

        # The library may actually be a librarian; if it is, use it,
        # otherwise find the real librarian.
        librarian = getattr(library, 'librarian', library)

        if ratings:
            ratings_item = RatingsMenuItem(songs, librarian)
            ratings_item.set_sensitive(bool(songs))
            self.append(ratings_item)
            self.separate()

        # external item groups
        for subitems in reversed(items or []):
            self.separate()
            for item in subitems:
                self.append(item)
            self.separate()

        if plugins:
            submenu = self.plugins.Menu(librarian, songs)
            if submenu is not None:
                b = qltk.MenuItem(_("_Plugins"), Gtk.STOCK_EXECUTE)
                b.set_sensitive(bool(songs))
                self.append(b)
                b.set_submenu(submenu)
                self.append(SeparatorMenuItem())

        in_lib = True
        can_add = True
        is_file = True
        for song in songs:
            if song not in library:
                in_lib = False
            if not song.can_add:
                can_add = False
            if not song.is_file:
                is_file = False

        if playlists:
            # Needed here to avoid a circular import; most browsers use
            # a SongsMenu, but SongsMenu needs access to the playlist
            # browser for this item.

            # FIXME: Two things are now importing browsers, so we need
            # some kind of inversion of control here.
            from quodlibet.browsers.playlists.menu import PlaylistMenu
            try:
                submenu = PlaylistMenu(songs)
            except AttributeError as e:
                print_w("Couldn't get Playlists menu: %s" % e)
            else:
                b = qltk.MenuItem(_("Play_lists"), Gtk.STOCK_ADD)
                b.set_sensitive(can_add and bool(songs))
                b.set_submenu(submenu)
                self.append(b)
        if queue:
            b = qltk.MenuItem(_("Add to _Queue"), Gtk.STOCK_ADD)

            def enqueue_cb(item, songs):
                songs = filter(lambda s: s.can_add, songs)
                if songs:
                    from quodlibet import app
                    app.window.playlist.enqueue(songs)

            b.connect('activate', enqueue_cb, songs)
            if accels:
                qltk.add_fake_accel(b, "<ctrl>Return")
            self.append(b)
            b.set_sensitive(can_add and bool(songs))

        if devices:
            from quodlibet import browsers
            try:
                browsers.media
            except AttributeError:
                pass
            else:
                if browsers.media.MediaDevices in browsers.browsers:
                    submenu = browsers.media.Menu(songs, library)
                    b = qltk.MenuItem(_("_Copy to Device"), Gtk.STOCK_COPY)
                    b.set_sensitive(
                        can_add and len(submenu) > 0 and bool(songs))
                    b.set_submenu(submenu)
                    self.append(b)

        if remove or delete:
            self.separate()

        if remove:
            b = qltk.MenuItem(_("_Remove from library"), Gtk.STOCK_REMOVE)
            if callable(remove):
                b.connect('activate', lambda item: remove(songs))
            else:
                def remove_cb(item, songs, library):
                    library.remove(set(songs))

                b.connect('activate', remove_cb, songs, library)
                b.set_sensitive(in_lib and bool(songs))
            self.append(b)

        if delete:
            if callable(delete):
                b = Gtk.ImageMenuItem(Gtk.STOCK_DELETE, use_stock=True)
                b.connect('activate', lambda item: delete(songs))
            else:
                b = TrashMenuItem()

                def trash_cb(item):
                    parent = get_menu_item_top_parent(item)
                    trash_songs(parent, songs, librarian)

                b.connect('activate', trash_cb)
                b.set_sensitive(is_file and bool(songs))
            self.append(b)

        if edit:
            self.separate()
            b = qltk.MenuItem(_("Edit _Tags"), Gtk.STOCK_PROPERTIES)
            b.set_sensitive(bool(songs))
            if accels:
                qltk.add_fake_accel(b, "<alt>Return")

            def song_properties_cb(menu_item):
                parent = get_menu_item_top_parent(menu_item)
                window = SongProperties(librarian, songs, parent)
                window.show()

            b.connect('activate', song_properties_cb)
            self.append(b)

            b = Gtk.ImageMenuItem(label=Gtk.STOCK_INFO, use_stock=True)
            b.set_sensitive(bool(songs))
            if accels:
                qltk.add_fake_accel(b, "<ctrl>I")

            def information_cb(menu_item):
                parent = get_menu_item_top_parent(menu_item)
                window = Information(librarian, songs, parent)
                window.show()
            b.connect('activate', information_cb)
            self.append(b)

        def selection_done_cb(menu):
            menu.destroy()

        self.connect('selection-done', selection_done_cb)

    def separate(self):
        if not self.get_children():
            return
        elif not isinstance(self.get_children()[-1], Gtk.SeparatorMenuItem):
            self.append(SeparatorMenuItem())

    def preseparate(self):
        if not self.get_children():
            return
        elif not isinstance(self.get_children()[0], Gtk.SeparatorMenuItem):
            self.prepend(SeparatorMenuItem())
