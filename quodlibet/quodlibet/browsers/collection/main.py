# -*- coding: utf-8 -*-
# Copyright 2010, 2012-2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation


from gi.repository import Gtk, GLib, Pango, Gdk

from quodlibet import qltk
from quodlibet import util
from quodlibet import config

from quodlibet.browsers.albums import AlbumTagCompletion
from quodlibet.browsers._base import Browser
from quodlibet.query import Query

from quodlibet.qltk.searchbar import SearchBarBox
from quodlibet.qltk.songsmenu import SongsMenu
from quodlibet.qltk.views import AllTreeView
from quodlibet.qltk.image import (get_scale_factor, get_pbosf_for_pixbuf,
    set_renderer_from_pbosf, scale, add_border_widget)
from quodlibet.qltk.x import ScrolledWindow, Align, SymbolicIconImage
from quodlibet.util.collection import Album
from quodlibet.util import connect_obj
from quodlibet.util.library import background_filter

from .models import (CollectionTreeStore, CollectionSortModel,
    CollectionFilterModel, MultiNode, UnknownNode)
from .prefs import get_headers, Preferences


class CollectionView(AllTreeView):
    def __init__(self):
        super(CollectionView, self).__init__()
        self.connect_after("row-expanded", self.__expand_helper)

    def __expand_helper(self, view, iter, path):
        model = view.get_model()
        children = list(model[path].iterchildren())
        if len(children) == 1:
            view.expand_row(children[0].path, False)

    def select_album(self, album, unselect=True):
        model = self.get_model()
        path = model.get_path_for_album(album)
        if path is not None:
            self.select_path(path, unselect)

    def select_path(self, path, unselect=True):
        path_idx = path
        if isinstance(path_idx, Gtk.TreePath):
            path_idx = path_idx.get_indices()
        for i, x in enumerate(path_idx[:-1]):
            self.expand_row(Gtk.TreePath(tuple(path_idx[:i + 1])), False)
        self.scroll_to_cell(path, use_align=True, row_align=0.5)
        selection = self.get_selection()
        assert selection
        if unselect:
            selection.unselect_all()
            self.set_cursor(path)
        else:
            selection.select_path(path)

    def get_selected_albums(self):
        selection = self.get_selection()
        assert selection
        model, paths = selection.get_selected_rows()
        albums = set()
        for path in paths:
            albums.update(model.get_albums_for_path(path))
        return albums


