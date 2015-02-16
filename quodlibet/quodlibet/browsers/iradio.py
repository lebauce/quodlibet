# -*- coding: utf-8 -*-
# Copyright 2011 Joe Wreschnig, Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import sys
import bz2
import urllib2
import urllib
import itertools

from gi.repository import Gtk, GLib, Pango

from quodlibet import const
from quodlibet import qltk
from quodlibet import util
from quodlibet import config

from quodlibet.browsers._base import Browser
from quodlibet.formats.remote import RemoteFile
from quodlibet.formats._audio import TAG_TO_SORT, MIGRATE, AudioFile
from quodlibet.library import SongLibrary
from quodlibet.query import Query
from quodlibet.qltk.getstring import GetStringDialog
from quodlibet.qltk.songsmenu import SongsMenu
from quodlibet.qltk.notif import Task
from quodlibet.util import copool, connect_destroy, sanitize_tags, connect_obj
from quodlibet.util.string import decode, encode
from quodlibet.util.uri import URI
from quodlibet.qltk.views import AllTreeView
from quodlibet.qltk.searchbar import SearchBarBox
from quodlibet.qltk.completion import LibraryTagCompletion
from quodlibet.qltk.x import MenuItem, Alignment, ScrolledWindow
from quodlibet.qltk.x import SymbolicIconImage
from quodlibet.qltk.menubutton import MenuButton

STATION_LIST_URL = \
    "http://bitbucket.org/lazka/quodlibet/downloads/radiolist.bz2"
STATIONS_FAV = os.path.join(const.USERDIR, "stations")
STATIONS_ALL = os.path.join(const.USERDIR, "stations_all")

# TODO: - Do the update in a thread
#       - Ranking: reduce duplicate stations (max 3 URLs per station)
#                  prefer stations that match a genre?

# Migration path for pickle
sys.modules["browsers.iradio"] = sys.modules[__name__]


class IRFile(RemoteFile):
    multisong = True
    can_add = False

    format = "Radio Station"

    __CAN_CHANGE = "title artist grouping".split()

    def __get(self, base_call, key, *args, **kwargs):
        if key == "title" and "title" not in self and "organization" in self:
            return base_call("organization", *args, **kwargs)

        # split title by " - " if no artist tag is present and
        # this is not the main song: common format for shoutcast stations
        if not self.multisong and key in ("title", "artist") and \
                "title" in self and "artist" not in self:
            title = base_call("title").split(" - ", 1)
            if len(title) > 1:
                return (key == "title" and title[-1]) or title[0]

        if key in ("artist", TAG_TO_SORT["artist"]) and \
                not base_call(key, *args) and "website" in self:
            return base_call("website", *args)

        if key == "~format" and "audio-codec" in self:
            return "%s (%s)" % (self.format,
                                base_call("audio-codec", *args, **kwargs))
        return base_call(key, *args, **kwargs)

    def __call__(self, key, *args, **kwargs):
        base_call = super(IRFile, self).__call__
        return self.__get(base_call, key, *args, **kwargs)

    def get(self, key, *args, **kwargs):
        base_call = super(IRFile, self).get
        return self.__get(base_call, key, *args, **kwargs)

    def write(self):
        pass

    def to_dump(self):
        # dump without title
        title = None
        if "title" in self:
            title = self["title"]
            del self["title"]
        dump = super(IRFile, self).to_dump()
        if title is not None:
            self["title"] = title

        # add all generated tags
        lines = dump.splitlines()
        for tag in ["title", "artist", "~format"]:
            value = self.get(tag)
            if value is not None:
                lines.append("%s=%s" % (tag, encode(value)))
        return "\n".join(lines)

    def can_change(self, k=None):
        if self.streamsong:
            if k is None:
                return []
            else:
                return False
        else:
            if k is None:
                return self.__CAN_CHANGE
            else:
                return k in self.__CAN_CHANGE


