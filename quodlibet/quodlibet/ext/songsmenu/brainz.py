# -*- coding: utf-8 -*-
# brainz.py - Quod Libet plugin to tag files from MusicBrainz automatically
# Copyright 2005-2010   Joshua Kwan <joshk@triplehelix.org>,
#                       Michael Ball <michael.ball@gmail.com>,
#                       Steven Robertson <steven@strobe.cc>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import re
import threading
import time

from gi.repository import Gtk, GObject, Pango, GLib

try:
    from musicbrainz2 import webservice as ws
    from musicbrainz2.utils import extractUuid
except ImportError as e:
    from quodlibet import plugins
    raise (plugins.MissingModulePluginException("musicbrainz2") if
           hasattr(plugins, "MissingModulePluginException") else e)

from quodlibet import config, util
from quodlibet.qltk.ccb import ConfigCheckButton
from quodlibet.plugins.songsmenu import SongsMenuPlugin
from quodlibet.qltk.views import HintedTreeView, MultiDragTreeView

VARIOUS_ARTISTS_ARTISTID = '89ad4ac3-39f7-470e-963a-56509c546377'


def get_artist(album):
    """Returns a single artist likely to be the MB AlbumArtist, or None."""
    for tag in ["albumartist", "artist", "performer"]:
        names = set()
        for song in album:
            for single in filter(None, song.get(tag, "").split("\n")):
                names.add(single)
        if len(names) == 1:
            return names.pop()
        elif len(names) > 1:
            return None
    return None


def get_trackcount(album):
    """Returns the track count, hammered into submission."""

    parts = []
    for song in album:
        parts.extend(song.get("tracknumber", "0").split("/"))

    max_count = len(album)
    for part in parts:
        try:
            tracks = int(part)
        except ValueError:
            continue
        max_count = max(max_count, tracks)

    return max_count


def config_get(key, default=''):
    return config.getboolean('plugins', 'brainz_' + key, default)


def dialog_get_widget_for_stockid(dialog, stockid):
    for child in dialog.get_action_area().get_children():
        if child.get_label() == stockid:
            return child


class ResultTreeView(HintedTreeView, MultiDragTreeView):
    """The result treeview. The model only stores local tracks; info about
    remote results is pulled from self.remote_album."""

    def __name_datafunc(self, col, cell, model, itr, data):
        song = model[itr][0]
        if song:
            cell.set_property('text', os.path.basename(song.get("~filename")))
        else:
            cell.set_property('text', '')

    def __track_datafunc(self, col, cell, model, itr, data):
        idx = model.get_path(itr)[0]
        if idx >= len(self.remote_album):
            cell.set_property('text', '')
        else:
            cell.set_property('text', str(idx + 1))

    def __title_datafunc(self, col, cell, model, itr, data):
        idx = model.get_path(itr)[0]
        if idx >= len(self.remote_album):
            cell.set_property('text', '')
        else:
            cell.set_property('text', self.remote_album[idx].title)

    def __artist_datafunc(self, col, cell, model, itr, data):
        idx = model.get_path(itr)[0]
        if idx >= len(self.remote_album) or not self.remote_album[idx].artist:
            cell.set_property('text', '')
        else:
            cell.set_property('text', self.remote_album[idx].artist.name)

    def __init__(self, album):
        self.album = album
        self.remote_album = []
        self.model = Gtk.ListStore(object)
        for song in album:
            self.model.append([song])

        super(ResultTreeView, self).__init__(self.model)
        self.set_headers_clickable(True)
        self.set_rules_hint(True)
        self.set_reorderable(True)
        self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        cols = [
                (_('Filename'), self.__name_datafunc, True),
                (_('Track'), self.__track_datafunc, False),
                (_('Title'), self.__title_datafunc, True),
                (_('Artist'), self.__artist_datafunc, True),
            ]

        for title, func, resize in cols:
            render = Gtk.CellRendererText()
            render.set_property('ellipsize', Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, render)
            col.set_cell_data_func(render, func)
            col.set_resizable(resize)
            col.set_expand(resize)
            self.append_column(col)

    def update_remote_album(self, remote_album):
        """Updates the TreeView, handling results with a different number of
        tracks than the album being tagged."""
        for i in range(len(self.model), len(remote_album)):
            self.model.append((None, ))
        for i in range(len(self.model), len(remote_album), -1):
            if self.model[-1][0] is not None:
                break
            itr = self.model.get_iter_from_string(str(len(self.model) - 1))
            self.model.remove(itr)
        self.remote_album = remote_album
        has_artists = bool(filter(lambda t: t.artist, remote_album))
        col = self.get_column(3)
        # sometimes gets called after the treeview is already gone
        if not col:
            return
        col.set_visible(has_artists)
        self.columns_autosize()
        self.queue_draw()


