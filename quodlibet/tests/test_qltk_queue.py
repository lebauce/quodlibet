from tests import TestCase

from gi.repository import Gtk

from quodlibet.player.nullbe import NullPlayer
from quodlibet.qltk.queue import QueueExpander, PlaybackStatusIcon
from quodlibet.library import SongLibrary
import quodlibet.config


class TQueueExpander(TestCase):
    def setUp(self):
        quodlibet.config.init()
        player = NullPlayer()
        self.queue = QueueExpander(Gtk.CheckMenuItem(), SongLibrary(), player)

    def test_ctr(self):
        pass

    def test_status_icon(self):
        widget = PlaybackStatusIcon()
        widget.play()
        widget.stop()
        widget.pause()
        widget.pause()

    def tearDown(self):
        self.queue.destroy()
        quodlibet.config.quit()
