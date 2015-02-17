# -*- coding: utf-8 -*-
from tests import TestCase

from quodlibet.qltk.exfalsowindow import ExFalsoWindow
from quodlibet.library import SongLibrary
import quodlibet.config


class TExFalsoWindow(TestCase):
    def setUp(self):
        quodlibet.config.init()
        self.ef = ExFalsoWindow(SongLibrary())

    def test_nothing(self):
        self.failUnless(self.ef.get_child())

    def tearDown(self):
        self.ef.destroy()
        quodlibet.config.quit()