class ResultComboBox(Gtk.ComboBox):
    """Formatted picker for different Result entries."""

    def __init__(self, model):
        super(ResultComboBox, self).__init__(model=model)
        render = Gtk.CellRendererText()
        render.set_fixed_height_from_font(2)

        def celldata(layout, cell, model, iter, data):
            release = model[iter][0]
            if not release:
                return
            date = release.getEarliestReleaseDate()
            if date:
                date = '%s, ' % date
            else:
                date = ''
            markup = "<b>%s</b>\n%s - %s%s tracks" % (
                    util.escape(release.title),
                    util.escape(release.artist.name),
                    date, release.tracksCount)
            cell.set_property('markup', markup)
        self.pack_start(render, True)
        self.set_cell_data_func(render, celldata, None)


class ReleaseEventComboBox(Gtk.HBox):
    """A ComboBox for picking a release event."""

    def __init__(self):
        super(ReleaseEventComboBox, self).__init__()
        self.model = Gtk.ListStore(object, str)
        self.combo = Gtk.ComboBox(model=self.model)
        render = Gtk.CellRendererText()
        self.combo.pack_start(render, True)
        self.combo.add_attribute(render, "markup", 1)
        self.combo.set_sensitive(False)
        self.label = Gtk.Label(label=_("_Release:"), use_underline=True)
        self.label.set_use_underline(True)
        self.label.set_mnemonic_widget(self.combo)
        self.pack_start(self.label, False, True, 0)
        self.pack_start(self.combo, True, True, 0)

    def update(self, release):
        self.model.clear()
        events = release.getReleaseEvents()
        # The catalog number is the most important of these fields, as it's
        # the source for the 'labelid' tag, which we'll use until MB NGS is
        # up and running to deal with multi-disc albums properly. We sort to
        # find the earliest release with a catalog number.
        events.sort(key=lambda e: (bool(not e.getCatalogNumber()),
                                   e.getDate() or '9999-12-31'))
        for rel_event in events:
            text = '%s %s: <b>%s</b> <i>(%s)</i>' % (
                    rel_event.getDate() or '', rel_event.getLabel() or '',
                    rel_event.getCatalogNumber(), rel_event.getCountry())
            self.model.append((rel_event, text))
        if len(events) > 0:
            self.combo.set_active(0)
        self.combo.set_sensitive((len(events) > 0))
        text = ngettext("%d _release:", "%d _releases:", len(events))
        self.label.set_text(text % len(events))
        self.label.set_use_underline(True)

    def get_release_event(self):
        itr = self.combo.get_active_iter()
        if itr:
            return self.model[itr][0]
        else:
            return None


class QueryThread(object):
    """Daemon thread which does HTTP retries and avoids flooding."""
    def __init__(self):
        self.running = True
        self.queue = []
        thread = threading.Thread(target=self.__run)
        thread.daemon = True
        thread.start()

    def add(self, callback, func, *args, **kwargs):
        """Add a func to be evaluated in a background thread.
        Callback will be called with the result from the main thread."""
        self.queue.append((callback, func, args, kwargs))

    def stop(self):
        """Stop the background thread."""
        self.running = False

    def __run(self):
        while self.running:
            if self.queue:
                callback, func, args, kwargs = self.queue.pop(0)
                try:
                    res = func(*args, **kwargs)
                except:
                    time.sleep(2)
                    try:
                        res = func(*args, **kwargs)
                    except:
                        res = None

                def idle_check(cb, res):
                    if self.running:
                        cb(res)
                GLib.idle_add(idle_check, callback, res)
            time.sleep(1)


