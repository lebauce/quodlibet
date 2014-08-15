# Copyright 2005 Joe Wreschnig
#           2012 Christoph Reiter
#      2011-2013 Nick Boultbee
#           2014 Jan Path
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, GLib, Gdk, GObject

from quodlibet import app
from quodlibet import config
from quodlibet import const
from quodlibet import qltk
from quodlibet import util

from quodlibet.parse import Query, Pattern
from quodlibet.qltk.information import Information
from quodlibet.qltk.properties import SongProperties
from quodlibet.qltk.views import AllTreeView, DragScroll
from quodlibet.qltk.ratingsmenu import RatingsMenuItem
from quodlibet.qltk.ratingsmenu import ConfirmRateMultipleDialog
from quodlibet.qltk.songmodel import PlaylistModel
from quodlibet.util.uri import URI
from quodlibet.formats._audio import TAG_TO_SORT, AudioFile
from quodlibet.qltk.x import SeparatorMenuItem
from quodlibet.util import human_sort_key
from quodlibet.qltk.songlistcolumns import create_songlist_column


DND_QL, DND_URI_LIST = range(2)


class SongInfoSelection(GObject.Object):
    """
    InfoSelection: Songs which get included in the status bar
    summary. changed gets fired after any of the songs in the
    selection or the selection it self have changed.
    The signal is async.

    Two selection states:
        - 0 or 1 selected row: all rows
        - 2 or more: only the selected rows

    The signals fires if the state changes.

    FIXME:
        row-changed for song lists isn't implemented (performance).
        Since a library change could change the selection it should
        also trigger a this.

        Since this would happen quite often (song stat changes) and
        would lead to a complete recalc in the common case ignore it for
        now.
    """

    __gsignals__ = {
        # changed(songs:list)
        'changed': (GObject.SignalFlags.RUN_LAST, None, (object,))
    }

    def __init__(self, songlist):
        super(SongInfoSelection, self).__init__()

        self.__idle = None
        self.__songlist = songlist
        self.__selection = sel = songlist.get_selection()
        self.__count = sel.count_selected_rows()
        self.__sel_id = sel.connect('changed', self.__selection_changed_cb)

    def destroy(self):
        self.__selection.disconnect(self.__sel_id)
        if self.__idle:
            GLib.source_remove(self.__idle)

    def _update_songs(self, songs):
        """After making changes (filling the list) call this to
        skip any queued changes and emit the passed songs instead"""
        self.__emit_info_selection(songs)
        self.__count = len(songs)

    def __idle_emit(self, songs):
        if songs is None:
            if self.__count <= 1:
                songs = self.__songlist.get_songs()
            else:
                songs = self.__songlist.get_selected_songs()
        self.emit('changed', songs)
        self.__idle = None
        False

    def __emit_info_selection(self, songs=None):
        if self.__idle:
            GLib.source_remove(self.__idle)
        self.__idle = GLib.idle_add(
            self.__idle_emit, songs, priority=GLib.PRIORITY_LOW)

    def __selection_changed_cb(self, selection):
        count = selection.count_selected_rows()
        if self.__count == count == 0:
            return
        if count <= 1:
            if self.__count > 1:
                self.__emit_info_selection()
        else:
            self.__emit_info_selection()
        self.__count = count


def get_columns():
    """Gets the list of songlist column headings"""

    if config.has_option("settings", "columns"):
        return config.getstringlist(
            "settings", "columns", const.DEFAULT_COLUMNS)
    else:
        # migrate old settings
        try:
            columns = config.get("settings", "headers").split()
        except config.Error:
            return const.DEFAULT_COLUMNS
        else:
            config.remove_option("settings", "headers")
            set_columns(columns)
            config.setstringlist("settings", "columns", columns)
            return columns


def set_columns(vals):
    """Persists the settings for songlist headings held in `vals`"""

    config.setstringlist("settings", "columns", vals)


