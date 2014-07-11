# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#           2012 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

from gi.repository import Gtk, GObject, Gdk, GLib, Gio

import quodlibet

from quodlibet import browsers
from quodlibet import config
from quodlibet import const
from quodlibet import formats
from quodlibet import qltk
from quodlibet import util
from quodlibet import app

from quodlibet.formats.remote import RemoteFile
from quodlibet.qltk.browser import LibraryBrowser
from quodlibet.qltk.chooser import FolderChooser, FileChooser
from quodlibet.qltk.controls import PlayControls
from quodlibet.qltk.cover import CoverImage
from quodlibet.qltk.getstring import GetStringDialog
from quodlibet.qltk.bookmarks import EditBookmarks
from quodlibet.qltk.info import SongInfo
from quodlibet.qltk.information import Information
from quodlibet.qltk.logging import LoggingWindow
from quodlibet.qltk.msg import ErrorMessage
from quodlibet.qltk.notif import StatusBar, TaskController
from quodlibet.qltk.playorder import PlayOrder
from quodlibet.qltk.pluginwin import PluginWindow
from quodlibet.qltk.properties import SongProperties
from quodlibet.qltk.prefs import PreferencesWindow
from quodlibet.qltk.queue import QueueExpander
from quodlibet.qltk.songlist import SongList
from quodlibet.qltk.songmodel import PlaylistMux
from quodlibet.qltk.x import RPaned, ConfigRVPaned, Alignment, ScrolledWindow
from quodlibet.qltk.x import SymbolicIconImage
from quodlibet.qltk.about import AboutQuodLibet
from quodlibet.util import copool, gobject_weak
from quodlibet.util.library import get_scan_dirs, set_scan_dirs
from quodlibet.util.uri import URI
from quodlibet.util.library import background_filter, scan_library
from quodlibet.qltk.window import PersistentWindowMixin
from quodlibet.qltk.songlistcolumns import SongListColumn


class CurrentColumn(SongListColumn):
    """Displays the current song indicator, either a play or pause icon."""

    def __init__(self):
        super(CurrentColumn, self).__init__("~current")
        self._render = Gtk.CellRendererPixbuf(follow_state=True)
        self.pack_start(self._render, True)
        self._render.set_property('xalign', 0.5)

        self.set_fixed_width(24)
        self.set_expand(False)
        self.set_cell_data_func(self._render, self._cdf)

    def _format_title(self, tag):
        return u""

    def _cdf(self, column, cell, model, iter_, user_data):
        PLAY = "media-playback-start"
        PAUSE = "media-playback-pause"
        STOP = "media-playback-stop"
        ERROR = "dialog-error"

        row = model[iter_]

        if row.path == model.current_path:
            player = app.player
            if player.error:
                name = ERROR
            elif model.sourced:
                name = [PLAY, PAUSE][player.paused]
            else:
                name = STOP
        else:
            name = None

        if not self._needs_update(name):
            return

        if name is not None:
            gicon = Gio.ThemedIcon.new_from_names(
                [name + "-symbolic", name])
        else:
            gicon = None

        cell.set_property('gicon', gicon)


class MainSongList(SongList):
    # The SongList that represents the current playlist.

    _activated = False

    def __init__(self, library, player):
        super(MainSongList, self).__init__(library, player, update=True)
        self.set_first_column_type(CurrentColumn)

        self.connect_object('row-activated', self.__select_song, player)

        # ugly.. so the main window knows if the next song-started
        # comes from an row-activated or anything else.
        def reset_activated(*args):
            self._activated = False
        s = player.connect_after('song-started', reset_activated)
        self.connect_object('destroy', player.disconnect, s)

        self.connect("orders-changed", self.__orders_changed)

    def __orders_changed(self, *args):
        l = []
        for tag, reverse in self.get_sort_orders():
            l.append("%d%s" % (int(reverse), tag))
        config.setstringlist('memory', 'sortby', l)

    def __select_song(self, player, indices, col):
        self._activated = True
        iter = self.model.get_iter(indices)
        if player.go_to(iter, True):
            player.paused = False


class SongListScroller(ScrolledWindow):
    def __init__(self, menu):
        super(SongListScroller, self).__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.set_shadow_type(Gtk.ShadowType.IN)
        self.connect_object('notify::visible', self.__visibility, menu)

    def __visibility(self, menu, event):
        value = self.get_property('visible')
        menu.set_active(value)
        config.set("memory", "songlist", str(value))