class CollectionBrowser(Browser, Gtk.VBox, util.InstanceTracker):
    __gsignals__ = Browser.__gsignals__

    name = _("Album Collection")
    accelerated_name = _("Album _Collection")
    priority = 5

    __model = None

    def pack(self, songpane):
        container = qltk.ConfigRHPaned(
            "browsers", "collectionbrowser_pos", 0.4)
        container.pack1(self, True, False)
        container.pack2(songpane, True, False)
        return container

    def unpack(self, container, songpane):
        container.remove(songpane)
        container.remove(self)

    @classmethod
    def _init_model(klass, library):
        klass.__model = model = CollectionTreeStore()
        klass.__albums = albums = library.albums

        albums.load()
        klass.__sigs = [
            albums.connect("added", klass._add_albums, model),
            albums.connect("removed", klass._remove_albums, model),
            albums.connect("changed", klass._change_albums, model),
        ]

        klass.set_hierarchy()

    @classmethod
    def _destroy_model(klass):
        for sig in klass.__sigs:
            klass.__albums.disconnect(sig)
        klass.__model = None
        del klass.__sigs

    def _refilter(self):
        if hasattr(self, "view"):
            self.view.get_model().refilter()

    @classmethod
    def set_hierarchy(klass):
        klass.__model.set_albums(get_headers(), klass.__albums.values())
        for inst in klass.instances():
            inst._refilter()

    @classmethod
    def _add_albums(klass, library, added, model):
        model.add_albums(added)

    @classmethod
    def _remove_albums(klass, library, removed, model):
        model.remove_albums(removed)

    @classmethod
    def _change_albums(klass, library, changed, model):
        model.change_albums(changed)

    def __init__(self, library):
        super(CollectionBrowser, self).__init__(spacing=6)
        self._register_instance()
        if self.__model is None:
            self._init_model(library)

        sw = ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        self.view = view = CollectionView()
        view.set_headers_visible(False)
        model_sort = CollectionSortModel(model=self.__model)
        model_filter = CollectionFilterModel(child_model=model_sort)
        self.__filter = None
        self.__bg_filter = background_filter()
        model_filter.set_visible_func(self.__parse_query)
        view.set_model(model_filter)

        def sort(model, i1, i2, data):
            t1, t2 = model[i1][0], model[i2][0]
            if t1 is None or t2 is None:
                # FIXME: why?
                return 0

            # FIXME: order this deterministically
            if t1 is MultiNode or t1 is UnknownNode or \
                    t2 is MultiNode or t2 is UnknownNode:
                return -cmp(t1, t2)

            if not isinstance(t1, Album):
                return cmp(util.human_sort_key(t1), util.human_sort_key(t2))

            a1, a2 = t1, t2
            return (cmp(a1.peoplesort and a1.peoplesort[0],
                        a2.peoplesort and a2.peoplesort[0]) or
                        cmp(a1.date or "ZZZZ", a2.date or "ZZZZ") or
                        cmp((a1.sort, a1.key), (a2.sort, a2.key)))

        model_sort.set_sort_func(0, sort)
        model_sort.set_sort_column_id(0, Gtk.SortType.ASCENDING)

        column = Gtk.TreeViewColumn("albums")

        def cell_data(column, cell, model, iter_, data):
            markup = model.get_markup(self.__model.tags, iter_)
            cell.markup = markup
            cell.set_property('markup', markup)

        def get_scaled_cover(album):
            # XXX: Cache this somewhere else
            cover = None
            if not hasattr(album, "_scaled_cover"):
                scale_factor = get_scale_factor(self)
                album.scan_cover(scale_factor=scale_factor)
                if album.cover:
                    s = 25 * scale_factor
                    cover = scale(album.cover, (s, s))
                    album._scaled_cover = cover
            else:
                cover = album._scaled_cover
            return cover

        def cell_data_pb(column, cell, model, iter_, data):
            album = model.get_album(iter_)
            if album is None:
                cell.set_property('stock_id', Gtk.STOCK_DIRECTORY)
            else:
                cover = get_scaled_cover(album)
                if cover:
                    round_ = config.getboolean("albumart", "round")
                    cover = add_border_widget(
                        cover, view, cell, round=round_)
                    pbosf = get_pbosf_for_pixbuf(self, cover)
                    set_renderer_from_pbosf(cell, pbosf)
                else:
                    cell.set_property('stock_id', Gtk.STOCK_CDROM)

        imgrender = Gtk.CellRendererPixbuf()
        render = Gtk.CellRendererText()
        if view.supports_hints():
            render.set_property('ellipsize', Pango.EllipsizeMode.END)
        column.pack_start(imgrender, False)
        column.pack_start(render, True)
        column.set_cell_data_func(render, cell_data)
        column.set_cell_data_func(imgrender, cell_data_pb)
        view.append_column(column)

        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(view)

        hbox = Gtk.HBox(spacing=6)

        prefs = Gtk.Button()
        prefs.add(SymbolicIconImage("emblem-system", Gtk.IconSize.MENU))
        prefs.connect('clicked', lambda *x: Preferences(self))

        search = SearchBarBox(completion=AlbumTagCompletion(),
                              accel_group=self.accelerators)

        search.connect('query-changed', self.__update_filter)
        self.__search = search

        hbox.pack_start(search, True, True, 0)
        hbox.pack_start(prefs, False, True, 0)

        self.pack_start(Align(hbox, left=6, top=6), False, True, 0)
        self.pack_start(sw, True, True, 0)

        view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.__sig = view.get_selection().connect('changed',
            self.__selection_changed)
        view.connect('row-activated', self.__play)
        connect_obj(view, 'popup-menu', self.__popup, view, library)

        targets = [("text/x-quodlibet-songs", Gtk.TargetFlags.SAME_APP, 1),
                   ("text/uri-list", 0, 2)]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        view.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.COPY)
        view.connect("drag-data-get", self.__drag_data_get)

        self.connect("destroy", self.__destroy)

        self.show_all()

    def __inhibit(self):
        self.view.get_selection().handler_block(self.__sig)

    def __uninhibit(self):
        self.view.get_selection().handler_unblock(self.__sig)

    def __parse_query(self, model, iter_, data):
        f, b = self.__filter, self.__bg_filter
        if f is None and b is None:
            return True

        def check_album(obj):
            if b is None:
                return f(obj)
            if f is None:
                return b(obj)
            return f(obj) and b(obj)

        obj = model.get_value(iter_)
        if isinstance(obj, Album):
            return check_album(obj)
        else:
            for album in model.iter_albums(iter_):
                if check_album(album):
                    return True
            return False

    def __update_filter(self, entry, text):
        self.__filter = None
        if not Query.match_all(text):
            tags = self.__model.tags + ["album"]
            self.__filter = Query(text, star=tags).search
        self.__bg_filter = background_filter()

        self.view.get_model().refilter()

    def __destroy(self, browser):
        klass = type(browser)
        if not klass.instances():
            klass._destroy_model()

    def __drag_data_get(self, view, ctx, sel, tid, etime):
        songs = self.__get_selected_songs()
        if tid == 1:
            qltk.selection_set_songs(sel, songs)
        else:
            sel.set_uris([song("~uri") for song in songs])

    def __popup(self, view, library):
        songs = self.__get_selected_songs(view.get_selection())
        menu = SongsMenu(library, songs)
        menu.show_all()
        return view.popup_menu(menu, 0, Gtk.get_current_event_time())

    def __play(self, view, path, col):
        model = view.get_model()
        if isinstance(model[path][0], Album):
            self.songs_activated()
        else:
            if view.row_expanded(path):
                view.collapse_row(path)
            else:
                view.expand_row(path, False)

    def __get_selected_songs(self, sort=True):
        albums = self.view.get_selected_albums()
        songs = []
        if sort:
            for album in albums:
                songs.extend(sorted(album.songs))
        else:
            for album in albums:
                songs.extend(album.songs)
        return songs

    def __selection_changed(self, selection):
        songs = self.__get_selected_songs(False)
        if songs is not None:
            GLib.idle_add(self.songs_selected, songs)

    def can_filter_albums(self):
        return True

    def filter_albums(self, album_keys):
        albums = filter(None, [self.__albums.get(k) for k in album_keys])
        if albums:
            self.view.select_album(albums[0], unselect=True)
        for album in albums[1:]:
            self.view.select_album(album, unselect=False)

    def can_filter_text(self):
        return True

    def filter_text(self, text):
        self.__search.set_text(text)
        if Query.is_parsable(text):
            self.__update_filter(self.__search, text)
            self.activate()

    def unfilter(self):
        pass

    def activate(self):
        self.view.get_selection().emit('changed')

    def restore(self):
        paths = config.get("browsers", "collection", "").split("\t")
        paths = [tuple(map(int, path.split())) for path in paths]
        self.__inhibit()
        if paths:
            if not paths[0]:
                self.__uninhibit()
                return
            self.view.select_path(paths[0], unselect=True)
        for path in paths[1:]:
            self.view.select_path(path, unselect=False)
        self.__uninhibit()

    def scroll(self, song):
        album = self.__albums.get(song.album_key)
        if album:
            self.view.select_album(album)

    def save(self):
        model, paths = self.view.get_selection().get_selected_rows()
        paths = "\t".join([" ".join(map(str, path)) for path in paths])
        config.set("browsers", "collection", paths)


browsers = [CollectionBrowser]
