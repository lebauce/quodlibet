# Copyright 2010 Steven Robertson
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import shelve
import urllib
import urllib2
import time
from datetime import date
from threading import Thread

from gi.repository import Gtk, GLib

from quodlibet import const, config, util, qltk
from quodlibet.qltk.entry import UndoEntry
from quodlibet.plugins.songsmenu import SongsMenuPlugin

try:
    import json
except ImportError:
    import simplejson as json

API_KEY = "f536cdadb4c2aec75ae15e2b719cb3a1"


def log(msg):
    print_d('[lastfmsync] %s' % msg)


def apicall(method, **kwargs):
    """Performs Last.fm API call."""
    real_args = {
            'api_key': API_KEY,
            'format': 'json',
            'method': method,
            }
    real_args.update(kwargs)
    url = ''.join(["http://ws.audioscrobbler.com/2.0/?",
                   urllib.urlencode(real_args)])
    log(url)
    uobj = urllib2.urlopen(url)
    resp = json.load(uobj)
    if 'error' in resp:
        errmsg = 'Last.fm API error: %s' % resp.get('message', '')
        log(errmsg)
        raise EnvironmentError(resp['error'], errmsg)
    return resp


def config_get(key, default=None):
    return config.get('plugins', 'lastfmsync_%s' % key, default)


class LastFMSyncCache(object):
    """Stores the Last.fm charts for a particular user."""
    def __init__(self, username):
        self.username = username
        self.lastupdated = None
        self.charts = {}
        self.songs = {}

    def update_charts(self, progress=None):
        """Updates Last.fm charts for the given user. Returns True if an
        update was attempted, False otherwise.

        progress is a callback func (msg, frac) that will be called to
        update a UI. 'frac' may be None to indicate no change should be made.
        If the function returns False, this thread will stop early."""

        def prog(msg, frac):
            if progress:
                if not progress(msg, frac):
                    # this gets caught later
                    raise ValueError()

        try:
            # Last.fm updates their charts weekly; we only poll for new
            # charts if it's been more than a day since the last poll
            now = time.time()
            if not self.lastupdated or self.lastupdated + (24 * 60 * 60) < now:
                prog("Updating chart list.", 0)
                resp = apicall('user.getweeklychartlist', user=self.username)
                charts = resp['weeklychartlist']['chart']
                for chart in charts:
                    # Charts keys are 2-tuple (from_timestamp, to_timestamp);
                    # values are whether we still need to fetch the chart
                    fro, to = map(lambda s: int(chart[s]), ('from', 'to'))
                    self.charts.setdefault((fro, to), True)
                self.lastupdated = now
            elif not filter(None, self.charts.values()):
                # No charts to fetch, no update scheduled.
                prog(_("Already up-to-date."), 1.)
                return False

            new_charts = filter(lambda k: self.charts[k], self.charts.keys())

            for idx, (fro, to) in enumerate(sorted(new_charts)):
                chart_week = date.fromtimestamp(fro).isoformat()
                prog(_("Fetching chart for week of %s.") % chart_week,
                     (idx + 1.) / (len(new_charts) + 2.))
                args = {'user': self.username, 'from': fro, 'to': to}
                try:
                    resp = apicall('user.getweeklytrackchart', **args)
                except urllib2.HTTPError, err:
                    msg = "HTTP error %d, retrying in %d seconds."
                    log(msg % (err.code, 15))
                    for i in range(15, 0, -1):
                        time.sleep(1)
                        prog(msg % (err.code, i), None)
                    resp = apicall('user.getweeklytrackchart', **args)
                try:
                    tracks = resp['weeklytrackchart']['track']
                except KeyError:
                    tracks = []
                # Delightfully, the API JSON frontend unboxes 1-element lists.
                if isinstance(tracks, dict):
                    tracks = [tracks]
                for track in tracks:
                    self._update_stats(track, fro, to)
                self.charts[(fro, to)] = False
            prog(_("Sync complete."), 1.)
        except ValueError:
            # this is probably from prog()
            pass
        except Exception:
            util.print_exc()
            prog(_("Error during sync"), None)
            return False

        return True

    def _update_stats(self, track, chart_fro, chart_to):
        """Updates a single track's stats. 'track' is as returned by API;
        'chart_fro' and 'chart_to' are the chart's timestamp range."""

        # we try track mbid, (artist mbid, name), (artist name, name) as keys
        keys = []
        if track['mbid']:
            keys.append(track['mbid'])
        for artist in (track['artist']['mbid'], track['artist']['#text']):
            if artist:
                keys.append((artist.lower(), track['name'].lower()))

        stats = filter(None, map(self.songs.get, keys))
        if stats:
            # Not sure if last.fm ever changes their tag values, but this
            # should map all changed values to the same object correctly
            plays = max(map(lambda d: d.get('playcount', 0), stats))
            last = max(map(lambda d: d.get('lastplayed', 0), stats))
            added = max(map(lambda d: d.get('added', chart_to), stats))
            stats = stats[0]
            stats.update(
                    {'playcount': plays, 'lastplayed': last, 'added': added})
        else:
            stats = {'playcount': 0, 'lastplayed': 0, 'added': chart_to}

        stats['playcount'] = stats['playcount'] + int(track['playcount'])
        stats['lastplayed'] = max(stats['lastplayed'], chart_fro)
        stats['added'] = min(stats['added'], chart_to)

        for key in keys:
            self.songs[key] = stats

    def update_songs(self, songs):
        """Updates each SongFile in songs from the cache."""
        for song in songs:
            keys = []
            if 'musicbrainz_trackid' in song:
                keys.append(song['musicbrainz_trackid'].lower())
            if 'musiscbrainz_artistid' in song:
                keys.append((song['musicbrainz_artistid'].lower(),
                            song.get('title', '').lower()))
            keys.append((song.get('artist', '').lower(),
                         song.get('title', '').lower()))
            stats = filter(None, map(self.songs.get, keys))
            if not stats:
                continue
            stats = stats[0]

            playcount = max(song.get('~#playcount', 0), stats['playcount'])
            if playcount != 0:
                song['~#playcount'] = playcount
            lastplayed = max(song.get('~#lastplayed', 0), stats['lastplayed'])
            if lastplayed != 0:
                song['~#lastplayed'] = lastplayed
            song['~#added'] = min(song['~#added'], stats['added'])