class TopBar(Gtk.Toolbar):
    def __init__(self, parent, player, library):
        super(TopBar, self).__init__()

        # play controls
        control_item = Gtk.ToolItem()
        self.insert(control_item, 0)
        t = PlayControls(player, library.librarian)
        self.volume = t.volume
        control_item.add(t)

        self.insert(Gtk.SeparatorToolItem(), 1)

        info_item = Gtk.ToolItem()
        self.insert(info_item, 2)
        info_item.set_expand(True)

        box = Gtk.Box(spacing=6)
        info_item.add(Alignment(box, border=3, right=-3))

        # song text
        text = SongInfo(library.librarian, player)
        box.pack_start(Alignment(text, top=3, bottom=3), True, True, 0)

        # cover image
        self.image = CoverImage(resize=True)
        gobject_weak(player.connect, 'song-started', self.__new_song,
                     parent=self)
        gobject_weak(parent.connect, 'artwork-changed',
                     self.__song_art_changed, library, parent=self)
        box.pack_start(self.image, False, True, 0)

        for child in self.get_children():
            child.show_all()

        context = self.get_style_context()
        context.add_class("primary-toolbar")

    def __new_song(self, player, song):
        self.image.set_song(song)

    def __song_art_changed(self, player, songs, library):
        self.image.refresh()
        refresh_albums = []
        for song in songs:
            # Album browser only (currently):
            album = library.albums.get(song.album_key, None)
            if album:
                album.scan_cover(force=True)
                refresh_albums.append(album)
        if refresh_albums:
            library.albums.refresh(refresh_albums)


class ReapeatButton(Gtk.ToggleButton):

    def __init__(self):
        super(ReapeatButton, self).__init__(
            image=SymbolicIconImage(
                "media-playlist-repeat", Gtk.IconSize.SMALL_TOOLBAR))

        self.set_name("ql-repeat-button")
        qltk.add_css(self, """
            #ql-repeat-button {
                padding: 0px;
            }
        """)
        self.set_size_request(26, 26)

        self.set_tooltip_text(_("Restart the playlist when finished"))

        self.bind_config("settings", "repeat")

    def bind_config(self, section, option):
        self.set_active(config.getboolean(section, option))

        def toggled_cb(*args):
            config.set(section, option, self.get_active())

        self.connect('toggled', toggled_cb)


class StatusBarBox(Gtk.HBox):

    def __init__(self, model, player):
        super(StatusBarBox, self).__init__(spacing=6)

        self.order = order = PlayOrder(model, player)
        self.pack_start(order, False, True, 0)

        self.repeat = repeat = ReapeatButton()
        self.pack_start(repeat, False, True, 0)
        repeat.connect('toggled', self.__repeat, model)
        model.repeat = repeat.get_active()

        self.statusbar = StatusBar(TaskController.default_instance)
        self.pack_start(self.statusbar, True, True, 0)

    def __repeat(self, button, model):
        model.repeat = button.get_active()


class AppMenu(object):
    """Implements a app menu proxy mirroring some main menu items
    to a new menu and exporting it on the session bus.

    Activation gets proxied back to the main menu actions.
    """

    def __init__(self, window, action_group):
        window.realize()

        self._bus = None
        self._ag_id = None
        self._am_id = None
        window.connect("destroy", self._unexport)

        if window.get_realized():
            self._export(window, action_group)
        else:
            self._id = window.connect("realize", self._realized, action_group)

    def _realized(self, window, ag):
        window.disconnect(self._id)
        self._export(window, ag)

    def _export(self, window, gtk_group):
        actions = [
            ["Preferences", "Plugins"],
            ["RefreshLibrary"],
            ["OnlineHelp", "About", "Quit"],
        ]

        # build the new menu
        menu = Gio.Menu()
        action_names = []
        for group in actions:
            section = Gio.Menu()
            for name in group:
                action = gtk_group.get_action(name)
                assert action
                label = action.get_label()
                section.append(label, "app." + name)
                action_names.append(name)
            menu.append_section(None, section)
        menu.freeze()

        # proxy activate to the old group
        def callback(action, data):
            name = action.get_name()
            gtk_action = gtk_group.get_action(name)
            gtk_action.activate()

        action_group = Gio.SimpleActionGroup()
        for name in action_names:
            action = Gio.SimpleAction.new(name, None)
            action_group.insert(action)
            action.connect("activate", callback)

        # export on the bus
        ag_object_path = "/net/sacredchao/QuodLibet"
        am_object_path = "/net/sacredchao/QuodLibet/menus/appmenu"
        app_id = "net.sacredchao.QuodLibet"

        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._ag_id = bus.export_action_group(ag_object_path, action_group)
            self._am_id = bus.export_menu_model(am_object_path, menu)
        except GLib.GError as e:
            print_d("Registering appmenu failed: %r" % e)
            return

        self._bus = bus

        win = window.get_window()
        if not hasattr(win, "set_utf8_property"):
            # not a GdkX11.X11Window
            print_d("Registering appmenu failed: X11 only")
            return

        win.set_utf8_property("_GTK_UNIQUE_BUS_NAME", bus.get_unique_name())
        win.set_utf8_property("_GTK_APPLICATION_ID", app_id)
        win.set_utf8_property("_GTK_APPLICATION_OBJECT_PATH", ag_object_path)
        win.set_utf8_property("_GTK_APP_MENU_OBJECT_PATH", am_object_path)

    def _unexport(self, window):
        if self._bus:
            self._bus.unexport_action_group(self._ag_id)
            self._bus.unexport_menu_model(self._am_id)
            self._bus = None


