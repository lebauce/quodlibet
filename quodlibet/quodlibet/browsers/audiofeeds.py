# -*- coding: utf-8 -*-
# Copyright 2005 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import cPickle as pickle
import os
import sys
import threading
import time

from gi.repository import Gtk, GLib, Pango, Gdk

from quodlibet import config
from quodlibet import const
from quodlibet import formats
from quodlibet import qltk
from quodlibet import util

from quodlibet.browsers._base import Browser
from quodlibet.formats._audio import AudioFile
from quodlibet.formats.remote import RemoteFile
from quodlibet.qltk.downloader import DownloadWindow
from quodlibet.qltk.getstring import GetStringDialog
from quodlibet.qltk.msg import ErrorMessage
from quodlibet.qltk.songsmenu import SongsMenu
from quodlibet.qltk.views import AllTreeView
from quodlibet.util import connect_obj
from quodlibet.qltk.x import ScrolledWindow, Alignment, Button


FEEDS = os.path.join(const.USERDIR, "feeds")
DND_URI_LIST, DND_MOZ_URL = range(2)

# Migration path for pickle
sys.modules["browsers.audiofeeds"] = sys.modules[__name__]


class InvalidFeed(ValueError):
    pass


class Feed(list):
    def __init__(self, uri):
        self.name = _("Unknown")
        self.uri = uri
        self.changed = False
        self.website = ""
        self.__lastgot = 0

    def get_age(self):
        return time.time() - self.__lastgot

    @staticmethod
    def __fill_af(feed, af):
        try:
            af["title"] = feed.title or _("Unknown")
        except:
            af["title"] = _("Unknown")
        try:
            af["date"] = "%04d-%02d-%02d" % feed.modified_parsed[:3]
        except (AttributeError, TypeError):
            pass

        for songkey, feedkey in [
                ("website", "link"),
                ("description", "tagline"),
                ("language", "language"),
                ("copyright", "copyright"),
                ("organization", "publisher"),
                ("license", "license")]:
            try:
                value = getattr(feed, feedkey)
            except:
                pass
            else:
                if value and value not in af.list(songkey):
                    af.add(songkey, value)

        try:
            author = feed.author_detail
        except AttributeError:
            try:
                author = feed.author
            except AttributeError:
                pass
            else:
                if author and author not in af.list("artist"):
                    af.add('artist', author)
        else:
            try:
                if author.email and author.email not in af.list("contact"):
                    af.add("contact", author.email)
            except AttributeError:
                pass
            try:
                if author.name and author.name not in af.list("artist"):
                    af.add("artist", author.name)
            except AttributeError:
                pass

        try:
            values = feed.contributors
        except AttributeError:
            pass
        else:
            for value in values:
                try:
                    value = value.name
                except AttributeError:
                    pass
                else:
                    if value and value not in af.list("performer"):
                        af.add("performer", value)

        try:
            af["~#length"] = util.parse_time(feed.itunes_duration)
        except (AttributeError, ValueError):
            pass

        try:
            values = dict(feed.categories).values()
        except AttributeError:
            pass
        else:
            for value in values:
                if value and value not in af.list("genre"):
                    af.add("genre", value)

    def parse(self):
        try:
            doc = feedparser.parse(self.uri)
        except:
            return False

        try:
            album = doc.channel.title
        except AttributeError:
            return False

        if album:
            self.name = album
        else:
            self.name = _("Unknown")

        defaults = AudioFile({"feed": self.uri})
        try:
            self.__fill_af(doc.channel, defaults)
        except:
            return False

        entries = []
        uris = set()
        for entry in doc.entries:
            try:
                for enclosure in entry.enclosures:
                    try:
                        if ("audio" in enclosure.type or
                                "ogg" in enclosure.type or
                                formats.filter(enclosure.url)):
                            uri = enclosure.url.encode('ascii', 'replace')
                            try:
                                size = enclosure.length
                            except AttributeError:
                                size = 0
                            entries.append((uri, entry, size))
                            uris.add(uri)
                            break
                    except AttributeError:
                        pass
            except AttributeError:
                pass

        for entry in list(self):
            if entry["~uri"] not in uris:
                self.remove(entry)
            else:
                uris.remove(entry["~uri"])

        entries.reverse()
        for uri, entry, size in entries:
            if uri in uris:
                song = RemoteFile(uri)
                song["~#size"] = size
                song.fill_metadata = False
                song.update(defaults)
                song["album"] = self.name
                try:
                    self.__fill_af(entry, song)
                except:
                    pass
                else:
                    self.insert(0, song)
        self.__lastgot = time.time()
        return bool(uris)