def ParsePLS(file):
    data = {}

    lines = file.readlines()
    if not lines or "[playlist]" not in lines.pop(0):
        return []

    for line in lines:
        try:
            head, val = line.strip().split("=", 1)
        except (TypeError, ValueError):
            continue
        else:
            head = head.lower()
            if head.startswith("length") and val == "-1":
                continue
            else:
                data[head] = val.decode('utf-8', 'replace')

    count = 1
    files = []
    warnings = []
    while True:
        if "file%d" % count in data:
            filename = data["file%d" % count].encode('utf-8', 'replace')
            if filename.lower()[-4:] in [".pls", ".m3u"]:
                warnings.append(filename)
            else:
                irf = IRFile(filename)
                for key in ["title", "genre", "artist"]:
                    try:
                        irf[key] = data["%s%d" % (key, count)]
                    except KeyError:
                        pass
                try:
                    irf["~#length"] = int(data["length%d" % count])
                except (KeyError, TypeError, ValueError):
                    pass
                files.append(irf)
        else:
            break
        count += 1

    if warnings:
        qltk.WarningMessage(
            None, _("Unsupported file type"),
            _("Station lists can only contain locations of stations, "
              "not other station lists or playlists. The following locations "
              "cannot be loaded:\n%s") %
            "\n  ".join(map(util.escape, warnings))
        ).run()

    return files


def ParseM3U(fileobj):
    files = []
    pending_title = None
    for line in fileobj:
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                pending_title = line.split(",", 1)[1]
            except IndexError:
                pending_title = None
        elif line.startswith("http"):
            irf = IRFile(line)
            if pending_title:
                irf["title"] = pending_title.decode('utf-8', 'replace')
                pending_title = None
            files.append(irf)
    return files


def add_station(uri):
    """Fetches the URI content and extracts IRFiles"""

    irfs = []
    if isinstance(uri, unicode):
        uri = uri.encode('utf-8')

    if uri.lower().endswith(".pls") or uri.lower().endswith(".m3u"):
        try:
            sock = urllib.urlopen(uri)
        except EnvironmentError, e:
            try:
                err = e.strerror.decode(const.ENCODING, 'replace')
            except (TypeError, AttributeError):
                err = e.strerror[1].decode(const.ENCODING, 'replace')
            qltk.ErrorMessage(None, _("Unable to add station"), err).run()
            return []

        if uri.lower().endswith(".pls"):
            irfs = ParsePLS(sock)
        elif uri.lower().endswith(".m3u"):
            irfs = ParseM3U(sock)

        sock.close()
    else:
        try:
            irfs = [IRFile(uri)]
        except ValueError, err:
            qltk.ErrorMessage(None, _("Unable to add station"), err).run()

    return irfs


def download_taglist(callback, cofuncid, step=1024 * 10):
    """Generator for loading the bz2 compressed tag list.

    Calls callback with the decompressed data or None in case of
    an error."""

    with Task(_("Internet Radio"), _("Downloading station list")) as task:
        if cofuncid:
            task.copool(cofuncid)

        try:
            response = urllib2.urlopen(STATION_LIST_URL)
        except urllib2.URLError:
            GLib.idle_add(callback, None)
            return

        try:
            size = int(response.info().get("content-length", 0))
        except ValueError:
            size = 0

        decomp = bz2.BZ2Decompressor()

        data = ""
        temp = ""
        read = 0
        while temp or not data:
            read += len(temp)

            if size:
                task.update(float(read) / size)
            else:
                task.pulse()
            yield True

            try:
                data += decomp.decompress(temp)
                temp = response.read(step)
            except (IOError, EOFError):
                data = None
                break
        response.close()

        yield True

        stations = None
        if data:
            stations = parse_taglist(data)

        GLib.idle_add(callback, stations)