class PlaybackErrorDialog(ErrorMessage):

    def __init__(self, parent, player_error):
        add_full_stop = lambda s: s and (s.rstrip(".") + ".")
        description = add_full_stop(util.escape(player_error.short_desc))
        details = add_full_stop(util.escape(player_error.long_desc or ""))
        if details:
            description += " " + details

        super(PlaybackErrorDialog, self).__init__(
            parent, _("Playback Error"), description)


DND_URI_LIST, = range(1)


class QuodLibetWindow(Gtk.Window, PersistentWindowMixin):
    SIG_PYOBJECT = (GObject.SignalFlags.RUN_LAST, None, (object,))
    __gsignals__ = {
        'artwork-changed': SIG_PYOBJECT,
    }

    def __init__(self, library, player, headless=False):
        super(QuodLibetWindow, self).__init__()
        self.last_dir = const.HOME

        self.__update_title(player)
        self.set_default_size(550, 450)

        main_box = Gtk.VBox()
        self.add(main_box)

        # create main menubar, load/restore accelerator groups
        self.__library = library
        ui = self.__create_menu(player, library)
        accel_group = ui.get_accel_group()
        self.add_accel_group(accel_group)

        # dbus app menu
        AppMenu(self, ui.get_action_groups()[0])

        accel_fn = os.path.join(const.USERDIR, "accels")
        Gtk.AccelMap.load(accel_fn)

        def accel_save_cb(*args):
            Gtk.AccelMap.save(accel_fn)
        accel_group.connect_object('accel-changed', accel_save_cb, None)
        main_box.pack_start(ui.get_widget("/Menu"), False, True, 0)

        # get the playlist up before other stuff
        self.songlist = MainSongList(library, player)
        self.songlist.show_all()
        self.songlist.connect_after(
            'drag-data-received', self.__songlist_drag_data_recv)
        self.song_scroller = SongListScroller(
            ui.get_widget("/Menu/View/SongList"))
        self.song_scroller.add(self.songlist)
        self.qexpander = QueueExpander(
            ui.get_widget("/Menu/View/Queue"), library, player)
        self.playlist = PlaylistMux(
            player, self.qexpander.model, self.songlist.model)

        top_bar = TopBar(self, player, library)
        main_box.pack_start(top_bar, False, True, 0)
        self.top_bar = top_bar

        self.__browserbox = Alignment(bottom=3)
        main_box.pack_start(self.__browserbox, True, True, 0)

        statusbox = StatusBarBox(self.songlist.model, player)
        self.order = statusbox.order
        self.repeat = statusbox.repeat
        self.statusbar = statusbox.statusbar

        main_box.pack_start(
            Alignment(statusbox, border=3, top=-3, right=6),
            False, True, 0)

        self.songpane = ConfigRVPaned("memory", "queue_position", 0.75)
        self.songpane.pack1(self.song_scroller, resize=True, shrink=False)
        self.songpane.pack2(self.qexpander, resize=True, shrink=False)
        self.__handle_position = self.songpane.get_property("position")

        def songpane_button_press_cb(pane, event):
            """If we start to drag the pane handle while the
            queue expander is unexpanded, expand it and move the handle
            to the bottom, so we can 'drag' the queue out
            """

            if event.window != pane.get_handle_window():
                return False

            if not self.qexpander.get_expanded():
                self.qexpander.set_expanded(True)
                pane.set_relative(1.0)
            return False

        self.songpane.connect("button-press-event", songpane_button_press_cb)

        self.song_scroller.connect('notify::visible', self.__show_or)
        self.qexpander.connect('notify::visible', self.__show_or)
        self.qexpander.connect('notify::expanded', self.__expand_or)
        self.qexpander.connect('draw', self.__qex_size_allocate)
        self.songpane.connect('notify', self.__moved_pane_handle)

        try:
            orders = []
            for e in config.getstringlist('memory', 'sortby', []):
                orders.append((e[1:], int(e[0])))
        except ValueError:
            pass
        else:
            self.songlist.set_sort_orders(orders)

        self.browser = None
        self.ui = ui

        main_box.show_all()

        try:
            self.select_browser(
                self, config.get("memory", "browser"), library, player, True)
        except:
            config.set("memory", "browser", browsers.name(0))
            config.save(const.CONFIG)
            raise

        # set at least the playlist before the mainloop starts..
        player.setup(self.playlist, None, 0)

        def delayed_song_set():
            self.__delayed_setup = None
            song = library.get(config.get("memory", "song"))
            seek_pos = config.getint("memory", "seek", 0)
            config.set("memory", "seek", 0)
            player.setup(self.playlist, song, seek_pos)
        self.__delayed_setup = GLib.idle_add(delayed_song_set)
        self.showhide_playlist(ui.get_widget("/Menu/View/SongList"))
        self.showhide_playqueue(ui.get_widget("/Menu/View/Queue"))

        self.songlist.connect('popup-menu', self.__songs_popup_menu)
        self.songlist.connect('columns-changed', self.__cols_changed)
        self.songlist.connect('columns-changed', self.__hide_headers)
        self.songlist.info.connect("changed", self.__set_time)

        lib = library.librarian
        gobject_weak(lib.connect_object, 'changed', self.__song_changed,
                     player, parent=self)

        self._playback_error_dialog = None
        player_sigs = [
            ('song-started', self.__song_started),
            ('paused', self.__update_paused, True),
            ('unpaused', self.__update_paused, False),
        ]
        for sig in player_sigs:
            gobject_weak(player.connect, *sig, **{"parent": self})

        # make sure we redraw all error indicators before opening
        # a dialog (blocking the main loop), so connect after default handlers
        gobject_weak(player.connect_after, 'error',
                     self.__player_error, **{"parent": self})

        # connect after to let SongTracker update stats
        player_sigs.append(
            gobject_weak(player.connect_after, "song-ended",
                         self.__song_ended, parent=self))

        targets = [("text/uri-list", Gtk.TargetFlags.OTHER_APP, DND_URI_LIST)]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        self.drag_dest_set(
            Gtk.DestDefaults.ALL, targets, Gdk.DragAction.COPY)
        self.connect('drag-data-received', self.__drag_data_received)

        if not headless:
            GLib.idle_add(self.__configure_scan_dirs, library)

        print_d("Checking library startup configuration...")
        if config.getboolean('library', 'refresh_on_start'):
            # Calls library's scan, which will set up watching if required
            self.__rebuild(None, False)
        elif config.getboolean('library', 'auto_update'):
            self.__library.start_watching()

        self.connect_object("key-press-event", self.__key_pressed, player)

        self.connect("delete-event", self.__save_browser)
        self.connect("destroy", self.__destroy)

        self.enable_window_tracking("quodlibet")

    def __player_error(self, player, song, player_error):
        # it's modal, but mmkeys etc. can still trigger new ones
        if self._playback_error_dialog:
            self._playback_error_dialog.destroy()
        dialog = PlaybackErrorDialog(self, player_error)
        self._playback_error_dialog = dialog
        dialog.run()
        self._playback_error_dialog = None

    def __configure_scan_dirs(self, library):
        """Get user to configure scan dirs, if none is set up"""
        if not get_scan_dirs() and not len(library) and \
                quodlibet.is_first_session("quodlibet"):
            print_d("Couldn't find any scan dirs")
            if qltk.ConfirmAction(self, _("Set up library directories?"),
                   _("You don't have any music library set up. "
                     "Would you like to do that now?")).run():
                prefs = PreferencesWindow(self)
                prefs.set_page("library")
                prefs.show()

    def __add_bookmark(self, librarian, player):
        if player.song:
            position = player.get_position() // 1000
            bookmarks = player.song.bookmarks
            new_mark = (position, _("Bookmark Name"))
            if new_mark not in bookmarks:
                bookmarks.append(new_mark)
                player.song.bookmarks = bookmarks

    def __edit_bookmarks(self, librarian, player):
        if player.song:
            window = EditBookmarks(self, librarian, player)
            window.show()

    def __key_pressed(self, player, event):
        if not player.song:
            return

        def seek_relative(seconds):
            current = player.get_position()
            current += seconds * 1000
            current = min(player.song("~#length") * 1000 - 1, current)
            current = max(0, current)
            player.seek(current)

        if qltk.is_accel(event, "<alt>Right"):
            seek_relative(10)
            return True
        elif qltk.is_accel(event, "<alt>Left"):
            seek_relative(-10)
            return True

    def __destroy(self, *args):
        if self.__delayed_setup:
            GLib.source_remove(self.__delayed_setup)
        # The tray icon plugin tries to unhide QL because it gets disabled
        # on Ql exit. The window should stay hidden after destroy.
        self.show = lambda: None
        self.present = self.show

    def __drag_data_received(self, widget, ctx, x, y, sel, tid, etime):
        assert tid == DND_URI_LIST

        uris = sel.get_uris()

        dirs = []
        error = False
        for uri in uris:
            try:
                uri = URI(uri)
            except ValueError:
                continue

            if uri.is_filename:
                loc = os.path.normpath(uri.filename)
                if os.path.isdir(loc):
                    dirs.append(loc)
                else:
                    loc = os.path.realpath(loc)
                    if loc not in self.__library:
                        self.__library.add_filename(loc)
            elif app.player.can_play_uri(uri):
                if uri not in self.__library:
                    self.__library.add([RemoteFile(uri)])
            else:
                error = True
                break
        Gtk.drag_finish(ctx, not error, False, etime)
        if error:
            ErrorMessage(
                self, _("Unable to add songs"),
                _("<b>%s</b> uses an unsupported protocol.") % uri).run()
        else:
            if dirs:
                copool.add(
                    self.__library.scan, dirs,
                    cofuncid="library", funcid="library")

    def __songlist_drag_data_recv(self, view, *args):
        if callable(self.browser.reordered):
            self.browser.reordered(view)
        self.songlist.clear_sort()

    def __save_browser(self, *args):
        print_d("Saving active browser state")
        try:
            self.browser.save()
        except NotImplementedError:
            pass

    def destroy(self, *args):
        self.__save_browser()
        super(QuodLibetWindow, self).destroy()

    def __show_or(self, widget, prop):
        ssv = self.song_scroller.get_property('visible')
        qxv = self.qexpander.get_property('visible')
        self.songpane.set_property('visible', ssv or qxv)
        if not ssv:
            self.qexpander.set_expanded(True)
        self.__expand_or(widget, prop)

    def __expand_or(self, widget, prop):
        if self.qexpander.get_property('expanded'):
            self.songpane.set_property("position", self.__handle_position)

    def __moved_pane_handle(self, widget, prop):
        if self.qexpander.get_property('expanded'):
            self.__handle_position = self.songpane.get_property("position")

    def __qex_size_allocate(self, event, param=None):
        if not self.qexpander.get_property('expanded'):
            p_max = self.songpane.get_property("max-position")
            p_cur = self.songpane.get_property("position")
            if p_max != p_cur:
                self.songpane.set_property("position", p_max)

    def __create_menu(self, player, library):
        ag = Gtk.ActionGroup.new('QuodLibetWindowActions')

        def logging_cb(*args):
            window = LoggingWindow(self)
            window.show()

        actions = [
            ('Music', None, _("_Music")),
            ('AddFolders', Gtk.STOCK_ADD, _('_Add a Folder...'),
             "<control>O", None, self.open_chooser),
            ('AddFiles', Gtk.STOCK_ADD, _('_Add a File...'),
             None, None, self.open_chooser),
            ('AddLocation', Gtk.STOCK_ADD, _('_Add a Location...'),
             None, None, self.open_location),
            ('BrowseLibrary', Gtk.STOCK_FIND, _('Open _Browser'), ""),
            ("Preferences", Gtk.STOCK_PREFERENCES, None, None, None,
             self.__preferences),
            ("Plugins", Gtk.STOCK_EXECUTE, _("_Plugins"), None, None,
             self.__plugins),
            ("Quit", Gtk.STOCK_QUIT, None, None, None, self.destroy),
            ('Filters', None, _("_Filters")),

            ("PlayedRecently", Gtk.STOCK_FIND, _("Recently _Played"),
             "", None, self.__filter_menu_actions),
            ("AddedRecently", Gtk.STOCK_FIND, _("Recently _Added"),
             "", None, self.__filter_menu_actions),
            ("TopRated", Gtk.STOCK_FIND, _("_Top 40"),
             "", None, self.__filter_menu_actions),
            ("All", Gtk.STOCK_FIND, _("All _Songs"),
             "", None, self.__filter_menu_actions),

            ("Control", None, _("_Control")),
            ("EditTags", Gtk.STOCK_PROPERTIES, _("Edit _Tags"), "", None,
             self.__current_song_prop),
            ("Information", Gtk.STOCK_INFO, None, None, None,
             self.__current_song_info),

            ("Jump", Gtk.STOCK_JUMP_TO, _("_Jump to Playing Song"),
             "<control>J", None, self.__jump_to_current),

            ("View", None, _("_View")),
            ("Help", None, _("_Help")),
            ("OutputLog", Gtk.STOCK_EDIT, _("_Output Log"),
             None, None, logging_cb),
            ]

        actions.append(("Previous", Gtk.STOCK_MEDIA_PREVIOUS, None,
                        "<control>comma", None, self.__previous_song))

        actions.append(("PlayPause", Gtk.STOCK_MEDIA_PLAY, None,
                        "<control>space", None, self.__play_pause))

        actions.append(("Next", Gtk.STOCK_MEDIA_NEXT, None,
                        "<control>period", None, self.__next_song))

        ag.add_actions(actions)

        act = Gtk.ToggleAction.new("StopAfter",
                                   _("Stop After This Song"), None, "")
        ag.add_action_with_accel(act, "<shift>space")

        # access point for the tray icon
        self.stop_after = act

        act = Gtk.Action.new(
            "AddBookmark", _("Add Bookmark"), None, Gtk.STOCK_ADD)
        act.connect_object('activate', self.__add_bookmark,
                           library.librarian, player)
        ag.add_action_with_accel(act, "<ctrl>D")

        act = Gtk.Action.new("EditBookmarks", _(u"Edit Bookmarks…"), None, "")
        act.connect_object('activate', self.__edit_bookmarks,
                           library.librarian, player)
        ag.add_action_with_accel(act, "<ctrl>B")

        act = Gtk.Action.new("About", None, None, Gtk.STOCK_ABOUT)
        act.connect_object('activate', self.__show_about, player)
        ag.add_action_with_accel(act, None)

        act = Gtk.Action.new(
            "OnlineHelp", _("Online Help"), None, Gtk.STOCK_HELP)
        act.connect_object('activate', util.website, const.ONLINE_HELP)
        ag.add_action_with_accel(act, "F1")

        act = Gtk.Action.new("SearchHelp", _("Search Help"), None, "")
        act.connect_object('activate', util.website, const.SEARCH_HELP)
        ag.add_action_with_accel(act, None)

        act = Gtk.Action.new(
            "RefreshLibrary", _("Re_fresh Library"), None, Gtk.STOCK_REFRESH)
        act.connect('activate', self.__rebuild, False)
        ag.add_action_with_accel(act, None)

        for tag_, lab in [
            ("genre", _("Filter on _Genre")),
            ("artist", _("Filter on _Artist")),
            ("album", _("Filter on Al_bum"))]:
            act = Gtk.Action.new(
                "Filter%s" % util.capitalize(tag_), lab, None, Gtk.STOCK_INDEX)
            act.connect_object('activate',
                               self.__filter_on, tag_, None, player)
            ag.add_action_with_accel(act, None)

        for (tag_, accel, label) in [
            ("genre", "G", _("Random _Genre")),
            ("artist", "T", _("Random _Artist")),
            ("album", "M", _("Random Al_bum"))]:
            act = Gtk.Action.new("Random%s" % util.capitalize(tag_), label,
                                 None, Gtk.STOCK_DIALOG_QUESTION)
            act.connect('activate', self.__random, tag_)
            ag.add_action_with_accel(act, "<control>" + accel)

        ag.add_toggle_actions([
            ("SongList", None, _("Song _List"), None, None,
             self.showhide_playlist,
             config.getboolean("memory", "songlist"))])

        ag.add_toggle_actions([
            ("Queue", None, _("_Queue"), None, None,
             self.showhide_playqueue,
             config.getboolean("memory", "queue"))])

        view_actions = []
        for i, Kind in enumerate(browsers.browsers):
            action = "View" + Kind.__name__
            label = Kind.accelerated_name
            view_actions.append((action, None, label, None, None, i))
        current = browsers.index(config.get("memory", "browser"))

        def action_callback(view_action, current):
            self.select_browser(view_action, current, library, player)
        ag.add_radio_actions(
            view_actions, current, action_callback,
            None)

        for Kind in browsers.browsers:
            if not Kind.in_menu:
                continue
            action = "Browser" + Kind.__name__
            label = Kind.accelerated_name
            act = Gtk.Action.new(action, label, None, None)
            act.connect_object('activate', LibraryBrowser.open, Kind, library)
            ag.add_action_with_accel(act, None)

        debug_menu = ""
        if const.DEBUG:
            debug_menu = (
                "<separator/>"
                "<menuitem action='OutputLog' always-show-image='true'/>")

        ui = Gtk.UIManager()
        ui.insert_action_group(ag, -1)
        menustr = const.MENU % {"browsers": browsers.BrowseLibrary(),
                                "views": browsers.ViewBrowser(),
                                "debug": debug_menu}
        ui.add_ui_from_string(menustr)

        # Cute. So. UIManager lets you attach tooltips, but when they're
        # for menu items, they just get ignored. So here I get to actually
        # attach them.
        ui.get_widget("/Menu/Music/RefreshLibrary").set_tooltip_text(
                _("Check for changes in your library"))

        ui.get_widget("/Menu/Filters/TopRated").set_tooltip_text(
                _("The 40 songs you've played most (more than 40 may "
                  "be chosen if there are ties)"))

        return ui

    def __show_about(self, player):
        about = AboutQuodLibet(self, player)
        about.run()
        about.destroy()

    def __browser_configure(self, paned, event, browser):
        if paned.get_property('position-set'):
            key = "%s_pos" % browser.__class__.__name__
            config.set("browsers", key, str(paned.get_relative()))

    def select_browser(self, activator, current, library, player,
                       restore=False):
        if isinstance(current, Gtk.RadioAction):
            current = current.get_current_value()
        Browser = browsers.get(current)
        config.set("memory", "browser", Browser.__name__)
        if self.browser:
            container = self.browser.__container
            self.browser.unpack(container, self.songpane)
            if self.browser.accelerators:
                self.remove_accel_group(self.browser.accelerators)
            container.destroy()
            self.browser.destroy()
        self.browser = Browser(library, True)
        self.browser.connect('songs-selected', self.__browser_cb)
        self.browser.connect('activated', self.__browser_activate)
        if restore:
            self.browser.restore()
            self.browser.activate()
        self.browser.finalize(restore)
        if self.browser.reordered:
            self.songlist.enable_drop()
        elif self.browser.dropped:
            self.songlist.enable_drop(False)
        else:
            self.songlist.disable_drop()
        if self.browser.accelerators:
            self.add_accel_group(self.browser.accelerators)

        container = self.browser.__container = self.browser.pack(self.songpane)

        # find a paned and save the position
        paned = None
        for widget in qltk.find_widgets(container, RPaned):
            if widget is not self.songpane:
                paned = widget
                break

        if paned:
            try:
                key = "%s_pos" % self.browser.__class__.__name__
                val = config.getfloat("browsers", key)
                # Use a minimum restore size
                val = max(val, 0.1)
            except:
                val = 0.4
            paned.connect(
                'notify::position', self.__browser_configure, self.browser)

            paned.set_relative(val)

        player.replaygain_profiles[1] = self.browser.replaygain_profiles
        player.volume = player.volume
        self.__browserbox.add(container)
        container.show()
        self.__hide_menus()
        self.__hide_headers()
        self.__refresh_size()

    def __update_paused(self, player, paused):
        menu = self.ui.get_widget("/Menu/Control/PlayPause")

        if paused:
            key = Gtk.STOCK_MEDIA_PLAY
        else:
            key = Gtk.STOCK_MEDIA_PAUSE
        text = Gtk.stock_lookup(key).label
        menu.get_image().set_from_stock(key, Gtk.IconSize.MENU)
        menu.set_label(text)
        menu.set_use_underline(True)

    def __song_ended(self, player, song, stopped):
        # check if the song should be removed base on the
        # active filter of the current browser
        active_filter = self.browser.active_filter
        if song and active_filter and not active_filter(song):
            iter_ = self.songlist.model.find(song)
            if iter_:
                self.songlist.remove_iters([iter_])

        if self.stop_after.get_active():
            player.paused = True
            self.stop_after.set_active(False)

    def __song_changed(self, player, songs):
        if player.info in songs:
            self.__update_title(player)

    def __update_title(self, player):
        song = player.info
        title = "Quod Libet"
        if song:
            title = song.comma("~title~version~~people") + " - " + title
        self.set_title(title)

    def __song_started(self, player, song):
        self.__update_title(player)

        for wid in ["Jump", "Next", "EditTags", "Information",
                    "EditBookmarks", "AddBookmark", "StopAfter"]:
            self.ui.get_widget(
                '/Menu/Control/' + wid).set_sensitive(bool(song))
        for wid in ["FilterAlbum", "FilterArtist", "FilterGenre"]:
            self.ui.get_widget(
                '/Menu/Filters/' + wid).set_sensitive(bool(song))
        if song:
            for h in ['genre', 'artist', 'album']:
                self.ui.get_widget(
                    "/Menu/Filters/Filter%s" % h.capitalize()).set_sensitive(
                    h in song)

        # don't jump on stream changes (player.info != player.song)
        if song and player.song is song and not self.songlist._activated and \
            config.getboolean("settings", "jump"):
            self.__jump_to_current(False)

    def __refresh_size(self):
        ssv = self.song_scroller.get_property('visible')
        qex = self.qexpander.get_property('visible')

        if ssv or qex:
            return

        # Handle more later if needed..
        if not isinstance(self.browser, Gtk.Box):
            return

        # If a child expands the browser will take the new space
        for child in self.browser.get_children():
            if self.browser.query_child_packing(child)[0]:
                break
        else:
            # no expanding child, make the window smaller instead
            width, height = self.get_size()
            height = self.size_request().height
            self.resize(width, height)

    def showhide_playlist(self, toggle):
        self.song_scroller.set_property('visible', toggle.get_active())
        self.__refresh_size()

    def showhide_playqueue(self, toggle):
        self.qexpander.set_property('visible', toggle.get_active())
        self.__refresh_size()

    def __play_pause(self, *args):
        if app.player.song is None:
            app.player.reset()
        else:
            app.player.paused ^= True

    def __jump_to_current(self, explicit):
        """Select/scroll to the current playing song in the playlist.
        If it can't be found tell the browser to properly fill the playlist
        with an appropriate selection containing the song.

        explicit means that the jump request comes from the user and not
        from an event like song-started.
        """

        def idle_jump_to(song, select):
            ok = self.songlist.jump_to_song(song, select=select)
            if ok:
                self.songlist.grab_focus()
            return False

        song = app.player.song

        # We are not playing a song
        if song is None:
            return

        ok = self.songlist.jump_to_song(song, select=explicit)
        if ok:
            self.songlist.grab_focus()
        elif explicit:
            # if we can't find it and the user requested it, try harder
            self.browser.scroll(song)
            # We need to wait until the browser has finished
            # scrolling/filling and the songlist is ready.
            # Not perfect, but works for now.
            GLib.idle_add(
                idle_jump_to, song, explicit, priority=GLib.PRIORITY_LOW)

    def __next_song(self, *args):
        app.player.next()

    def __previous_song(self, *args):
        app.player.previous()

    def __random(self, item, key):
        self.browser.filter_random(key)

    def __filter_menu_actions(self, menuitem):
        name = menuitem.get_name()

        if name == "PlayedRecently":
            self.__make_query("#(lastplayed < 7 days ago)")
        elif name == "AddedRecently":
            self.__make_query("#(added < 7 days ago)")
        elif name == "TopRated":
            bg = background_filter()
            songs = (bg and filter(bg, self.__library)) or self.__library
            songs = [song.get("~#playcount", 0) for song in songs]
            if len(songs) == 0:
                return
            songs.sort()
            if len(songs) < 40:
                self.__make_query("#(playcount > %d)" % (songs[0] - 1))
            else:
                self.__make_query("#(playcount > %d)" % (songs[-40] - 1))
        elif name == "All":
            self.browser.unfilter()

    def __rebuild(self, activator, force):
        scan_library(self.__library, force)

    # Set up the preferences window.
    def __preferences(self, activator):
        window = PreferencesWindow(self)
        window.show()

    def __plugins(self, activator):
        window = PluginWindow(self)
        window.show()

    def open_location(self, action):
        name = GetStringDialog(self, _("Add a Location"),
            _("Enter the location of an audio file:"),
            okbutton=Gtk.STOCK_ADD).run()
        if name:
            if not util.uri_is_valid(name):
                ErrorMessage(
                    self, _("Unable to add location"),
                    _("<b>%s</b> is not a valid location.") % (
                    util.escape(name))).run()
            elif not app.player.can_play_uri(name):
                ErrorMessage(
                    self, _("Unable to add location"),
                    _("<b>%s</b> uses an unsupported protocol.") % (
                    util.escape(name))).run()
            else:
                if name not in self.__library:
                    self.__library.add([RemoteFile(name)])

    def open_chooser(self, action):
        last_dir = self.last_dir
        if not os.path.exists(last_dir):
            last_dir = const.HOME

        class MusicFolderChooser(FolderChooser):
            def __init__(self, parent, init_dir):
                super(MusicFolderChooser, self).__init__(
                    parent, _("Add Music"), init_dir)

                cb = Gtk.CheckButton(_("Watch this folder for new songs"))
                # enable if no folders are being watched
                cb.set_active(not get_scan_dirs())
                cb.show()
                self.set_extra_widget(cb)

            def run(self):
                fns = super(MusicFolderChooser, self).run()
                cb = self.get_extra_widget()
                return fns, cb.get_active()

        class MusicFileChooser(FileChooser):
            def __init__(self, parent, init_dir):
                super(MusicFileChooser, self).__init__(
                    parent, _("Add Music"), formats.filter, init_dir)

        if action.get_name() == "AddFolders":
            dialog = MusicFolderChooser(self, last_dir)
            fns, do_watch = dialog.run()
            dialog.destroy()
            if fns:
                # scan them
                self.last_dir = fns[0]
                copool.add(self.__library.scan, fns, funcid="library")

                # add them as library scan directory
                if do_watch:
                    dirs = get_scan_dirs()
                    for fn in fns:
                        if fn not in dirs:
                            dirs.append(fn)
                    set_scan_dirs(dirs)
        else:
            dialog = MusicFileChooser(self, last_dir)
            fns = dialog.run()
            dialog.destroy()
            if fns:
                self.last_dir = os.path.dirname(fns[0])
                for filename in map(os.path.realpath, map(util.fsnative, fns)):
                    self.__library.add_filename(filename)

    def __songs_popup_menu(self, songlist):
        path, col = songlist.get_cursor()
        header = col.header_name
        menu = self.songlist.Menu(header, self.browser, self.__library)
        if menu is not None:
            return self.songlist.popup_menu(menu, 0,
                    Gtk.get_current_event_time())

    def __current_song_prop(self, *args):
        song = app.player.song
        if song:
            librarian = self.__library.librarian
            window = SongProperties(librarian, [song], parent=self)
            window.show()

    def __current_song_info(self, *args):
        song = app.player.song
        if song:
            librarian = self.__library.librarian
            window = Information(librarian, [song], self)
            window.show()

    def __hide_menus(self):
        menus = {'genre': ["/Menu/Filters/FilterGenre",
                           "/Menu/Filters/RandomGenre"],
                 'artist': ["/Menu/Filters/FilterArtist",
                           "/Menu/Filters/RandomArtist"],
                 'album': ["/Menu/Filters/FilterAlbum",
                           "/Menu/Filters/RandomAlbum"],
                 None: ["/Menu/Filters/PlayedRecently",
                        "/Menu/Filters/AddedRecently",
                        "/Menu/Filters/TopRated",
                        "/Menu/Filters/All"]}
        for key, widgets in menus.items():
            c = self.browser.can_filter(key)
            for widget in widgets:
                self.ui.get_widget(widget).set_property('visible', c)

    def __browser_activate(self, browser):
        model = self.songlist.get_model()
        model.reset()
        if app.player.go_to(model.get_iter_first(), True):
            app.player.paused = False

    def __browser_cb(self, browser, songs, sorted):
        if browser.background:
            bg = background_filter()
            if bg:
                songs = filter(bg, songs)
        self.songlist.set_songs(songs, sorted)

    def __filter_on(self, header, songs, player):
        browser = self.browser

        if not browser:
            return

        # Fall back to the playing song
        if songs is None:
            if player.song:
                songs = [player.song]
            else:
                return

        browser.filter_on(songs, header)

    def __hide_headers(self, activator=None):
        for column in self.songlist.get_columns():
            if self.browser.headers is None:
                column.set_visible(True)
            else:
                for tag in util.tagsplit(column.header_name):
                    if tag in self.browser.headers:
                        column.set_visible(True)
                        break
                else:
                    column.set_visible(False)

    def __cols_changed(self, songlist):
        headers = [col.header_name for col in songlist.get_columns()]
        try:
            headers.remove('~current')
        except ValueError:
            pass
        if len(headers) == len(config.get_columns()):
            # Not an addition or removal (handled separately)
            config.set_columns(headers)
            SongList.headers = headers

    def __make_query(self, query):
        if self.browser.can_filter_text():
            self.browser.filter_text(query.encode('utf-8'))
            self.browser.activate()

    def __set_time(self, info, songs):
        i = len(songs)
        length = sum(song.get("~#length", 0) for song in songs)
        t = self.browser.statusbar(i) % {
            'count': i, 'time': util.format_time_long(length)}
        self.statusbar.set_default_text(t)