class SearchWindow(Gtk.Dialog):
    def __save(self, widget=None, response=None):
        """Writes values to Song objects."""
        self._qthread.stop()
        if response != Gtk.ResponseType.ACCEPT:
            self.destroy()
            return

        album = self.current_release
        shared = {}

        shared['album'] = album.title
        if config_get('split_disc', True):
            m = re.match(r'(.*) \(disc (.*?)\)$', album.title)
            if m:
                shared['album'] = m.group(1)
                disc = m.group(2).split(': ', 1)
                shared['discnumber'] = disc[0]
                if len(disc) > 1:
                    shared['discsubtitle'] = disc[1]

        relevt = self.release_combo.get_release_event()
        shared['date'] = relevt and relevt.getDate() or ''
        if shared['date'] and config_get('year_only', False):
            shared['date'] = shared['date'].split('-')[0]

        if config_get('labelid', True):
            if relevt and relevt.getCatalogNumber():
                shared['labelid'] = relevt.getCatalogNumber()

        if not album.isSingleArtistRelease():
            if (config_get('albumartist', True)
                and extractUuid(album.artist.id) != VARIOUS_ARTISTS_ARTISTID):
                shared['albumartist'] = album.artist.name
                if config_get('artist_sort', False) and \
                        album.artist.sortName != album.artist.name:
                    shared['albumartistsort'] = album.artist.sortName

        if config_get('standard', True):
            shared['musicbrainz_albumartistid'] = extractUuid(album.artist.id)
            shared['musicbrainz_albumid'] = extractUuid(album.id)

        for idx, (song, ) in enumerate(self.result_treeview.model):
            if song is None:
                continue
            song.update(shared)
            if idx >= len(album.tracks):
                continue
            track = album.tracks[idx]
            song['title'] = track.title
            song['tracknumber'] = '%d/%d' % (idx + 1,
                    max(len(album.tracks), len(self.result_treeview.model)))
            if config_get('standard', True):
                song['musicbrainz_trackid'] = extractUuid(track.id)
            if album.isSingleArtistRelease() or not track.artist:
                song['artist'] = album.artist.name
                if config_get('artist_sort', False) and \
                        album.artist.sortName != album.artist.name:
                    song['artistsort'] = album.artist.sortName
            else:
                song['artist'] = track.artist.name
                if config_get('artist_sort', False) and \
                        track.artist.sortName != track.artist.name:
                    song['artistsort'] = track.artist.sortName
                if config_get('standard', True):
                    song['musicbrainz_artistid'] = extractUuid(track.artist.id)
            if config_get('split_feat', False):
                feats = re.findall(r' \(feat\. (.*?)\)', track.title)
                if feats:
                    feat = []
                    for value in feats:
                        values = value.split(', ')
                        if len(values) > 1:
                            values += values.pop().split(' & ')
                        feat += values
                    song['performer'] = '\n'.join(feat)
                    song['title'] = re.sub(r' \(feat\. .*?\)', '', track.title)

        self.destroy()

    def __do_query(self, *args):
        """Search for album using the query text."""
        query = self.search_query.get_text()
        if not query:
            self.result_label.set_markup(_("<b>Please enter a query.</b>"))
            self.search_button.set_sensitive(True)
            return
        self.result_label.set_markup(_(u"<i>Searching…</i>"))
        filt = ws.ReleaseFilter(query=query)
        self._qthread.add(self.__process_results,
                         self._query.getReleases, filt)

    def __process_results(self, results):
        """Callback for search query completion."""
        self._resultlist.clear()
        self.search_button.set_sensitive(True)
        if results is None:
            self.result_label.set_text(_("Error encountered. Please retry."))
            self.search_button.set_sensitive(True)
            return
        for release in map(lambda r: r.release, results):
            self._resultlist.append((release, ))
        if len(results) > 0 and self.result_combo.get_active() == -1:
            self.result_label.set_markup(_(u"<i>Loading result…</i>"))
            self.result_combo.set_active(0)
        else:
            self.result_label.set_markup(_("No results found."))

    def __result_changed(self, combo):
        """Called when a release is chosen from the result combo."""
        idx = combo.get_active()
        if idx == -1:
            return
        rel_id = self._resultlist[idx][0].id
        if rel_id in self._releasecache:
            self.__update_results(self._releasecache[rel_id])
        else:
            self.result_label.set_markup(_(u"<i>Loading result…</i>"))
            inc = ws.ReleaseIncludes(
                    artist=True, releaseEvents=True, tracks=True)
            self._qthread.add(self.__update_result,
                    self._query.getReleaseById, rel_id, inc)

    def __update_result(self, release):
        """Callback for release detail download from result combo."""
        num_results = len(self._resultlist)
        text = ngettext("Found %d result.", "Found %d results.", num_results)
        self.result_label.set_text(text % num_results)
        # issue 973: search can return invalid (or removed) ReleaseIDs
        if release is None:
            return
        self._releasecache.setdefault(extractUuid(release.id), release)
        self.result_treeview.update_remote_album(release.tracks)
        self.current_release = release
        self.release_combo.update(release)
        save_button = dialog_get_widget_for_stockid(self, Gtk.STOCK_SAVE)
        save_button.set_sensitive(True)

    def __init__(self, parent, album, cache):
        self.album = album

        self._query = ws.Query()
        self._resultlist = Gtk.ListStore(GObject.TYPE_PYOBJECT)
        self._releasecache = cache
        self._qthread = QueryThread()
        self.current_release = None

        super(SearchWindow, self).__init__(_("MusicBrainz lookup"), buttons=(
                    Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT))
        self.set_default_size(650, 500)
        self.set_border_width(5)
        self.set_transient_for(parent)

        save_button = dialog_get_widget_for_stockid(self, Gtk.STOCK_SAVE)
        save_button.set_sensitive(False)

        vb = Gtk.VBox()
        vb.set_spacing(8)

        hb = Gtk.HBox()
        hb.set_spacing(8)
        sq = self.search_query = Gtk.Entry()
        sq.connect('activate', self.__do_query)

        alb = '"%s"' % album[0].comma("album").replace('"', '')
        art = get_artist(album)
        if art:
            alb = '%s AND artist:"%s"' % (alb, art.replace('"', ''))
        sq.set_text('%s AND tracks:%d' %
                (alb, get_trackcount(album)))

        lbl = Gtk.Label(label=_("_Query:"))
        lbl.set_use_underline(True)
        lbl.set_mnemonic_widget(sq)
        stb = self.search_button = Gtk.Button(_('S_earch'), use_underline=True)
        stb.connect('clicked', self.__do_query)
        hb.pack_start(lbl, False, True, 0)
        hb.pack_start(sq, True, True, 0)
        hb.pack_start(stb, False, True, 0)
        vb.pack_start(hb, False, True, 0)

        self.result_combo = ResultComboBox(self._resultlist)
        self.result_combo.connect('changed', self.__result_changed)
        vb.pack_start(self.result_combo, False, True, 0)

        rhb = Gtk.HBox()
        rl = Gtk.Label()
        rl.set_markup(_("Results <i>(drag to reorder)</i>"))
        rl.set_alignment(0, 0.5)
        rhb.pack_start(rl, False, True, 0)
        rl = self.result_label = Gtk.Label(label="")
        rhb.pack_end(rl, False, True, 0)
        vb.pack_start(rhb, False, True, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        rtv = self.result_treeview = ResultTreeView(self.album)
        rtv.set_border_width(8)
        sw.add(rtv)
        vb.pack_start(sw, True, True, 0)

        hb = Gtk.HBox()
        hb.set_spacing(8)
        self.release_combo = ReleaseEventComboBox()
        vb.pack_start(self.release_combo, False, True, 0)

        self.get_content_area().pack_start(vb, True, True, 0)
        self.connect('response', self.__save)

        stb.emit('clicked')
        self.get_child().show_all()


class MyBrainz(SongsMenuPlugin):
    PLUGIN_ID = "MusicBrainz lookup"
    PLUGIN_NAME = _("MusicBrainz Lookup")
    PLUGIN_ICON = Gtk.STOCK_CDROM
    PLUGIN_DESC = _('Re-tags an album based on a MusicBrainz search.')

    cache = {}

    def plugin_albums(self, albums):
        if not albums:
            return

        def win_finished_cb(widget, *args):
            if albums:
                start_processing(albums.pop(0))
            else:
                self.plugin_finish()

        def start_processing(disc):
            win = SearchWindow(
                self.plugin_window, disc, self.cache)
            win.connect("destroy", win_finished_cb)
            win.show()

        start_processing(albums.pop(0))

    @classmethod
    def PluginPreferences(self, win):
        items = [
            ('split_disc', _('Split _disc from album'), True),
            ('split_feat', _('Split _featured performers from track'), False),
            ('year_only', _('Only use year for "date" tag'), False),
            ('albumartist', _('Write "_albumartist" when needed'), True),
            ('artist_sort', _('Write sort tags for artist names'), False),
            ('standard', _('Write _standard MusicBrainz tags'), True),
            ('labelid',
                _('Write _labelid tag (fixes multi-disc albums)'), True),
        ]

        vb = Gtk.VBox()
        vb.set_spacing(8)

        for key, label, default in items:
            ccb = ConfigCheckButton(label, 'plugins', 'brainz_' + key)
            ccb.set_active(config_get(key, default))
            vb.pack_start(ccb, True, True, 0)

        return vb
