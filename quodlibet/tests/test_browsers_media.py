# -*- coding: utf-8 -*-
# Copyright 2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from tests import TestCase

from quodlibet import config
from quodlibet.browsers.media import *
from quodlibet.library import SongLibrary


class TMediaBrowser(TestCase):

    def setUp(self):
        config.init()

    def tearDown(self):
        config.quit()

    def test_init(self):
        library = SongLibrary()
        MediaDevices(library).destroy()

    def test_property(self):
        class FakeDevice(dict):
            block_device = "Fake"
            mountpoint = "/"
            Properties = lambda *x: []
        fake = FakeDevice({"name": "Foo"})

        DeviceProperties(None, fake).destroy()