class LastFMSyncWindow(Gtk.Dialog):
    def __init__(self, parent):
        super(LastFMSyncWindow, self).__init__(
                _("Last.fm Sync"), parent, buttons=(
                    Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT))
        self.set_border_width(5)
        self.set_default_size(300, 100)

        vbox = Gtk.VBox()
        vbox.set_spacing(12)

        self.progbar = Gtk.ProgressBar()
        vbox.pack_start(self.progbar, False, True, 0)
        self.status = Gtk.Label(label="")
        vbox.pack_start(self.status, True, True, 0)
        self.get_content_area().pack_start(vbox, True, True, 0)

        self.set_response_sensitive(Gtk.ResponseType.ACCEPT, False)
        self.show_all()

    def progress(self, message, fraction):
        self.status.set_text(message)
        if fraction is not None:
            self.progbar.set_fraction(fraction)
            self.progbar.set_text("%2.1f%%" % (fraction * 100))
            if fraction == 1:
                self.set_response_sensitive(Gtk.ResponseType.ACCEPT, True)


class LastFMSync(SongsMenuPlugin):
    PLUGIN_ID = "Last.fm Sync"
    PLUGIN_NAME = _("Last.fm Sync")
    PLUGIN_DESC = ("Update your library's statistics from your "
                   "Last.fm profile.")
    PLUGIN_ICON = 'gtk-refresh'
    PLUGIN_VERSION = '0.1'

    CACHE_PATH = os.path.join(const.USERDIR, "lastfmsync.db")

    def runner(self, cache):
        changed = True
        try:
            changed = cache.update_charts(self.progress)
        except:
            pass
        if changed:
            self.cache_shelf[cache.username] = cache
        self.cache_shelf.close()

    def progress(self, msg, frac):
        if self.running:
            GLib.idle_add(self.dialog.progress, msg, frac)
            return True
        else:
            return False

    def plugin_songs(self, songs):
        self.cache_shelf = shelve.open(self.CACHE_PATH)
        user = config_get('username', '')
        try:
            cache = self.cache_shelf.setdefault(user, LastFMSyncCache(user))
        except Exception:
            # unpickle can fail in many ways. this is just cache, so ignore
            cache = self.cache_shelf[user] = LastFMSyncCache(user)

        self.dialog = LastFMSyncWindow(self.plugin_window)
        self.running = True
        thread = Thread(target=self.runner, args=(cache,))
        thread.daemon = True
        thread.start()
        resp = self.dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            cache.update_songs(songs)
        self.running = False
        self.dialog.destroy()

    @classmethod
    def PluginPreferences(klass, win):
        def entry_changed(entry):
            config.set('plugins', 'lastfmsync_username', entry.get_text())

        label = Gtk.Label(label=_("_Username:"), use_underline=True)
        entry = UndoEntry()
        entry.set_text(config_get('username', ''))
        entry.connect('changed', entry_changed)
        label.set_mnemonic_widget(entry)

        hbox = Gtk.HBox()
        hbox.set_spacing(6)
        hbox.pack_start(label, False, True, 0)
        hbox.pack_start(entry, True, True, 0)

        return qltk.Frame(_("Account"), child=hbox)