def parse_taglist(data):
    """Parses a dump file like list of tags and returns a list of IRFiles

    uri=http://...
    tag=value1
    tag2=value
    tag=value2
    uri=http://...
    ...

    """

    stations = []
    station = None

    for l in data.split("\n"):
        key = l.split("=")[0]
        value = l.split("=", 1)[1]
        if key == "uri":
            if station:
                stations.append(station)
            station = IRFile(value)
            continue

        value = decode(value)
        san = sanitize_tags({key: value}, stream=True).items()
        if not san:
            continue

        key, value = san[0]
        if key == "~listenerpeak":
            key = "~#listenerpeak"
            value = int(value)

        if isinstance(value, str):
            value = value.decode("utf-8")
            if value not in station.list(key):
                station.add(key, value)
        else:
            station[key] = value

    if station:
        stations.append(station)

    return stations


class AddNewStation(GetStringDialog):
    def __init__(self, parent):
        super(AddNewStation, self).__init__(
            parent, _("New Station"),
            _("Enter the location of an Internet radio station:"),
            okbutton=Gtk.STOCK_ADD)

    def _verify_clipboard(self, text):
        # try to extract a URI from the clipboard
        for line in text.splitlines():
            line = line.strip()

            try:
                URI(line)
            except ValueError:
                pass
            else:
                return line


class GenreFilter(object):
    STAR = ["genre", "organization"]

    # This probably needs improvements
    GENRES = {
        "electronic": (
            _("Electronic"),
            "|(electr,house,techno,trance,/trip.?hop/,&(drum,n,bass),chill,"
            "dnb,minimal,/down(beat|tempo)/,&(dub,step))"),
        "rap": (_("Hip Hop / Rap"), "|(&(hip,hop),rap)"),
        "oldies": (_("Oldies"), "|(/[2-9]0\S?s/,oldies)"),
        "r&b": (_("R&B"), "/r(\&|n)b/"),
        "japanese": (_("Japanese"), "|(anime,jpop,japan,jrock)"),
        "indian": (_("Indian"), "|(bollywood,hindi,indian,bhangra)"),
        "religious": (
            _("Religious"),
            "|(religious,christian,bible,gospel,spiritual,islam)"),
        "charts": (_("Charts"), "|(charts,hits,top)"),
        "turkish": (_("Turkish"), "|(turkish,turkce)"),
        "reggae": (_("Reggae / Dancehall"), "|(/reggae([^\w]|$)/,dancehall)"),
        "latin": (_("Latin"), "|(latin,salsa)"),
        "college": (_("College Radio"), "|(college,campus)"),
        "talk_news": (_("Talk / News"), "|(news,talk)"),
        "ambient": (_("Ambient"), "|(ambient,easy)"),
        "jazz": (_("Jazz"), "|(jazz,swing)"),
        "classical": (_("Classical"), "classic"),
        "pop": (_("Pop"), None),
        "alternative": (_("Alternative"), None),
        "metal": (_("Metal"), None),
        "country": (_("Country"), None),
        "news": (_("News"), None),
        "schlager": (_("Schlager"), None),
        "funk": (_("Funk"), None),
        "indie": (_("Indie"), None),
        "blues": (_("Blues"), None),
        "soul": (_("Soul"), None),
        "lounge": (_("Lounge"), None),
        "punk": (_("Punk"), None),
        "reggaeton": (_("Reggaeton"), None),
        "slavic": (
            _("Slavic"),
            "|(narodna,albanian,manele,shqip,kosova)"),
        "greek": (_("Greek"), None),
        "gothic": (_("Gothic"), None),
        "rock": (_("Rock"), None),
    }

    # parsing all above takes 350ms on an atom, so only generate when needed
    __CACHE = {}

    def keys(self):
        return self.GENRES.keys()

    def query(self, key):
        if key not in self.__CACHE:
            text, filter_ = self.GENRES[key]
            if filter_ is None:
                filter_ = key
            self.__CACHE[key] = Query(filter_, star=self.STAR)
        return self.__CACHE[key]

    def text(self, key):
        return self.GENRES[key][0]


class CloseButton(Gtk.Button):
    """Reimplementation of 3.10 close button for InfoBar."""

    def __init__(self):
        image = Gtk.Image(visible=True, can_focus=False,
                          icon_name="window-close-symbolic")

        super(CloseButton, self).__init__(
            visible=False, can_focus=True, image=image,
            relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER)

        ctx = self.get_style_context()
        ctx.add_class("raised")
        ctx.add_class("close")


