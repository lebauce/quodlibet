# -*- coding: utf-8 -*-
from tests import TestCase

from gi.repository import Gtk

import quodlibet.browsers.search
import quodlibet.config

from quodlibet.browsers.search import SearchBar
from quodlibet.browsers.empty import EmptyBar
from quodlibet.formats._audio import AudioFile
from quodlibet.util.path import fsnative
from quodlibet.library import SongLibrary, SongLibrarian

# Don't sort yet, album_key makes it complicated...
SONGS = [AudioFile({
                "title": "one",
                "artist": "piman",
                "~filename": fsnative(u"/dev/null")}),
         AudioFile({
                "title": "two",
                "artist": "mu",
                "~filename": fsnative(u"/dev/zero")}),
         AudioFile({
                "title": "three",
                "artist": "boris",
                "~filename": fsnative(u"/bin/ls")}),
         AudioFile({
                "title": "four",
                "artist": "random",
                "album": "don't stop",
                "labelid": "65432-1",
                "~filename": fsnative(u"/dev/random")}),
         AudioFile({
                "title": "five",
                "artist": "shell",
                "album": "don't stop",
                "labelid": "12345-6",
                "~filename": fsnative(u"/dev/sh")})]


class TEmptyBar(TestCase):
    Bar = EmptyBar

    def setUp(self):
        quodlibet.config.init()
        quodlibet.browsers.search.library = SongLibrary()
        quodlibet.browsers.search.library.librarian = SongLibrarian()
        for af in SONGS:
            af.sanitize()
        quodlibet.browsers.search.library.add(SONGS)
        self.bar = self.Bar(quodlibet.browsers.search.library)
        self.bar.connect('songs-selected', self._expected)

    def _expected(self, bar, songs, sort):
        songs.sort()
        self.failUnlessEqual(self.expected, songs)
        self.expected = None

    def _do(self):
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.failUnless(self.expected is None)

    def test_can_filter(self):
        for key in ["foo", "title", "fake~key", "~woobar", "~#huh"]:
            self.failUnless(self.bar.can_filter(key))

    def test_empty_is_all(self):
        self.bar.filter_text("")
        self.expected = list(sorted(SONGS))
        self._do()

    def test_active_filter(self):
        self.assertTrue(self.bar.active_filter(SONGS[0]))
        self.bar.filter_text("this does not match any song")
        self.expected = []
        self.assertFalse(self.bar.active_filter(SONGS[0]))

    def test_filter(self):
        self.expected = [SONGS[1]]
        self.bar.filter("title", ["two"])

    def test_filter_again(self):
        self.expected = sorted(SONGS[3:5])
        self.bar.filter("album", ["don't stop"])

    def test_filter_notvalue(self):
        self.expected = sorted(SONGS[0:2])
        self.bar.filter("artist", ["notvalue", "mu", "piman"])

    def test_filter_none(self):
        self.expected = []
        self.bar.filter("title", ["not a value"])

    def test_filter_album_by_labelid(self):
        self.expected = [SONGS[3]]
        self.bar.filter("labelid", [("65432-1")])

    def test_filter_numeric(self):
        self.expected = list(sorted(SONGS))
        self.bar.filter("~#length", [0])

    def test_saverestore(self):
        self.bar.filter_text("title = %s" % SONGS[0]["title"])
        self.expected = [SONGS[0]]
        self._do()
        self.bar.save()
        self.bar.filter_text("")
        self.expected = list(sorted(SONGS))
        self._do()
        self.bar.restore()
        self.bar.activate()
        self.expected = [SONGS[0]]
        self._do()

    def tearDown(self):
        self.bar.destroy()
        quodlibet.browsers.search.library.destroy()
        quodlibet.config.quit()


class TSearchBar(TEmptyBar):
    Bar = SearchBar
