from tests import TestCase, add

from quodlibet.library import SongLibrary
from quodlibet.browsers.iradio import InternetRadio, IRFile
from quodlibet.player.nullbe import NullPlayer
import quodlibet.config

class TInternetRadio(TestCase):
    def setUp(self):
        quodlibet.config.init()
        self.bar = InternetRadio(SongLibrary(), NullPlayer())

    def test_can_filter(self):
        for key in ["foo", "title", "fake~key", "~woobar", "~#huh"]:
            self.failIf(self.bar.can_filter(key))

    def tearDown(self):
        self.bar.destroy()
        quodlibet.config.quit()
add(TInternetRadio)


class TIRFile(TestCase):
    def setUp(self):
        self.s = IRFile("http://foo.bar")

    def test_website(self):
        self.s["website"] = "abc"
        self.assertEqual(self.s.get("artist"), "abc")
        self.assertEqual(self.s("artist"), "abc")

    def test_organisation(self):
        self.s["organization"] = "foo"
        self.assertEqual(self.s("title"), "foo")
        self.assertEqual(self.s.get("title"), "foo")

    def test_title_split_stream(self):
        self.assertFalse(self.s("artist"))
        self.s["title"] = "artist - title"
        self.s.multisong = False
        self.assertEqual(self.s("title"), "title")
        self.assertEqual(self.s.get("title"), "title")
        self.assertEqual(self.s("artist"), "artist")
        self.assertEqual(self.s.get("artist"), "artist")

    def test_title_split(self):
        self.assertTrue(self.s.multisong)
        self.s["title"] = "artist - title"
        self.assertEqual(self.s("title"), self.s["title"])

    def test_format(self):
        self.assertEqual(self.s("~format"), self.s.format)
        self.s["audio-codec"] = "SomeCodec"
        self.assertTrue("SomeCodec" in self.s("~format"))
        self.assertTrue(self.s.format in self.s("~format"))

    def test_people(self):
        self.s["title"] = "artist - title"
        self.s.multisong = False
        self.assertEqual(self.s("~people"), "artist")
        self.assertEqual(self.s("~~people~foo"), "artist")

add(TIRFile)
