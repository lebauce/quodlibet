# -*- coding: utf-8 -*-
import sys
from tests import TestCase

from quodlibet import browsers
browsers.init()


class TBrowsers(TestCase):
    def test_presence(self):
        self.failUnless(browsers.empty)
        self.failUnless(browsers.search)
        self.failUnless(browsers.paned)
        self.failUnless(browsers.iradio)
        self.failUnless(browsers.audiofeeds)
        self.failUnless(browsers.albums)
        self.failUnless(browsers.playlists)
        self.failUnless(browsers.filesystem)

    def test_get(self):
        self.failUnless(browsers.get("EmptyBar") is browsers.empty.EmptyBar)
        self.failUnless(
            browsers.get("FileSystem") is browsers.filesystem.FileSystem)

    def test_get_invalid(self):
        self.failUnless(
            browsers.get("DoesNotExist") is browsers.empty.EmptyBar)

    def test_migrate(self):
        self.failUnless(
            sys.modules["browsers.audiofeeds"] is browsers.audiofeeds)
        self.failUnless(
            sys.modules["browsers.iradio"] is browsers.iradio)
