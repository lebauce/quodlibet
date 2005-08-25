from unittest import TestCase
from tests import registerCase
import os, gtk, const
from browsers.search import EmptyBar, SearchBar
from properties import VALIDATERS
from efwidgets import DirectoryTree

from widgets import PlayList, FileChooser, CountManager, FSInterface, PluginWindow, PreferencesWindow
import qltk

class TFSInterface(TestCase):
    from formats.audio import AudioFile as AF
    def setUp(self):
        self.w = qltk.SongWatcher()
        self.fs = FSInterface(self.w)

    def do(self):
        while gtk.events_pending(): gtk.main_iteration()

    def test_init(self):
        self.do()
        self.failUnless(os.path.exists(const.PAUSED))
        self.failIf(os.path.exists(const.CURRENT))

    def test_start(self):
        self.w.song_started(self.AF({"woo": "bar", "~#length": 10}))
        self.do()
        self.failUnless("woo=bar\n" in file(const.CURRENT).read())

    def test_pause(self):
        for b in [True, False, True, True, False, True]:
            self.w.set_paused(b); self.do()
            self.failUnlessEqual(os.path.exists(const.PAUSED), b)

    def test_song_ended(self):
        self.w.song_started(self.AF({"woo": "bar", "~#length": 10}))
        self.do()
        self.w.song_ended({}, False)
        self.do()
        self.failIf(os.path.exists(const.CURRENT))

    def tearDown(self):
        self.w.destroy()
        try: os.unlink(const.PAUSED)
        except EnvironmentError: pass
        try: os.unlink(const.CURRENT)
        except EnvironmentError: pass

registerCase(TFSInterface)

class TFileChooser(TestCase):
    def test_init_nodir(self):
        f = FileChooser(None, "A file chooser")
        self.assertEqual(f.get_current_folder(), os.path.realpath("."))
        f.destroy()

    def test_init_dir(self):
        f = FileChooser(None, "A file chooser", "/home")
        self.assertEqual(f.get_current_folder(), "/home")
        f.destroy()

registerCase(TFileChooser)

