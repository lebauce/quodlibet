import gtk
from tests import add, TestCase
from qltk.count import CountManager
from qltk.watcher import SongWatcher
from formats._audio import AudioFile as AF

class TCountManager(TestCase):
    def setUp(self):
        self.w = SongWatcher()
        self.s1 = AF({"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10})
        self.s2 = AF({"~#playcount": 0, "~#skipcount": 0, "~#lastplayed": 10})
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

add(TCountManager)