class AddFeedDialog(GetStringDialog):
    def __init__(self, parent):
        super(AddFeedDialog, self).__init__(
            qltk.get_top_parent(parent), _("New Feed"),
            _("Enter the location of an audio feed:"),
            okbutton=Gtk.STOCK_ADD)

    def run(self):
        uri = super(AddFeedDialog, self).run()
        if uri:
            return Feed(uri.encode('ascii', 'replace'))
        else:
            return None


class AudioFeeds(Browser, Gtk.VBox):
    __gsignals__ = Browser.__gsignals__

    __feeds = Gtk.ListStore(object)  # unread

    headers = ("title artist performer ~people album date website language "
               "copyright organization license contact").split()

    name = _("Audio Feeds")
    accelerated_name = _("_Audio Feeds")
    priority = 20
    uses_main_library = False

    __last_folder = const.HOME

    def pack(self, songpane):
        container = qltk.ConfigRHPaned("browsers", "audiofeeds_pos", 0.4)
        self.show()
        container.pack1(self, True, False)
        container.pack2(songpane, True, False)
        return container

    def unpack(self, container, songpane):
        container.remove(songpane)
        container.remove(self)

    @staticmethod
    def cell_data(col, render, model, iter, data):
        if model[iter][0].changed:
            render.markup = "<b>%s</b>" % util.escape(model[iter][0].name)
        else:
            render.markup = util.escape(model[iter][0].name)
        render.set_property('markup', render.markup)

    @classmethod
    def changed(klass, feeds):
        for row in klass.__feeds:
            if row[0] in feeds:
                row[0].changed = True
                row[0] = row[0]
        AudioFeeds.write()

    @classmethod
    def write(klass):
        feeds = [row[0] for row in klass.__feeds]
        f = file(FEEDS, "wb")
        pickle.dump(feeds, f, pickle.HIGHEST_PROTOCOL)
        f.close()

    @classmethod
    def init(klass, library):
        try:
            feeds = pickle.load(file(FEEDS, "rb"))
        except (pickle.PickleError, EnvironmentError, EOFError):
            pass
        else:
            for feed in feeds:
                klass.__feeds.append(row=[feed])
        GLib.idle_add(klass.__do_check)

    @classmethod
    def __do_check(klass):
        thread = threading.Thread(target=klass.__check, args=())
        thread.setDaemon(True)
        thread.start()

    @classmethod
    def __check(klass):
        for row in klass.__feeds:
            feed = row[0]
            if feed.get_age() < 2 * 60 * 60:
                continue
            elif feed.parse():
                feed.changed = True
                row[0] = feed
        klass.write()
        GLib.timeout_add(60 * 60 * 1000, klass.__do_check)

    def Menu(self, songs, library, items):
        if len(songs) == 1:
            item = qltk.MenuItem(_(u"_Download…"), Gtk.STOCK_CONNECT)
            item.connect('activate', self.__download, songs[0]("~uri"))
            item.set_sensitive(not songs[0].is_file)
        else:
            songs = filter(lambda s: not s.is_file, songs)
            uris = [song("~uri") for song in songs]
            item = qltk.MenuItem(_(u"_Download…"), Gtk.STOCK_CONNECT)
            item.connect('activate', self.__download_many, uris)
            item.set_sensitive(bool(songs))

        items.append([item])
        menu = SongsMenu(library, songs, items=items)
        return menu

    def __download_many(self, activator, sources):
        chooser = Gtk.FileChooserDialog(
            title=_("Download Files"), parent=qltk.get_top_parent(self),
            action=Gtk.FileChooserAction.CREATE_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        chooser.set_current_folder(self.__last_folder)
        resp = chooser.run()
        if resp == Gtk.ResponseType.OK:
            target = chooser.get_filename()
            if target:
                type(self).__last_folder = os.path.dirname(target)
                for i, source in enumerate(sources):
                    base = os.path.basename(source)
                    if not base:
                        base = ("file%d" % i) + (
                            os.path.splitext(source)[1] or ".audio")
                    fulltarget = os.path.join(target, base)
                    DownloadWindow.download(source, fulltarget, self)
        chooser.destroy()

    def __download(self, activator, source):
        chooser = Gtk.FileChooserDialog(
            title=_("Download File"), parent=qltk.get_top_parent(self),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        chooser.set_current_folder(self.__last_folder)
        name = os.path.basename(source)
        if name:
            chooser.set_current_name(name)
        resp = chooser.run()
        if resp == Gtk.ResponseType.OK:
            target = chooser.get_filename()
            if target:
                type(self).__last_folder = os.path.dirname(target)
                DownloadWindow.download(source, target, self)
        chooser.destroy()

    def __init__(self, library):
        super(AudioFeeds, self).__init__(spacing=6)

        self.__view = view = AllTreeView()
        self.__render = render = Gtk.CellRendererText()
        render.set_property('ellipsize', Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("Audio Feeds", render)
        col.set_cell_data_func(render, AudioFeeds.cell_data)
        view.append_column(col)
        view.set_model(self.__feeds)
        view.set_rules_hint(True)
        view.set_headers_visible(False)
        swin = ScrolledWindow()
        swin.set_shadow_type(Gtk.ShadowType.IN)
        swin.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        swin.add(view)
        self.pack_start(swin, True, True, 0)

        new = Button(_("_New"), Gtk.STOCK_ADD, Gtk.IconSize.MENU)
        new.connect('clicked', self.__new_feed)
        view.get_selection().connect('changed', self.__changed)
        view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        view.connect('popup-menu', self.__popup_menu)

        targets = [
            ("text/uri-list", 0, DND_URI_LIST),
            ("text/x-moz-url", 0, DND_MOZ_URL)
        ]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        view.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.COPY)
        view.connect('drag-data-received', self.__drag_data_received)
        view.connect('drag-motion', self.__drag_motion)
        view.connect('drag-leave', self.__drag_leave)

        connect_obj(self, 'destroy', self.__save, view)

        self.pack_start(Alignment(new, left=3, bottom=3), False, True, 0)

        for child in self.get_children():
            child.show_all()

    def __drag_motion(self, view, ctx, x, y, time):
        targets = [t.name() for t in ctx.list_targets()]
        if "text/x-quodlibet-songs" not in targets:
            view.get_parent().drag_highlight()
            return True
        return False

    def __drag_leave(self, view, ctx, time):
        view.get_parent().drag_unhighlight()

    def __drag_data_received(self, view, ctx, x, y, sel, tid, etime):
        view.emit_stop_by_name('drag-data-received')
        targets = [
            ("text/uri-list", 0, DND_URI_LIST),
            ("text/x-moz-url", 0, DND_MOZ_URL)
        ]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        view.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.COPY)
        if tid == DND_URI_LIST:
            uri = sel.get_uris()[0]
        elif tid == DND_MOZ_URL:
            uri = sel.data.decode('utf16', 'replace').split('\n')[0]
        else:
            ctx.finish(False, False, etime)
            return

        ctx.finish(True, False, etime)

        feed = Feed(uri.encode("ascii", "replace"))
        feed.changed = feed.parse()
        if feed:
            self.__feeds.append(row=[feed])
            AudioFeeds.write()
        else:
            ErrorMessage(
                self, _("Unable to add feed"),
                _("%s could not be added. The server may be down, "
                  "or the location may not be an audio feed.") %
                util.bold(util.escape(feed.uri))).run()

    def __popup_menu(self, view):
        model, paths = view.get_selection().get_selected_rows()
        menu = Gtk.Menu()
        refresh = Gtk.ImageMenuItem(Gtk.STOCK_REFRESH, use_stock=True)
        delete = Gtk.ImageMenuItem(Gtk.STOCK_DELETE, use_stock=True)

        connect_obj(refresh,
            'activate', self.__refresh, [model[p][0] for p in paths])
        connect_obj(delete,
            'activate', map, model.remove, map(model.get_iter, paths))

        menu.append(refresh)
        menu.append(delete)
        menu.show_all()
        menu.connect('selection-done', lambda m: m.destroy())

        # XXX: keep the menu arround
        self.__menu = menu

        return view.popup_menu(menu, 0, Gtk.get_current_event_time())

    def __save(self, view):
        AudioFeeds.write()

    def __refresh(self, feeds):
        changed = filter(Feed.parse, feeds)
        AudioFeeds.changed(changed)

    def activate(self):
        self.__changed(self.__view.get_selection())

    def __changed(self, selection):
        model, paths = selection.get_selected_rows()
        if model and paths:
            songs = []
            for path in paths:
                model[path][0].changed = False
                songs.extend(model[path][0])
            self.songs_selected(songs, True)
            config.set("browsers", "audiofeeds",
                       "\t".join([model[path][0].name for path in paths]))

    def __new_feed(self, activator):
        feed = AddFeedDialog(self).run()
        if feed is not None:
            feed.changed = feed.parse()
            if feed:
                self.__feeds.append(row=[feed])
                AudioFeeds.write()
            else:
                ErrorMessage(
                    self, _("Unable to add feed"),
                    _("%s could not be added. The server may be down, "
                      "or the location may not be an audio feed.") %
                    util.bold(util.escape(feed.uri))).run()

    def restore(self):
        try:
            names = config.get("browsers", "audiofeeds").split("\t")
        except:
            pass
        else:
            self.__view.select_by_func(lambda r: r[0].name in names)

browsers = []
try:
    import feedparser
except ImportError:
    print_w(_("Could not import %s. Audio Feeds browser disabled.")
            % "python-feedparser")
else:
    from quodlibet import app
    if not app.player or app.player.can_play_uri("http://"):
        browsers = [AudioFeeds]
    else:
        print_w(_("The current audio backend does not support URLs, "
                  "Audio Feeds browser disabled."))