def get_sort_tag(tag):
    """Returns a tag that can be used for sorting for the given column tag.

    Returns '' if the default sort key should be used.
    """

    replace_order = {
        "~#track": "",
        "~#disc": "",
        "~length": "~#length"
    }

    if tag == "~title~version":
        tag = "title"
    elif tag == "~album~discsubtitle":
        tag = "album"

    if tag.startswith("<"):
        for key, value in replace_order.iteritems():
            tag = tag.replace("<%s>" % key, "<%s>" % value)
        tag = Pattern(tag).format
    else:
        tags = util.tagsplit(tag)
        sort_tags = []
        for tag in tags:
            tag = replace_order.get(tag, tag)
            tag = TAG_TO_SORT.get(tag, tag)
            if tag not in sort_tags:
                sort_tags.append(tag)
        if len(sort_tags) > 1:
            tag = "~" + "~".join(sort_tags)

    return tag


class SongListDnDMixin(object):
    """DnD support for the SongList class"""

    def setup_drop(self, library):
        self.connect('drag-motion', self.__drag_motion)
        self.connect('drag-leave', self.__drag_leave)
        self.connect('drag-data-get', self.__drag_data_get)
        self.connect('drag-data-received', self.__drag_data_received, library)

    def enable_drop(self, by_row=True):
        targets = [
            ("text/x-quodlibet-songs", Gtk.TargetFlags.SAME_APP, DND_QL),
            ("text/uri-list", 0, DND_URI_LIST)
        ]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]
        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, targets,
            Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        self.drag_dest_set(Gtk.DestDefaults.ALL, targets,
                           Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        self.__drop_by_row = by_row

    def disable_drop(self):
        targets = [
            ("text/x-quodlibet-songs", Gtk.TargetFlags.SAME_APP, DND_QL),
            ("text/uri-list", 0, DND_URI_LIST)
        ]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]
        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.COPY)
        self.drag_dest_unset()

    def __drag_motion(self, view, ctx, x, y, time):
        if self.__drop_by_row:
            self.set_drag_dest(x, y)
            self.scroll_motion(x, y)
            if Gtk.drag_get_source_widget(ctx) == self:
                kind = Gdk.DragAction.MOVE
            else:
                kind = Gdk.DragAction.COPY
            Gdk.drag_status(ctx, kind, time)
            return True
        else:
            self.get_parent().drag_highlight()
            Gdk.drag_status(ctx, Gdk.DragAction.COPY, time)
            return True

    def __drag_leave(self, widget, ctx, time):
        widget.get_parent().drag_unhighlight()
        self.scroll_disable()

    def __drag_data_get(self, view, ctx, sel, tid, etime):
        model, paths = self.get_selection().get_selected_rows()
        if tid == DND_QL:
            songs = [model[path][0] for path in paths
                     if model[path][0].can_add]
            if len(songs) != len(paths):
                qltk.ErrorMessage(
                    qltk.get_top_parent(self), _("Unable to copy songs"),
                    _("The files selected cannot be copied to other "
                      "song lists or the queue.")).run()
                Gdk.drag_abort(ctx, etime)
                return

            qltk.selection_set_songs(sel, songs)
            if ctx.get_actions() & Gdk.DragAction.MOVE:
                self.__drag_iters = map(model.get_iter, paths)
            else:
                self.__drag_iters = []
        else:
            uris = [model[path][0]("~uri") for path in paths]
            sel.set_uris(uris)
            self.__drag_iters = []

    def __drag_data_received(self, view, ctx, x, y, sel, info, etime, library):
        model = view.get_model()
        if info == DND_QL:
            filenames = qltk.selection_get_filenames(sel)
            move = (Gtk.drag_get_source_widget(ctx) == view)
        elif info == DND_URI_LIST:
            def to_filename(s):
                try:
                    return URI(s).filename
                except ValueError:
                    return None

            filenames = filter(None, map(to_filename, sel.get_uris()))
            move = False
        else:
            Gtk.drag_finish(ctx, False, False, etime)
            return

        to_add = []
        for filename in filenames:
            if filename not in library.librarian:
                library.add_filename(filename)
            elif filename not in library:
                to_add.append(library.librarian[filename])
        library.add(to_add)
        songs = filter(None, map(library.get, filenames))
        if not songs:
            Gtk.drag_finish(ctx, bool(not filenames), False, etime)
            return

        if not self.__drop_by_row:
            success = self.__drag_data_browser_dropped(songs)
            Gtk.drag_finish(ctx, success, False, etime)
            return

        try:
            path, position = view.get_dest_row_at_pos(x, y)
        except TypeError:
            path = max(0, len(model) - 1)
            position = Gtk.TreeViewDropPosition.AFTER

        if move and Gtk.drag_get_source_widget(ctx) == view:
            iter = model.get_iter(path) # model can't be empty, we're moving
            if position in (Gtk.TreeViewDropPosition.BEFORE,
                            Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                while self.__drag_iters:
                    model.move_before(self.__drag_iters.pop(0), iter)
            else:
                while self.__drag_iters:
                    model.move_after(self.__drag_iters.pop(), iter)
            Gtk.drag_finish(ctx, True, False, etime)
        else:
            song = songs.pop(0)
            try:
                iter = model.get_iter(path)
            except ValueError:
                iter = model.append(row=[song]) # empty model
            else:
                if position in (Gtk.TreeViewDropPosition.BEFORE,
                                Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                    iter = model.insert_before(iter, [song])
                else:
                    iter = model.insert_after(iter, [song])
            for song in songs:
                iter = model.insert_after(iter, [song])
            Gtk.drag_finish(ctx, True, move, etime)

    def __drag_data_browser_dropped(self, songs):
        window = qltk.get_top_parent(self)
        if callable(window.browser.dropped):
            return window.browser.dropped(self, songs)
        else:
            return False


class SongList(AllTreeView, SongListDnDMixin, DragScroll,
               util.InstanceTracker):
    # A TreeView containing a list of songs.

    __gsignals__ = {
        # changed(songs:list)
        'orders-changed': (GObject.SignalFlags.RUN_LAST, None, [])
    }

    headers = [] # The list of current headers.
    star = list(Query.STAR)
    sortable = True

    def Menu(self, header, browser, library):
        songs = self.get_selected_songs()
        if not songs:
            return

        can_filter = browser.can_filter

        menu = browser.Menu(songs, self, library)

        def Filter(t):
            # Translators: The substituted string is the name of the
            # selected column (a translated tag name).
            b = qltk.MenuItem(
                _("_Filter on %s") % util.tag(t, True), Gtk.STOCK_INDEX)
            b.connect_object('activate', self.__filter_on, t, songs, browser)
            return b

        header = util.tagsplit(header)[0]

        if can_filter("artist") or can_filter("album") or can_filter(header):
            menu.preseparate()

        if can_filter("artist"):
            menu.prepend(Filter("artist"))
        if can_filter("album"):
            menu.prepend(Filter("album"))
        if (header not in ["artist", "album"] and can_filter(header)):
            menu.prepend(Filter(header))

        ratings = RatingsMenuItem(songs, library)
        menu.preseparate()
        menu.prepend(ratings)
        menu.show_all()
        return menu

    def __init__(self, library, player=None, update=False):
        super(SongList, self).__init__()
        self._register_instance(SongList)
        self.set_model(PlaylistModel())
        self.info = SongInfoSelection(self)
        self.set_size_request(200, 150)
        self.set_rules_hint(True)
        self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.set_fixed_height_mode(True)
        self.__csig = self.connect('columns-changed', self.__columns_changed)
        self._first_column = None
        # A priority list of how to apply the sort keys.
        # might contain column header names not present...
        self._sort_sequence = []
        self.set_column_headers(self.headers)
        librarian = library.librarian or library
        sigs = []
        # The player needs to be called first so it can ge the next song
        # in case the current one gets deleted and the order gets reset.
        if player:
            s = librarian.connect_object('removed', map, player.remove)
            sigs.append(s)
        sigs.extend([librarian.connect('changed', self.__song_updated),
                librarian.connect('removed', self.__song_removed)])
        if update:
            sigs.append(librarian.connect('added', self.__song_added))
        for sig in sigs:
            self.connect_object('destroy', librarian.disconnect, sig)
        if player:
            sigs = [
                player.connect('paused', lambda *x: self.__redraw_current()),
                player.connect('unpaused', lambda *x: self.__redraw_current()),
                player.connect('error', lambda *x: self.__redraw_current()),
            ]
            for sig in sigs:
                self.connect_object('destroy', player.disconnect, sig)

        self.connect('button-press-event', self.__button_press, librarian)
        self.connect('key-press-event', self.__key_press, librarian)

        self.setup_drop(library)
        self.disable_drop()

        self.set_search_equal_func(self.__search_func, None)

        self.connect('destroy', self.__destroy)

    @property
    def model(self):
        return self.get_model()

    def toggle_column_sort(self, column, replace=True, refresh=True):
        """Toggles the sort order of a column.

        If not sorted, defaults to Gtk.SortType.ASCENDING

        If replace is False, the column will be appended to existing
        sorted columns. If it replaces a sort sequence where it was part of
        before it will not toggle itself, only remove the other ones.

        If refresh is True, the song list will be resorted.
        """

        if not self.sortable:
            return

        # update the sort priority list
        if replace:
            del self._sort_sequence[:]
        else:
            try:
                self._sort_sequence.remove(column.header_name)
            except ValueError:
                pass
        self._sort_sequence.append(column.header_name)

        # in case we replace a multi sort with one sort that was part before
        # don't toggle, because it usually means we want to get rid of
        # the other one
        dont_reverse = False
        if replace and column.get_sort_indicator():
            for c in self.get_columns():
                if c is not column and c.get_sort_indicator():
                    dont_reverse = True
                    break

        # set the inidicators
        default_order = Gtk.SortType.ASCENDING
        reversed_ = False
        for c in self.get_columns():
            if c is column:
                if c.get_sort_indicator():
                    if dont_reverse:
                        order = c.get_sort_order()
                    else:
                        order = not c.get_sort_order()
                        reversed_ = True
                else:
                    order = default_order
                c.set_sort_order(order)
                c.set_sort_indicator(True)
                if not replace:
                    break
            elif replace:
                c.set_sort_indicator(False)

        if refresh:
            songs = self.get_songs()
            if reversed_:
                # python sort is faster if presorted
                songs.reverse()
            self.set_songs(songs)

        self.emit("orders-changed")

    def find_default_sort_column(self):
        """Returns a column that will sort using only the default sort key
        or None if none can't be found
        """

        for c in self.get_columns():
            # get_sort_tag == "" if the default sort key should be used
            if not get_sort_tag(c.header_name):
                return c

    def is_sorted(self):
        """If any of the columns has a sort indicator.

        This does not mean that the list content is sorted.
        """

        for c in self.get_columns():
            if c.get_sort_indicator():
                return True
        return False

    def clear_sort(self):
        """Remove all column sort indicators"""

        for h in self.get_columns():
            h.set_sort_indicator(False)
        del self._sort_sequence[:]

        self.emit("orders-changed")

    def get_sort_orders(self):
        """Returns a list of tuples (header_name, descending)"""

        sorted_ = [c for c in self.get_columns() if c.get_sort_indicator()]

        # if someone adds columns and sorts them using the TV API directly..
        # better not crash I guess
        for c in sorted_:
            if c.header_name not in self._sort_sequence:
                self._sort_sequence.append(c.header_name)

        sorted_.sort(key=lambda c: self._sort_sequence.index(c.header_name))
        return [(c.header_name, bool(c.get_sort_order())) for c in sorted_]

    def set_sort_orders(self, orders):
        """Pass a value returned by get_sort_orders() to restore the state"""

        if not self.sortable:
            return

        self._sort_sequence = [tag for tag, o in orders]

        orders = dict(orders)
        for c in self.get_columns():
            if c.header_name in orders:
                c.set_sort_indicator(True)
                c.set_sort_order(orders[c.header_name])
            else:
                c.set_sort_indicator(False)

        self.emit("orders-changed")

    def __destroy(self, *args):
        self.info.destroy()
        self.handler_block(self.__csig)
        for column in self.get_columns():
            self.remove_column(column)
        self.handler_unblock(self.__csig)

    def __search_func(self, model, column, key, iter, *args):
        for column in self.get_columns():
            value = model.get_value(iter)(column.header_name)
            if not isinstance(value, basestring):
                continue
            elif key in value.lower() or key in value:
                return False
        else:
            return True

    def __filter_on(self, header, songs, browser):
        if not browser:
            return

        # Fall back to the playing song
        if songs is None:
            if app.player.song:
                songs = [app.player.song]
            else:
                return

        browser.filter_on(songs, header)

    def __button_press(self, view, event, librarian):
        if event.button != Gdk.BUTTON_PRIMARY:
            return
        x, y = map(int, [event.x, event.y])
        try:
            path, col, cellx, celly = view.get_path_at_pos(x, y)
        except TypeError:
            return True
        if event.window != self.get_bin_window():
            return False
        if col.header_name == "~rating":
            if not config.getboolean("browsers", "rating_click"):
                return

            song = view.get_model()[path][0]
            l = Gtk.Label()
            l.show()
            l.set_text(config.RATINGS.full_symbol)
            width = l.get_preferred_size()[1].width
            l.destroy()
            if not width:
                return False
            precision = config.RATINGS.precision
            count = int(float(cellx - 5) / width) + 1
            rating = max(0.0, min(1.0, count * precision))
            if (rating <= precision and
                    song("~#rating") == precision):
                rating = 0.0
            self.__set_rating(rating, [song], librarian)

    def __set_rating(self, value, songs, librarian):
        count = len(songs)
        if (count > 1 and
                config.getboolean("browsers", "rating_confirm_multiple")):
            dialog = ConfirmRateMultipleDialog(self, count, value)
            if dialog.run() != Gtk.ResponseType.YES:
                return
        for song in songs:
            song["~#rating"] = value
        librarian.changed(songs)

    def __key_press(self, songlist, event, librarian):
        rating_accels = [
            "<ctrl>%d" % i for i in range(min(10, config.RATINGS.number + 1))]

        if qltk.is_accel(event, *rating_accels):
            rating = int(chr(event.keyval)) * config.RATINGS.precision
            self.__set_rating(rating, self.get_selected_songs(), librarian)
            return True
        elif qltk.is_accel(event, "<ctrl>Return", "<ctrl>KP_Enter"):
            self.__enqueue(self.get_selected_songs())
            return True
        elif qltk.is_accel(event, "<control>F"):
            self.emit('start-interactive-search')
            return True
        elif qltk.is_accel(event, "<alt>Return"):
            songs = self.get_selected_songs()
            if songs:
                window = SongProperties(librarian, songs, parent=self)
                window.show()
            return True
        elif qltk.is_accel(event, "<control>I"):
            songs = self.get_selected_songs()
            if songs:
                window = Information(librarian, songs, self)
                window.show()
            return True
        return False

    def __enqueue(self, songs):
        songs = filter(lambda s: s.can_add, songs)
        if songs:
            from quodlibet import app
            app.window.playlist.enqueue(songs)

    def __redraw_current(self):
        model = self.get_model()
        iter_ = model.current_iter
        if iter_:
            path = model.get_path(iter_)
            model.row_changed(path, iter_)

    def __columns_changed(self, *args):
        headers = map(lambda h: h.header_name, self.get_columns())
        SongList.set_all_column_headers(headers)
        SongList.headers = headers

    def __column_width_changed(self, *args):
        # make sure non resizable columns stay non expanding.
        # gtk likes to change them sometimes
        for c in self.get_columns():
            if not c.get_resizable() and c.get_expand():
                c.set_expand(False)

        widths = []
        expands = []
        for c in self.get_columns():
            if not c.get_resizable():
                continue
            widths.extend((c.header_name, str(c.get_fixed_width())))
            expands.extend((c.header_name, str(int(c.get_expand()))))
        config.setstringlist("memory", "column_widths", widths)
        config.setstringlist("memory", "column_expands", expands)

    @classmethod
    def set_all_column_headers(cls, headers):
        set_columns(headers)
        try:
            headers.remove("~current")
        except ValueError:
            pass
        cls.headers = headers
        for listview in cls.instances():
            listview.set_column_headers(headers)

        star = list(Query.STAR)
        for header in headers:
            if "<" in header:
                try:
                    tags = Pattern(header).tags
                except ValueError:
                    continue
            else:
                tags = util.tagsplit(header)
            for tag in tags:
                if not tag.startswith("~#") and tag not in star:
                    star.append(tag)
        SongList.star = star

    def set_model(self, model):
        super(SongList, self).set_model(model)
        self.set_search_column(0)

    def get_songs(self):
        """Get all songs currently in the song list"""

        model = self.get_model()
        if not model:
            return []
        return model.get()

    def _sort_songs(self, songs):
        """Sort passed songs in place based on the column sort orders"""

        last_tag = None
        last_order = None
        first = True
        for tag, reverse in self.get_sort_orders():
            tag = get_sort_tag(tag)

            # always sort using the default sort key first
            if first:
                first = False
                songs.sort(key=lambda s: s.sort_key, reverse=reverse)
                last_order = reverse
                last_tag = ""

            # no need to sort twice in a row with the same key/order
            if tag == last_tag and last_order == reverse:
                continue
            last_order = reverse
            last_tag = tag

            if tag == "":
                songs.sort(key=lambda s: s.sort_key, reverse=reverse)
            else:
                sort_func = AudioFile.sort_by_func(tag)
                songs.sort(key=sort_func, reverse=reverse)

    def add_songs(self, songs):
        """Add songs to the list in the right order and position"""

        if not songs:
            return

        model = self.get_model()
        if not len(model):
            self.set_songs(songs)
            return

        if not self.is_sorted():
            model.append_many(songs)
            return

        # FIXME: Replace with something fast
        old_songs = self.get_songs()
        old_songs.extend(songs)

        self._sort_songs(old_songs)

        for index, song in sorted(zip(map(old_songs.index, songs), songs)):
            model.insert(index, row=[song])

    def set_songs(self, songs, sorted=False):
        """Fill the song list.

        If sorted is True, the passed songs will not be sorted and
        all sort indicators will be removed.
        """

        model = self.get_model()

        if not sorted:
            # make sure some sorting is set and visible
            if not self.is_sorted():
                default = self.find_default_sort_column()
                if default:
                    self.toggle_column_sort(default, refresh=False)
            self._sort_songs(songs)
        else:
            self.clear_sort()

        with self.without_model() as model:
            model.set(songs)

        # the song selection has queued a change now, cancel that and
        # pass the songs manually
        self.info._update_songs(songs)

    def jump_to_song(self, song, select=False):
        """Scrolls to and selects the given song if in the list.

        Returns True if the song was found.
        """

        model = self.get_model()
        if not model:
            return False

        # fast path
        if song == model.current:
            path = model.current_path
        else:
            iter_ = model.find(song)
            if iter_ is None:
                return False
            path = model.get_path(iter_)

        self.scroll_to_cell(path, use_align=True, row_align=0.5)
        if select:
            self.set_cursor(path)

        return True

    def get_selected_songs(self):
        """Returns a list of selected songs"""

        songs = []

        def func(model, path, iter_, user_data):
            songs.append(model.get_value(iter_))
        selection = self.get_selection()
        selection.selected_foreach(func, None)
        return songs

    def __song_updated(self, librarian, songs):
        """Only update rows that are currently displayed.
        Warning: This makes the row-changed signal useless.
        """

        vrange = self.get_visible_range()
        if vrange is None:
            return
        (start,), (end,) = vrange
        model = self.get_model()
        for path in xrange(start, end + 1):
            row = model[path]
            if row[0] in songs:
                model.row_changed(row.path, row.iter)

    def __song_added(self, librarian, songs):
        window = qltk.get_top_parent(self)
        filter_ = window.browser.active_filter
        if callable(filter_):
            self.add_songs(filter(filter_, songs))

    def __song_removed(self, librarian, songs):
        # The selected songs are removed from the library and should
        # be removed from the view.

        if not len(self.get_model()):
            return

        songs = set(songs)

        # search in the selection first
        # speeds up common case: select songs and remove them
        model, rows = self.get_selection().get_selected_rows()
        rows = rows or []
        iters = [model[r].iter for r in rows if model[r][0] in songs]

        # if not all songs were in the selection, search the whole view
        if len(iters) != len(songs):
            iters = model.find_all(songs)

        self.remove_iters(iters)

    def __song_properties(self, librarian):
        model, rows = self.get_selection().get_selected_rows()
        if rows:
            songs = [model[row][0] for row in rows]
        else:
            from quodlibet import app
            if app.player.song:
                songs = [app.player.song]
            else:
                return
        window = SongProperties(librarian, songs, parent=self)
        window.show()

    def __information(self, librarian):
        model, rows = self.get_selection().get_selected_rows()
        if rows:
            songs = [model[row][0] for row in rows]
        else:
            from quodlibet import app
            if app.player.song:
                songs = [app.player.song]
            else:
                return
        window = Information(librarian, songs, self)
        window.show()

    def set_first_column_type(self, column_type):
        """Set a column that will be included at the beginning"""

        self._first_column = column_type

        # refresh
        self.set_column_headers(self.headers)

    # Build a new filter around our list model, set the headers to their
    # new values.
    def set_column_headers(self, headers):
        if len(headers) == 0:
            return

        self.handler_block(self.__csig)

        old_sort = self.get_sort_orders()
        for column in self.get_columns():
            self.remove_column(column)

        if self._first_column:
            column = self._first_column()
            self.append_column(column)

        cws = config.getstringlist("memory", "column_widths")
        column_widths = {}
        for i in range(0, len(cws), 2):
            column_widths[cws[i]] = int(cws[i + 1])

        ce = config.getstringlist("memory", "column_expands")
        column_expands = {}
        for i in range(0, len(ce), 2):
            column_expands[ce[i]] = int(ce[i + 1])

        for t in headers:
            column = create_songlist_column(t)
            if column.get_resizable():
                if t in column_widths:
                    column.set_fixed_width(column_widths[t])
                if t in column_expands:
                    column.set_expand(column_expands[t])
                else:
                    column.set_expand(True)

            def column_clicked(column, *args):
                # if ctrl is held during the sort click, append a sort key
                # or change order if already sorted
                ctrl_held = False
                event = Gtk.get_current_event()
                if event:
                    ok, state = event.get_state()
                    if ok and state & Gdk.ModifierType.CONTROL_MASK:
                        ctrl_held = True

                self.toggle_column_sort(column, replace=not ctrl_held)

            column.connect('clicked', column_clicked)
            column.connect('button-press-event', self.__showmenu)
            column.connect('popup-menu', self.__showmenu)
            column.connect('notify::width', self.__column_width_changed)
            column.set_reorderable(True)
            self.append_column(column)

        self.columns_autosize()
        self.set_sort_orders(old_sort)

        self.handler_unblock(self.__csig)

    def __getmenu(self, column):
        menu = Gtk.Menu()
        menu.connect_object('selection-done', Gtk.Menu.destroy, menu)

        current = SongList.headers[:]
        current_set = set(current)

        def tag_title(tag):
            if tag.startswith("<"):
                return util.pattern(tag)
            return util.tag(tag)
        current = zip(map(tag_title, current), current)

        def add_header_toggle(menu, (header, tag), active, column=column):
            item = Gtk.CheckMenuItem(label=header)
            item.tag = tag
            item.set_active(active)
            item.connect('activate', self.__toggle_header_item, column)
            item.show()
            item.set_tooltip_text(tag)
            menu.append(item)

        for header in current:
            add_header_toggle(menu, header, True)

        sep = SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        trackinfo = """title genre ~title~version ~#track
            ~#playcount ~#skipcount ~rating ~#length""".split()
        peopleinfo = """artist ~people performer arranger author composer
            conductor lyricist originalartist""".split()
        albuminfo = """album ~album~discsubtitle labelid ~#disc ~#discs
            ~#tracks albumartist""".split()
        dateinfo = """date originaldate recordingdate ~#laststarted
            ~#lastplayed ~#added ~#mtime""".split()
        fileinfo = """~format ~#bitrate ~#filesize ~filename ~basename ~dirname
            ~uri""".split()
        copyinfo = """copyright organization location isrc
            contact website""".split()
        all_headers = reduce(lambda x, y: x + y,
            [trackinfo, peopleinfo, albuminfo, dateinfo, fileinfo, copyinfo])

        for name, group in [
            (_("All _Headers"), all_headers),
            (_("_Track Headers"), trackinfo),
            (_("_Album Headers"), albuminfo),
            (_("_People Headers"), peopleinfo),
            (_("_Date Headers"), dateinfo),
            (_("_File Headers"), fileinfo),
            (_("_Production Headers"), copyinfo),
        ]:
            item = Gtk.MenuItem(label=name, use_underline=True)
            item.show()
            menu.append(item)
            submenu = Gtk.Menu()
            item.set_submenu(submenu)
            for header in sorted(zip(map(util.tag, group), group)):
                add_header_toggle(submenu, header, header[1] in current_set)

        sep = SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        custom = Gtk.MenuItem(
            label=_("_Customize Headers..."), use_underline=True)
        custom.show()
        custom.connect('activate', self.__add_custom_column)
        menu.append(custom)

        item = Gtk.CheckMenuItem(label=_("_Expand"), use_underline=True)
        item.set_active(column.get_expand())
        item.set_sensitive(column.get_resizable())

        def set_expand_cb(item, column):
            do_expand = item.get_active()
            if not do_expand:
                # in case we unexpand, get the current width and set it
                # so the column doesn't give up all its space
                # to the left over expanded columns
                column.set_fixed_width(column.get_width())
            else:
                # in case we expand this seems to trigger a re-distribution
                # between all expanded columns
                column.set_fixed_width(-1)
            column.set_expand(do_expand)
            self.columns_autosize()

        sep = SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        item.connect('activate', set_expand_cb, column)
        item.show()
        menu.append(item)

        return menu

    def __toggle_header_item(self, item, column):
        headers = SongList.headers[:]
        if item.get_active():
            try:
                headers.insert(self.get_columns().index(column), item.tag)
            except ValueError:
                headers.append(item.tag)
        else:
            try:
                headers.remove(item.tag)
            except ValueError:
                pass

        SongList.set_all_column_headers(headers)
        SongList.headers = headers

    def __add_custom_column(self, item):
        # Prefs has to import SongList, so do this here to avoid
        # a circular import.
        from quodlibet.qltk.prefs import PreferencesWindow
        window = PreferencesWindow(self)
        window.show()
        window.set_page("songlist")

    def __showmenu(self, column, event=None):
        time = event.time if event else Gtk.get_current_event_time()

        if event is not None and event.button != Gdk.BUTTON_SECONDARY:
            return False

        if event:
            self.__getmenu(column).popup(None, None, None, None,
                                         event.button, time)
            return True

        widget = column.get_widget()
        return qltk.popup_menu_under_widget(self.__getmenu(column),
                widget, 3, time)


@config.register_upgrade_function
def _migrate_rating_column(config, old, new):
    if old < 0:
        # https://code.google.com/p/quodlibet/issues/detail?id=1381
        columns = get_columns()[:]
        for i, c in enumerate(columns):
            if c == "~#rating":
                columns[i] = "~rating"
        set_columns(columns)
