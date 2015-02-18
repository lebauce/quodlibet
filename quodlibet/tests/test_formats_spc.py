# -*- coding: utf-8 -*-
# Copyright 2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

from tests import TestCase, DATA_DIR
from quodlibet.formats.spc import SPCFile


class TSPCFile(TestCase):
    def setUp(self):
        self.song = SPCFile(os.path.join(DATA_DIR, 'test.spc'))

    def test_tags(self):
        tags = {
            "title": "Game Select",
            "artist": "Koji Kondo",
            "album": "Super Mario All-Stars",
            "dumper": "Datschge",
        }

        for k, v in tags.items():
            self.failUnlessEqual(self.song[k], v)

    def test_length(self):
        self.failUnlessEqual(self.song("~#length"), 25)

    def test_write(self):
        self.song.write()

    def test_can_change(self):
        self.failUnless(self.song.can_change("title"))

    def test_invalid(self):
        path = os.path.join(DATA_DIR, 'empty.xm')
        self.failUnless(os.path.exists(path))
        self.failUnlessRaises(Exception, SPCFile, path)
