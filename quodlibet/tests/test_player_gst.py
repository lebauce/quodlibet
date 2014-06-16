# -*- coding: utf-8 -*-

import os
import contextlib

try:
    from gi.repository import Gst
except ImportError:
    Gst = None

import unittest
from tests import TestCase, skipUnless

try:
    from quodlibet.player.gstbe.util import GStreamerSink as Sink
    from quodlibet.player.gstbe.util import parse_gstreamer_taglist
    from quodlibet.player.gstbe.util import find_audio_sink
    from quodlibet.player.gstbe.prefs import GstPlayerPreferences
except ImportError:
    pass

from quodlibet.player import PlayerError
from quodlibet.util import sanitize_tags
from quodlibet import config


@contextlib.contextmanager
def ignore_gst_errors():
    old = Gst.debug_get_default_threshold()
    Gst.debug_set_default_threshold(Gst.DebugLevel.NONE)
    yield
    Gst.debug_set_default_threshold(old)


@skipUnless(Gst, "GStreamer missing")
class TGstPlayerPrefs(TestCase):

    def setUp(self):
        config.init()

    def tearDown(self):
        config.quit()

    def test_main(self):
        widget = GstPlayerPreferences(None, True)
        widget.destroy()


@skipUnless(Gst, "GStreamer missing")
class TGStreamerSink(TestCase):
    def test_simple(self):
        sinks = ["gconfaudiosink", "alsasink"]
        for n in filter(Gst.ElementFactory.find, sinks):
            obj, name = Sink(n)
            self.failUnless(obj)
            self.failUnlessEqual(name, n)

    def test_invalid(self):
        with ignore_gst_errors():
            self.assertRaises(PlayerError, Sink, "notarealsink")

    def test_fallback(self):
        obj, name = Sink("")
        self.failUnless(obj)
        if os.name == "nt":
            self.failUnlessEqual(name, "directsoundsink")
        else:
            self.failUnlessEqual(name, find_audio_sink()[1])

    def test_append_sink(self):
        obj, name = Sink("volume")
        self.failUnless(obj)
        self.failUnlessEqual(name.split("!")[-1].strip(), Sink("")[1])


@skipUnless(Gst, "GStreamer missing")
class TGstreamerTagList(TestCase):
    def test_parse(self):
        # gst.TagList can't be filled using pyGtk... so use a dict instead

        l = {}
        l["extended-comment"] = u"foo=bar"
        self.failUnless("foo" in parse_gstreamer_taglist(l))

        l["extended-comment"] = [u"foo=bar", u"bar=foo", u"bar=foo2"]
        self.failUnless("foo" in parse_gstreamer_taglist(l))
        self.failUnless("bar" in parse_gstreamer_taglist(l))
        self.failUnlessEqual(parse_gstreamer_taglist(l)["bar"], "foo\nfoo2")

        # date is abstract, so define our own
        # (might work with pygobject now)
        class Foo(object):
            def to_iso8601_string(self):
                return "3000-10-2"
        l["date"] = Foo()
        date = Gst.DateTime
        Gst.DateTime = Foo
        self.failUnlessEqual(parse_gstreamer_taglist(l)["date"], "3000-10-2")
        Gst.DateTime = date

        l["foo"] = u"äöü"
        parsed = parse_gstreamer_taglist(l)
        self.assertTrue(isinstance(parsed["foo"], unicode))
        self.assertTrue(u"äöü" in parsed["foo"].split("\n"))

        l["foo"] = u"äöü".encode("utf-8")
        parsed = parse_gstreamer_taglist(l)
        self.assertTrue(isinstance(parsed["foo"], unicode))
        self.assertTrue(u"äöü" in parsed["foo"].split("\n"))

        l["bar"] = 1.2
        self.failUnlessEqual(parse_gstreamer_taglist(l)["bar"], 1.2)

        l["bar"] = 9L
        self.failUnlessEqual(parse_gstreamer_taglist(l)["bar"], 9)

        l["bar"] = 9
        self.failUnlessEqual(parse_gstreamer_taglist(l)["bar"], 9)

        l["bar"] = Gst.TagList() # some random gst instance
        self.failUnless(isinstance(parse_gstreamer_taglist(l)["bar"], unicode))
        self.failUnless("GstTagList" in parse_gstreamer_taglist(l)["bar"])

    def test_sanitize(self):
        l = sanitize_tags({"location": u"http://foo"})
        self.failUnless("website" in l)

        l = sanitize_tags({"channel-mode": u"joint-stereo"})
        self.failUnlessEqual(l["channel-mode"], "stereo")

        l = sanitize_tags({"channel-mode": u"dual"})
        self.failUnlessEqual(l["channel-mode"], "stereo")

        l = sanitize_tags({"audio-codec": u"mp3"})
        self.failUnlessEqual(l["audio-codec"], "MP3")

        l = sanitize_tags({"audio-codec": u"Advanced Audio Coding"})
        self.failUnlessEqual(l["audio-codec"], "MPEG-4 AAC")

        l = sanitize_tags({"audio-codec": u"vorbis"})
        self.failUnlessEqual(l["audio-codec"], "Ogg Vorbis")

        l = {"a": u"http://www.shoutcast.com", "b": u"default genre"}
        l = sanitize_tags(l)
        self.failIf(l)

        l = sanitize_tags({"duration": 1000 * 42}, stream=True)
        self.failUnlessEqual(l["~#length"], 42)
        l = sanitize_tags({"duration": 1000 * 42})
        self.failIf(l)

        l = sanitize_tags({"duration": u"bla"}, stream=True)
        self.failUnlessEqual(l["duration"], u"bla")

        l = sanitize_tags({"bitrate": 1000 * 42}, stream=True)
        self.failUnlessEqual(l["~#bitrate"], 42)
        l = sanitize_tags({"bitrate": 1000 * 42})
        self.failIf(l)

        l = sanitize_tags({"bitrate": u"bla"})
        self.failUnlessEqual(l["bitrate"], u"bla")

        l = sanitize_tags({"nominal-bitrate": 1000 * 42})
        self.failUnlessEqual(l["~#bitrate"], 42)
        l = sanitize_tags({"nominal-bitrate": 1000 * 42}, stream=True)
        self.failIf(l)

        l = sanitize_tags({"nominal-bitrate": u"bla"})
        self.failUnlessEqual(l["nominal-bitrate"], u"bla")

        l = {"emphasis": u"something"}
        self.failIf(sanitize_tags(l))
        self.failIf(sanitize_tags(l))

        l = {"title": u"something"}
        self.failIf(sanitize_tags(l))
        self.failUnless(sanitize_tags(l, stream=True))

        l = {"artist": u"something"}
        self.failIf(sanitize_tags(l))
        self.failUnless(sanitize_tags(l, stream=True))

        l = {"~#foo": 42, "bar": 42, "~#bla": u"42"}
        self.failUnless("~#foo" in sanitize_tags(l))
        self.failUnless("~#bar" in sanitize_tags(l))
        self.failUnless("bla" in sanitize_tags(l))

        l = {}
        l["extended-comment"] = [u"location=1", u"website=2", u"website=3"]
        l = parse_gstreamer_taglist(l)
        l = sanitize_tags(l)["website"].split("\n")
        self.failUnless("1" in l)
        self.failUnless("2" in l)
        self.failUnless("3" in l)

        # parse_gstreamer_taglist should only return unicode
        self.failIf(sanitize_tags({"foo": "bar"}))