class QuestionBar(Gtk.InfoBar):
    """A widget which suggest to download the radio list if
    no radio stations are present.

    Connect to Gtk.InfoBar::response and check for RESPONSE_LOAD
    as response id.
    """

    RESPONSE_LOAD = 1

    def __init__(self):
        super(QuestionBar, self).__init__()
        self.connect("response", self.__response)
        self.set_message_type(Gtk.MessageType.QUESTION)

        label = Gtk.Label(label=_(
            "Would you like to load a list of popular radio stations?"))
        label.set_line_wrap(True)
        label.show()
        content = self.get_content_area()
        content.add(label)

        self.add_button(_("_Load Stations"), self.RESPONSE_LOAD)

        try:
            self.set_show_close_button(True)
        except AttributeError:
            # < gtk3.10
            action = self.get_action_area()
            close_button = CloseButton()
            close_button.show()
            self.add_action_widget(close_button, Gtk.ResponseType.CLOSE)
            # FIXME: doesn't seem to have any effect
            action.set_child_packing(
                close_button, False, True, 2, Gtk.PackType.START)

    def __response(self, bar, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            bar.hide()


class InternetRadio(Gtk.VBox, Browser, util.InstanceTracker):
    __gsignals__ = Browser.__gsignals__

    __stations = None
    __fav_stations = None
    __librarian = None

    __filter = None

    name = _("Internet Radio")
    accelerated_name = _("_Internet Radio")
    priority = 16
    headers = "title artist ~people grouping genre website ~format " \
        "channel-mode".split()

    TYPE, STOCK, KEY, NAME = range(4)
    TYPE_FILTER, TYPE_ALL, TYPE_FAV, TYPE_SEP, TYPE_NOCAT = range(5)
    STAR = ["artist", "title", "website", "genre", "comment"]

    @classmethod
    def _init(klass, library):
        klass.__librarian = library.librarian

        klass.__stations = SongLibrary("iradio-remote")
        klass.__stations.load(STATIONS_ALL)

        klass.__fav_stations = SongLibrary("iradio")
        klass.__fav_stations.load(STATIONS_FAV)

        klass.filters = GenreFilter()

    @classmethod
    def _destroy(klass):
        if klass.__stations.dirty:
            klass.__stations.save()
        klass.__stations.destroy()
        klass.__stations = None

        if klass.__fav_stations.dirty:
            klass.__fav_stations.save()
        klass.__fav_stations.destroy()
        klass.__fav_stations = None

        klass.__librarian = None

        klass.filters = None

    def __inhibit(self):
        self.view.get_selection().handler_block(self.__changed_sig)

    def __uninhibit(self):
        self.view.get_selection().handler_unblock(self.__changed_sig)

    def __destroy(self, *args):
        if not self.instances():
            self._destroy()

    def __init__(self, library):
        super(InternetRadio, self).__init__(spacing=12)

        if not self.instances():
            self._init(library)
        self._register_instance()

        self.connect('destroy', self.__destroy)

        completion = LibraryTagCompletion(self.__stations)
        self.accelerators = Gtk.AccelGroup()
        self.__searchbar = search = SearchBarBox(completion=completion,
                                                 accel_group=self.accelerators)
        search.connect('query-changed', self.__filter_changed)

        menu = Gtk.Menu()
        new_item = MenuItem(_(u"_New Station…"), Gtk.STOCK_ADD)
        new_item.connect('activate', self.__add)
        menu.append(new_item)
        update_item = MenuItem(_("_Update Stations"), Gtk.STOCK_REFRESH)
        update_item.connect('activate', self.__update)
        menu.append(update_item)
        menu.show_all()

        button = MenuButton(
            SymbolicIconImage("emblem-system", Gtk.IconSize.MENU),
            arrow=True)
        button.set_menu(menu)

        def focus(widget, *args):
            qltk.get_top_parent(widget).songlist.grab_focus()
        search.connect('focus-out', focus)

        # treeview
        scrolled_window = ScrolledWindow()
        scrolled_window.show()
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        self.view = view = AllTreeView()
        view.show()
        view.set_headers_visible(False)
        scrolled_window.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(view)
        model = Gtk.ListStore(int, str, str, str)

        model.append(row=[self.TYPE_ALL, Gtk.STOCK_DIRECTORY, "__all",
                          _("All Stations")])
        model.append(row=[self.TYPE_SEP, Gtk.STOCK_DIRECTORY, "", ""])
        #Translators: Favorite radio stations
        model.append(row=[self.TYPE_FAV, Gtk.STOCK_DIRECTORY, "__fav",
                          _("Favorites")])
        model.append(row=[self.TYPE_SEP, Gtk.STOCK_DIRECTORY, "", ""])

        filters = self.filters
        for text, k in sorted([(filters.text(k), k) for k in filters.keys()]):
            model.append(row=[self.TYPE_FILTER, Gtk.STOCK_FIND, k, text])

        model.append(row=[self.TYPE_NOCAT, Gtk.STOCK_DIRECTORY,
                          "nocat", _("No Category")])

        def separator(model, iter, data):
            return model[iter][self.TYPE] == self.TYPE_SEP
        view.set_row_separator_func(separator, None)

        def search_func(model, column, key, iter, data):
            return key.lower() not in model[iter][column].lower()
        view.set_search_column(self.NAME)
        view.set_search_equal_func(search_func, None)

        column = Gtk.TreeViewColumn("genres")
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)

        renderpb = Gtk.CellRendererPixbuf()
        renderpb.props.xpad = 3
        column.pack_start(renderpb, False)
        column.add_attribute(renderpb, "stock_id", self.STOCK)

        render = Gtk.CellRendererText()
        render.set_property('ellipsize', Pango.EllipsizeMode.END)
        view.append_column(column)
        column.pack_start(render, True)
        column.add_attribute(render, "text", self.NAME)

        view.set_model(model)

        # selection
        selection = view.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.__changed_sig = connect_destroy(selection, 'changed',
            util.DeferredSignal(lambda x: self.activate()))

        box = Gtk.HBox(spacing=6)
        box.pack_start(search, True, True, 0)
        box.pack_start(button, False, True, 0)
        self._searchbox = Alignment(box, left=0, right=6, top=6)
        self._searchbox.show_all()

        def qbar_response(infobar, response_id):
            if response_id == infobar.RESPONSE_LOAD:
                self.__update()

        self.qbar = QuestionBar()
        self.qbar.connect("response", qbar_response)
        if self._is_library_empty():
            self.qbar.show()

        pane = qltk.ConfigRHPaned("browsers", "internetradio_pos", 0.4)
        pane.show()
        pane.pack1(scrolled_window, resize=False, shrink=False)
        songbox = Gtk.VBox(spacing=6)
        songbox.pack_start(self._searchbox, False, True, 0)
        self._songpane_container = Gtk.VBox()
        self._songpane_container.show()
        songbox.pack_start(self._songpane_container, True, True, 0)
        songbox.pack_start(self.qbar, False, True, 0)
        songbox.show()
        pane.pack2(songbox, resize=True, shrink=False)
        self.pack_start(pane, True, True, 0)
        self.show()

    def _is_library_empty(self):
        return not len(self.__stations) and not len(self.__fav_stations)

    def pack(self, songpane):
        container = Gtk.VBox()
        container.add(self)
        self._songpane_container.add(songpane)
        return container

    def unpack(self, container, songpane):
        self._songpane_container.remove(songpane)
        container.remove(self)

    def __update(self, *args):
        self.qbar.hide()
        copool.add(download_taglist, self.__update_done,
                   cofuncid="radio-load", funcid="radio-load")

    def __update_done(self, stations):
        if not stations:
            print_w("Loading remote station list failed.")
            return

        # filter stations based on quality, listenercount
        def filter_stations(station):
            peak = station.get("~#listenerpeak", 0)
            if peak < 10:
                return False
            aac = "AAC" in station("~format")
            bitrate = station("~#bitrate", 50)
            if (aac and bitrate < 40) or (not aac and bitrate < 60):
                return False
            return True
        stations = filter(filter_stations, stations)

        # group them based on the title
        groups = {}
        for s in stations:
            key = s("~title~artist")
            groups.setdefault(key, []).append(s)

        # keep at most 2 URLs for each group
        stations = []
        for key, sub in groups.iteritems():
            sub.sort(key=lambda s: s.get("~#listenerpeak", 0), reverse=True)
            stations.extend(sub[:2])

        # only keep the ones in at least one category
        all_ = [self.filters.query(k) for k in self.filters.keys()]
        assert all_
        anycat_filter = reduce(lambda x, y: x | y, all_)
        stations = filter(anycat_filter.search, stations)

        # remove listenerpeak
        for s in stations:
            s.pop("~#listenerpeak", None)

        # update the libraries
        stations = dict(((s.key, s) for s in stations))
        # don't add ones that are in the fav list
        for fav in self.__fav_stations.iterkeys():
            stations.pop(fav, None)

        # separate
        o, n = set(self.__stations.iterkeys()), set(stations)
        to_add, to_change, to_remove = n - o, o & n, o - n
        del o, n

        # migrate stats
        to_change = [stations.pop(k) for k in to_change]
        for new in to_change:
            old = self.__stations[new.key]
            # clear everything except stats
            AudioFile.reload(old)
            # add new metadata except stats
            for k in (x for x in new.iterkeys() if x not in MIGRATE):
                old[k] = new[k]

        to_add = [stations.pop(k) for k in to_add]
        to_remove = [self.__stations[k] for k in to_remove]

        self.__stations.remove(to_remove)
        self.__stations.changed(to_change)
        self.__stations.add(to_add)

    def __filter_changed(self, bar, text, restore=False):
        self.__filter = Query(text, self.STAR)

        if not restore:
            self.activate()

    def __get_selected_libraries(self):
        """Returns the libraries to search in depending on the
        filter selection"""

        selection = self.view.get_selection()
        model, rows = selection.get_selected_rows()
        types = [model[row][self.TYPE] for row in rows]
        libs = [self.__fav_stations]
        if types != [self.TYPE_FAV]:
            libs.append(self.__stations)

        return libs

    def __get_selection_filter(self):
        """Retuns a filter object for the current selection or None
        if nothing should be filtered"""

        selection = self.view.get_selection()
        model, rows = selection.get_selected_rows()

        filter_ = None
        for row in rows:
            type_ = model[row][self.TYPE]
            if type_ == self.TYPE_FILTER:
                key = model[row][self.KEY]
                current_filter = self.filters.query(key)
                if current_filter:
                    if filter_:
                        filter_ |= current_filter
                    else:
                        filter_ = current_filter
            elif type_ == self.TYPE_NOCAT:
                # if notcat is selected, combine all filters, negate and merge
                all_ = [self.filters.query(k) for k in self.filters.keys()]
                nocat_filter = all_ and -reduce(lambda x, y: x | y, all_)
                if nocat_filter:
                    if filter_:
                        filter_ |= nocat_filter
                    else:
                        filter_ = nocat_filter
            elif type_ == self.TYPE_ALL:
                filter_ = None
                break

        return filter_

    def __add_fav(self, songs):
        songs = [s for s in songs if s in self.__stations]
        type(self).__librarian.move(
            songs, self.__stations, self.__fav_stations)

    def __remove_fav(self, songs):
        songs = [s for s in songs if s in self.__fav_stations]
        type(self).__librarian.move(
            songs, self.__fav_stations, self.__stations)

    def __add(self, button):
        parent = qltk.get_top_parent(self)
        uri = (AddNewStation(parent).run(clipboard=True) or "").strip()
        if uri != "":
            self.__add_station(uri)

    def __add_station(self, uri):
        irfs = add_station(uri)

        if not irfs:
            qltk.ErrorMessage(
                None, _("No stations found"),
                _("No Internet radio stations were found at %s.") %
                util.escape(uri)).run()
            return

        irfs = filter(lambda station: station not in self.__fav_stations, irfs)
        if not irfs:
            qltk.WarningMessage(
                None, _("Unable to add station"),
                _("All stations listed are already in your library.")).run()

        if irfs:
            self.__fav_stations.add(irfs)

    def Menu(self, songs, library, items):
        in_fav = False
        in_all = False
        for song in songs:
            if song in self.__fav_stations:
                in_fav = True
            elif song in self.__stations:
                in_all = True
            if in_fav and in_all:
                break

        iradio_items = []
        button = MenuItem(_("Add to Favorites"), Gtk.STOCK_ADD)
        button.set_sensitive(in_all)
        connect_obj(button, 'activate', self.__add_fav, songs)
        iradio_items.append(button)
        button = MenuItem(_("Remove from Favorites"), Gtk.STOCK_REMOVE)
        button.set_sensitive(in_fav)
        connect_obj(button, 'activate', self.__remove_fav, songs)
        iradio_items.append(button)

        items.append(iradio_items)
        menu = SongsMenu(self.__librarian, songs, playlists=False, remove=True,
                         queue=False, devices=False, items=items)
        return menu

    def restore(self):
        text = config.get("browsers", "query_text").decode("utf-8")
        self.__searchbar.set_text(text)
        if Query.is_parsable(text):
            self.__filter_changed(self.__searchbar, text, restore=True)

        keys = config.get("browsers", "radio").splitlines()

        def select_func(row):
            return row[self.TYPE] != self.TYPE_SEP and row[self.KEY] in keys

        self.__inhibit()
        view = self.view
        if not view.select_by_func(select_func):
            for row in view.get_model():
                if row[self.TYPE] == self.TYPE_FAV:
                    view.set_cursor(row.path)
                    break
        self.__uninhibit()

    def __get_filter(self):
        filter_ = self.__get_selection_filter()
        text_filter = self.__filter or Query("")

        if filter_:
            filter_ &= text_filter
        else:
            filter_ = text_filter

        return filter_

    def can_filter_text(self):
        return True

    def filter_text(self, text):
        self.__searchbar.set_text(text)
        if Query.is_parsable(text):
            self.__filter_changed(self.__searchbar, text)
            self.activate()

    def activate(self):
        filter_ = self.__get_filter()
        libs = self.__get_selected_libraries()
        songs = filter_.filter(itertools.chain(*libs))
        self.songs_selected(songs)

    def active_filter(self, song):
        for lib in self.__get_selected_libraries():
            if song in lib:
                break
        else:
            return False

        filter_ = self.__get_filter()

        if filter_:
            return filter_.search(song)
        return True

    def save(self):
        text = self.__searchbar.get_text().encode("utf-8")
        config.set("browsers", "query_text", text)

        selection = self.view.get_selection()
        model, rows = selection.get_selected_rows()
        names = filter(None, [model[row][self.KEY] for row in rows])
        config.set("browsers", "radio", "\n".join(names))

    def scroll(self, song):
        # nothing we care about
        if song not in self.__stations and song not in self.__fav_stations:
            return

        path = None
        for row in self.view.get_model():
            if row[self.TYPE] == self.TYPE_FILTER:
                if self.filters.query(row[self.KEY]).search(song):
                    path = row.path
                    break
        else:
            # in case nothing matches, select all
            path = (0,)

        self.view.set_cursor(path)
        self.view.scroll_to_cell(path, use_align=True, row_align=0.5)

    def statusbar(self, i):
        return ngettext("%(count)d station", "%(count)d stations", i)


from quodlibet import app
if not app.player or app.player.can_play_uri("http://"):
    browsers = [InternetRadio]
else:
    browsers = []
