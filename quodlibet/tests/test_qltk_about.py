# -*- coding: utf-8 -*-
from tests import TestCase

from quodlibet.qltk.about import AboutQuodLibet, AboutExFalso
from quodlibet.player.nullbe import NullPlayer


class TAboutQuodLibet(TestCase):
    def test_ctr(self):
        AboutQuodLibet(None, NullPlayer()).destroy()

    def test_ef(self):
        AboutExFalso(None, NullPlayer()).destroy()