class TCountManager(TestCase):
    def setUp(self):
        self.w = qltk.SongWatcher()
        self.s1 = {"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10}
        self.s2 = {"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10}
        self.cm = CountManager(self.w, self)
        self.current = None

    def do(self):
        while gtk.events_pending(): gtk.main_iteration()

    def test_play(self):
        self.w.song_ended(self.s1, False)
        self.do()
        import time; t = time.time()
        self.assertEquals(self.s1["~#playcount"], 1)
        self.assertEquals(self.s1["~#skipcount"], 0)
        self.failUnless(t - self.s1["~#lastplayed"] <= 1)

    def test_skip(self):
        self.w.song_ended(self.s1, True)
        self.do()
        self.assertEquals(self.s1["~#playcount"], 0)
        self.assertEquals(self.s1["~#skipcount"], 1)
        self.failUnless(self.s1["~#lastplayed"], 10)

    def test_restart(self):
        self.current = self.s1
        self.w.song_ended(self.s1, True)
        self.do()
        self.assertEquals(self.s1["~#playcount"], 0)
        self.assertEquals(self.s1["~#skipcount"], 0)

    def tearDown(self):
        self.w.destroy()

registerCase(TCountManager)

class TPluginWindow(TestCase):
    def test_create(self):
        from plugins import PluginManager
        from widgets import SongList
        SongList.pm = PluginManager(qltk.SongWatcher(), [])
        w = PluginWindow(None)
        w.destroy()
        del(SongList.pm)
        os.unlink(const.CONFIG)

registerCase(TPluginWindow)

class TPreferencesWindow(TestCase):
    def test_create(self):
        w = PreferencesWindow(None)
        w.destroy()
        os.unlink(const.CONFIG)

registerCase(TPreferencesWindow)

class TestDirTree(TestCase):
    def test_initial(self):
        for path in ["/", "/home", os.environ["HOME"], "/usr/bin"]:
            dirlist = DirectoryTree(path)
            model, rows = dirlist.get_selection().get_selected_rows()
            selected = [model[row][0] for row in rows]
            dirlist.destroy()
            self.failUnlessEqual([path], selected)

    def test_bad_initial(self):
        for path in ["/", os.environ["HOME"]]:
            newpath = os.path.join(path, "bin/file/does/not/exist")
            dirlist = DirectoryTree(newpath)
            model, rows = dirlist.get_selection().get_selected_rows()
            selected = [model[row][0] for row in rows]
            dirlist.destroy()
            self.failUnlessEqual([path], selected)

class SongWatcher(TestCase):
    def setUp(self):
        self.watcher = qltk.SongWatcher()

    def __changed(self, watcher, song, expected):
        self.failUnlessEqual(expected.pop(0), song)

    def __test_signal(self, sig):
        expected = range(5)
        self.watcher.connect(sig, self.__changed, expected)
        map(getattr(self.watcher, sig), range(5))
        while gtk.events_pending(): gtk.main_iteration()
        self.failIf(expected)

    def test_changed(self): self.__test_signal('changed')
    def test_removed(self): self.__test_signal('removed')
    def test_missing(self): self.__test_signal('missing')

    def __test_started_cb(self, watcher, song):
        self.failUnlessEqual(watcher.time[0], 0)
        self.failUnlessEqual(watcher.song, song)
        if song: self.failUnlessEqual(watcher.time[1], song["~#length"]*1000)
        else: self.failUnlessEqual(watcher.time[1], 1)
        self.__count += 1

    def test_started(self):
        self.__count = 0
        self.watcher.connect('song-started', self.__test_started_cb)
        self.watcher.song_started(None)
        while gtk.events_pending(): gtk.main_iteration()
        self.watcher.song_started({"~#length": 10})
        while gtk.events_pending(): gtk.main_iteration()
        self.watcher.song_started(None)
        while gtk.events_pending(): gtk.main_iteration()
        self.watcher.song_started({"~#length": 12})
        while gtk.events_pending(): gtk.main_iteration()
        self.failUnlessEqual(4, self.__count)

    def __refresh_cb(self, watcher): self.__refreshed = True
    def test_refresh(self):
        self.__refreshed = False
        self.watcher.connect('refresh', self.__refresh_cb)
        self.watcher.refresh()
        while gtk.events_pending(): gtk.main_iteration()
        self.failUnless(self.__refreshed)

    def __ended_cb(self, watcher, song, stopped):
        if song & 1: self.failIf(stopped)
        else: self.failUnless(stopped)
        watcher.song = song

    def test_ended(self):
        self.watcher.connect('song-ended', self.__ended_cb)
        self.watcher.song_ended(1, False)
        self.watcher.song_ended(2, True)
        self.watcher.song_ended(3, False)
        self.watcher.song_ended(4, True)
        while gtk.events_pending(): gtk.main_iteration()
        self.failUnlessEqual(4, self.watcher.song)

    def __paused_cb(self, watcher): self.__paused += 1
    def __unpaused_cb(self, watcher): self.__unpaused += 1
    def test_paused(self):
        self.__paused = 0
        self.__unpaused = 0
        self.watcher.connect('paused', self.__paused_cb)
        self.watcher.connect('unpaused', self.__unpaused_cb)
        for i in range(4): self.watcher.set_paused(True)
        for i in range(6): self.watcher.set_paused(False)
        while gtk.events_pending(): gtk.main_iteration()
        self.failUnlessEqual(4, self.__paused)
        self.failUnlessEqual(6, self.__unpaused)

    def tearDown(self):
        self.watcher.destroy()

class ValidaterTests(TestCase):
    def validate(self, key, values):
        for val in values: self.failUnless(VALIDATERS[key][0](val))
    def invalidate(self, key, values):
        for val in values: self.failIf(VALIDATERS[key][0](val))

    def test_date_valid(self):
        self.validate("date", ["2002-10-12", "2000", "1200-10", "0000-00-00"])
    def test_date_invalid(self):
        self.invalidate(
            "date", ["200", "date-or-no", "", "2000-00-00-00"])

    def test_gain_valid(self):
        gains = ["2.12 dB", "99. dB", "-1.11 dB", "-0.99 dB", "0 dB"]
        self.validate('replaygain_track_gain', gains)
        self.validate('replaygain_album_gain', gains)
    def test_gain_invalid(self):
        gains = ["12.12", "hooray", "", "dB dB"]
        self.invalidate('replaygain_track_gain', gains)
        self.invalidate('replaygain_album_gain', gains)

    def test_peak_valid(self):
        peaks = ["12.12", "100", "0.999", "123.145"]
        self.validate('replaygain_track_peak', peaks)
        self.validate('replaygain_album_peak', peaks)
    def test_peak_invalid(self):
        peaks = ["", "100 dB", "woooo", "12.12.12"]
        self.invalidate('replaygain_track_peak', peaks)
        self.invalidate('replaygain_album_peak', peaks)

registerCase(TestDirTree)
registerCase(SongWatcher)
registerCase(ValidaterTests)
