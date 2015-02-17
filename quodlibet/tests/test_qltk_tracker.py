# -*- coding: utf-8 -*-
import os

from tests import TestCase

from gi.repository import Gtk

from quodlibet import config
from quodlibet import const
from quodlibet.formats._audio import AudioFile
from quodlibet.player.nullbe import NullPlayer
from quodlibet.qltk.tracker import SongTracker, FSInterface
from quodlibet.library import SongLibrary


class TSongTracker(TestCase):
    def setUp(self):
        config.init()
        self.p = NullPlayer()
        self.w = SongLibrary()
        self.s1 = AudioFile(
            {"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10,
             "~filename": "foo", "~#length": 1.5})
        self.s2 = AudioFile(
            {"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10,
             "~filename": "foo", "~#length": 1.5})
        self.cm = SongTracker(self.w, self.p, self)
        self.current = None

    def do(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def test_destroy(self):
        self.cm.destroy()

    def test_play(self):
        import time
        # Allow at least 2 second to elapse to simulate playing
        self.p.song = self.s1
        self.p.paused = False
        time.sleep(2)
        self.do()
        self.p.emit('song-ended', self.s1, False)
        self.do()
        t = time.time()
        self.assertEquals(self.s1["~#playcount"], 1)
        self.assertEquals(self.s1["~#skipcount"], 0)
        self.failUnless(t - self.s1["~#lastplayed"] <= 1)

    def test_skip(self):
        self.p.emit('song-ended', self.s1, True)
        self.do()
        self.assertEquals(self.s1["~#playcount"], 0)
        self.assertEquals(self.s1["~#skipcount"], 1)
        self.failUnless(self.s1["~#lastplayed"], 10)

    def test_error(self):
        self.current = self.p.song = self.s1
        self.p._error('Test error')
        self.do()
        self.assertEquals(self.s1["~#playcount"], 0)
        self.assertEquals(self.s1["~#skipcount"], 0)
        self.failUnless(self.s1["~#lastplayed"], 10)

    def test_restart(self):
        self.current = self.s1
        self.p.emit('song-ended', self.s1, True)
        self.do()
        self.assertEquals(self.s1["~#playcount"], 0)
        self.assertEquals(self.s1["~#skipcount"], 0)

    def tearDown(self):
        self.w.destroy()
        config.quit()


class TFSInterface(TestCase):
    def setUp(self):
        self.p = NullPlayer()
        self.fs = FSInterface(self.p)

    def do(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def test_init(self):
        self.do()
        self.failIf(os.path.exists(const.CURRENT))

    def test_start(self):
        self.p.emit('song_started', AudioFile({"woo": "bar", "~#length": 10}))
        self.do()
        self.failUnless("woo=bar\n" in file(const.CURRENT).read())

    def test_song_ended(self):
        self.p.emit('song-started', AudioFile({"woo": "bar", "~#length": 10}))
        self.do()
        self.p.emit('song-ended', {}, False)
        self.do()
        self.failIf(os.path.exists(const.CURRENT))

    def tearDown(self):
        self.p.destroy()
        try:
            os.unlink(const.CURRENT)
        except EnvironmentError:
            pass
