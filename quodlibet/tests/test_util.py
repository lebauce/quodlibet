# -*- coding: utf-8 -*-
import uuid
from quodlibet.config import HardCodedRatingsPrefs
from quodlibet.util.path import *
from quodlibet.util import re_escape
from quodlibet.util.string import decode, encode, split_escape, join_escape
from quodlibet.util.string.splitters import *
from quodlibet.util.library import *
from tests import TestCase, mkstemp, skipIf

import tempfile
import os
import sys
import threading
import time
from quodlibet import util
from quodlibet import config
from quodlibet.util import format_time_long as f_t_l


is_win = os.name == "nt"


class Tmkdir(TestCase):
    def test_exists(self):
        mkdir(".")

    def test_notdirectory(self):
        self.failUnlessRaises(OSError, mkdir, __file__)

    def test_manydeep(self):
        self.failUnless(not os.path.isdir("nonext"))
        mkdir("nonext/test/test2/test3")
        try:
            self.failUnless(os.path.isdir("nonext/test/test2/test3"))
        finally:
            os.rmdir("nonext/test/test2/test3")
            os.rmdir("nonext/test/test2")
            os.rmdir("nonext/test")
            os.rmdir("nonext")


class Tgetcwd(TestCase):

    def test_Tgetcwd(self):
        self.assertTrue(is_fsnative(getcwd()))


class Tmtime(TestCase):
    def test_equal(self):
        self.failUnlessEqual(mtime("."), os.path.getmtime("."))

    def test_bad(self):
        self.failIf(os.path.exists("/dev/doesnotexist"))
        self.failUnlessEqual(mtime("/dev/doesnotexist"), 0)


class Tunexpand(TestCase):
    d = expanduser("~")
    u = unexpand(d)

    def test_base(self):
        path = unexpand(self.d)
        if is_win:
            self.failUnlessEqual(path, "%USERPROFILE%")
        else:
            self.failUnlessEqual(path, "~")

    def test_base_trailing(self):
        path = unexpand(self.d + os.path.sep)
        self.failUnlessEqual(path, self.u + os.path.sep)

    def test_noprefix(self):
        path = unexpand(self.d + "foobar" + os.path.sep)
        self.failUnlessEqual(path, self.d + "foobar" + os.path.sep)

    def test_subfile(self):
        path = unexpand(os.path.join(self.d, "la", "la"))
        self.failUnlessEqual(path, os.path.join(self.u, "la", "la"))


class Tformat_rating(TestCase):
    def setUp(self):
        self.r = config.RATINGS = HardCodedRatingsPrefs()

    def test_empty(self):
        self.failUnlessEqual(util.format_rating(0, blank=False), "")

    def test_full(self):
        self.failUnlessEqual(
            len(util.format_rating(1, blank=False)),
            int(1 / self.r.precision))

    def test_rating_length(self):
        config.RATINGS.number = 4
        for i in range(0, int(1 / self.r.precision + 1)):
            self.failUnlessEqual(
                i, len(util.format_rating(i * self.r.precision, blank=False)))

    def test_bogus(self):
        max_length = int(1 / self.r.precision)
        self.failUnlessEqual(len(util.format_rating(2 ** 32 - 1, blank=False)),
                             max_length)
        self.failUnlessEqual(len(util.format_rating(-4.2, blank=False)), 0)

    def test_blank_lengths(self):
        """Check that there are no unsuspected edge-cases
        for various rating precisions"""
        for self.r.number in [1, 5, 4, 3, 2]:
            steps = self.r.number
            self.failUnlessEqual(len(util.format_rating(1)), steps)
            self.failUnlessEqual(len(util.format_rating(0)), steps)
            self.failUnlessEqual(len(util.format_rating(0.5)), steps)
            self.failUnlessEqual(len(util.format_rating(1 / 3.0)), steps)

    def test_blank_values(self):
        self.r.number = 5
        self.r.blank_symbol = "0"
        self.r.full_symbol = "1"
        # Easy ones first
        self.failUnlessEqual(util.format_rating(0.0), "00000")
        self.failUnlessEqual(util.format_rating(0.2), "10000")
        self.failUnlessEqual(util.format_rating(0.8), "11110")
        self.failUnlessEqual(util.format_rating(1.0), "11111")
        # A bit arbitrary, but standard behaviour
        self.failUnlessEqual(util.format_rating(0.5), "11100")
        # Test rounding down...
        self.failUnlessEqual(util.format_rating(0.6), "11100")
        # Test rounding up...
        self.failUnlessEqual(util.format_rating(0.9), "11111")
        # You never know...
        self.failUnlessEqual(util.format_rating(3.0), "11111")
        self.failUnlessEqual(util.format_rating(-0.5), "00000")


class Tpango(TestCase):
    def test_escape_empty(self):
        self.failUnlessEqual(util.escape(""), "")

    def test_roundtrip(self):
        for s in ["foo&amp;", "<&>", "&", "&amp;", "<&testing&amp;>amp;"]:
            esc = util.escape(s)
            self.failIfEqual(s, esc)
            self.failUnlessEqual(s, util.unescape(esc))

    def test_unescape_empty(self):
        self.failUnlessEqual(util.unescape(""), "")

    def test_format(self):
        self.assertEqual(util.bold("foo"), "<b>foo</b>")
        self.assertEqual(util.italic("foo"), "<i>foo</i>")
        self.assertEqual(util.monospace("foo"), "<tt>foo</tt>")


class Tre_esc(TestCase):
    def test_empty(self):
        self.failUnlessEqual(re_escape(""), "")
        self.assertTrue(isinstance(re_escape(""), bytes))

    def test_empty_unicode(self):
        self.failUnlessEqual(re_escape(u""), u"")
        self.assertTrue(isinstance(re_escape(u""), unicode))

    def test_safe(self):
        self.failUnlessEqual(re_escape("fo o"), "fo o")

    def test_unsafe(self):
        self.failUnlessEqual(re_escape("!bar"), r"\!bar")

    def test_many_unsafe(self):
        self.failUnlessEqual(
            re_escape("*quux#argh?woo"), r"\*quux\#argh\?woo")


class Tdecode(TestCase):
    def test_empty(self):
        self.failUnlessEqual(decode(""), "")

    def test_safe(self):
        self.failUnlessEqual(decode("foo!"), "foo!")

    def test_invalid(self):
        self.failUnlessEqual(
            decode("fo\xde"), u'fo\ufffd [Invalid Encoding]')


class Tencode(TestCase):
    def test_empty(self):
        self.failUnlessEqual(encode(""), "")

    def test_unicode(self):
        self.failUnlessEqual(encode(u"abcde"), "abcde")


class Tcapitalize(TestCase):
    def test_empty(self):
        self.failUnlessEqual(util.capitalize(""), "")

    def test_firstword(self):
        self.failUnlessEqual(util.capitalize("aa b"), "Aa b")

    def test_preserve(self):
        self.failUnlessEqual(util.capitalize("aa B"), "Aa B")

    def test_nonalphabet(self):
        self.failUnlessEqual(util.capitalize("!aa B"), "!aa B")


class Thuman_sort(TestCase):
    def smaller(self, x, y):
        return util.human_sort_key(x) < util.human_sort_key(y)

    def test_human(self):
        self.failUnlessEqual(self.smaller(u"2", u"15"), True)
        self.failUnlessEqual(self.smaller(u" 2", u"15 "), True)
        self.failUnlessEqual(self.smaller(u"a2 g", u"a 2z"), True)
        self.failUnlessEqual(self.smaller(u"a2zz", u"a2.1z"), True)

        self.failUnlessEqual(self.smaller(u"42o", u"42\xf6"), True)
        self.failUnlessEqual(self.smaller(u"42\xf6", u"42p"), True)

        self.failUnlessEqual(self.smaller(u"bbb", u"zzz3"), True)

    def test_false(self):
        # album browser needs that to sort albums without artist/title
        # to the bottom
        self.failIf(util.human_sort_key(""))

    def test_white(self):
        self.failUnlessEqual(
            util.human_sort_key(u"  3foo    bar6 42.8"),
            util.human_sort_key(u"3 foo bar6  42.8  "))
        self.failUnlessEqual(64.0 in util.human_sort_key(u"64. 8"), True)


class Tformat_time(TestCase):
    def test_seconds(self):
        self.failUnlessEqual(util.format_time(0), "0:00")
        self.failUnlessEqual(util.format_time(59), "0:59")

    def test_minutes(self):
        self.failUnlessEqual(util.format_time(60), "1:00")
        self.failUnlessEqual(util.format_time(60 * 59 + 59), "59:59")

    def test_hourss(self):
        self.failUnlessEqual(util.format_time(60 * 60), "1:00:00")
        self.failUnlessEqual(
            util.format_time(60 * 60 + 60 * 59 + 59), "1:59:59")

    def test_negative(self):
        self.failUnlessEqual(util.format_time(-124), "-2:04")


class Tparse_time(TestCase):
    def test_invalid(self):
        self.failUnlessEqual(util.parse_time("not a time"), 0)

    def test_except(self):
        self.failUnlessRaises(ValueError, util.parse_time, "not a time", None)

    def test_empty(self):
        self.failUnlessEqual(util.parse_time(""), 0)

    def test_roundtrip(self):
        # The values are the ones tested for Tformat_time, so we know they
        # will be formatted correctly. They're also representative of
        # all the major patterns.
        for i in [0, 59, 60, 60 * 59 + 59, 60 * 60, 60 * 60 + 60 * 59 + 59]:
            self.failUnlessEqual(util.parse_time(util.format_time(i)), i)

    def test_negative(self):
        self.failUnlessEqual(util.parse_time("-2:04"), -124)


class Tparse_date(TestCase):

    def test_invalid(self):
        self.assertRaises(ValueError, util.parse_date, "not a date")
        self.assertRaises(ValueError, util.parse_date, "0")
        self.assertRaises(ValueError, util.parse_date, "2000-13")
        self.assertRaises(ValueError, util.parse_date, "2000-01-32")
        self.assertRaises(ValueError, util.parse_date, "2000-01-0")
        self.assertRaises(ValueError, util.parse_date, "2000-0-01")

    def test_valid(self):
        ref = time.mktime(time.strptime("2004", "%Y"))
        self.assertEqual(util.parse_date("2004"), ref)
        self.assertEqual(util.parse_date("2004-01-01"), ref)
        self.assertEqual(util.parse_date("2004-1-1"), ref)
        self.assertTrue(
            util.parse_date("2004-01-01") < util.parse_date("2004-01-02"))


class Tdate_key(TestCase):

    def test_compare(self):
        date_key = util.date_key
        self.assertTrue(date_key("2004") == date_key("2004-01-01"))
        self.assertTrue(date_key("2004") == date_key("2004-01"))
        self.assertTrue(date_key("2004") < date_key("2004-01-02"))
        self.assertTrue(date_key("2099-02-02") < date_key("2099-03-30"))

        self.assertTrue(date_key("2004-01-foo") == date_key("2004-01"))

    def test_validate(self):
        validate = util.validate_query_date

        for valid in ["2004", "2005-01", "3000-3-4"]:
            self.assertTrue(validate(valid))

        for invalid in ["", "-", "3000-", "9-0", "8-1-0", "1-13-1", "1-1-32",
                        "1-1-1-1-1", "a", "1-a", "1-1-a"]:
            self.assertFalse(validate(invalid))


class Tformat_size(TestCase):
    def t_dict(self, d):
        for key, value in d.items():
            self.failUnlessEqual(util.format_size(key), value)

    def test_bytes(self):
        self.t_dict({0: "0 B", 1: "1 B", 1023: "1023 B"})

    def test_kbytes(self):
        self.t_dict({
            1024: "1.00 KB",
            1536: "1.50 KB",
            10240: "10 KB",
            15360: "15 KB"
        })

    def test_mbytes(self):
        self.t_dict({
            1024 * 1024: "1.00 MB",
            1024 * 1536: "1.50 MB",
            1024 * 10240: "10.0 MB",
            1024 * 15360: "15.0 MB",
            123456 * 1024: "121 MB",
            765432 * 1024: "747 MB"})

    def test_gbytes(self):
        self.t_dict({
            1024 * 1024 * 1024: "1.0 GB",
            1024 * 1024 * 1536: "1.5 GB",
            1024 * 1024 * 10240: "10.0 GB",
            1024 * 1024 * 15360: "15.0 GB"
        })


class Tsplit_title(TestCase):

    def test_trailing(self):
        self.failUnlessEqual(split_title("foo ~"), ("foo ~", []))

    def test_prefixed(self):
        self.failUnlessEqual(split_title("~foo "), ("~foo ", []))

    def test_prefix_and_trailing(self):
        self.failUnlessEqual(split_title("~foo ~"), ("~foo ~", []))

    def test_prefix_and_version(self):
        self.failUnlessEqual(split_title("~foo ~bar~"), ("~foo", ["bar"]))

    def test_simple(self):
        self.failUnlessEqual(split_title("foo (baz)"), ("foo", ["baz"]))

    def test_two_versions(self):
        self.failUnlessEqual(
            split_title("foo [b, c]"), ("foo", ["b", "c"]))

    def test_custom_splitter(self):
        self.failUnlessEqual(
            split_title("foo [b c]", " "), ("foo", ["b", "c"]))


class Tsplit_album(TestCase):
    def test_album_looks_like_disc(self):
        self.failUnlessEqual(
            split_album("disk 2"), ("disk 2", None))

    def test_basic_disc(self):
        self.failUnlessEqual(
            split_album("foo disc 1/2"), ("foo", "1/2"))

    def test_looks_like_disc_but_isnt(self):
        self.failUnlessEqual(
            split_album("disc foo disc"), ("disc foo disc", None))

    def test_disc_album_and_disc(self):
        self.failUnlessEqual(
            split_album("disc foo disc 1"), ("disc foo", "1"))

    def test_weird_disc(self):
        self.failUnlessEqual(
            split_album("foo ~disk 3~"), ("foo", "3"))

    def test_weird_not_disc(self):
        self.failUnlessEqual(
            split_album("foo ~crazy 3~"), ("foo ~crazy 3~", None))


class Tsplit_people(TestCase):

    def test_parened_person(self):
        self.failUnlessEqual(split_people("foo (bar)"), ("foo", ["bar"]))

    def test_with_person(self):
        self.failUnlessEqual(
            split_people("foo (With bar)"), ("foo", ["bar"]))

    def test_with_with_person(self):
        self.failUnlessEqual(
            split_people("foo (with with bar)"), ("foo", ["with bar"]))

    def test_featuring_two_people(self):
        self.failUnlessEqual(
            split_people("foo featuring bar, qx"), ("foo", ["bar", "qx"]))

    def test_featuring_person_bracketed(self):
        self.failUnlessEqual(
            split_people("foo (Ft. bar)"), ("foo", ["bar"]))
        self.failUnlessEqual(
            split_people("foo(feat barman)"), ("foo", ["barman"]))

    def test_originally_by(self):
        self.failUnlessEqual(
            split_people("title (originally by artist)"),
            ("title", ["artist"]))
        self.failUnlessEqual(
            split_people("title [originally by artist & artist2]"),
            ("title", ["artist", "artist2"]))

    def test_cover(self):
        self.failUnlessEqual(
            split_people("Pyscho Killer [Talking Heads Cover]"),
            ("Pyscho Killer", ["Talking Heads"]))


class Ttag(TestCase):
    def test_empty(self):
        self.failUnlessEqual(util.tag(""), "Invalid tag")

    def test_basic(self):
        self.failUnlessEqual(util.tag("title"), "Title")

    def test_basic_nocap(self):
        self.failUnlessEqual(util.tag("title", False), "title")

    def test_internal(self):
        self.failUnlessEqual(util.tag("~year"), "Year")

    def test_numeric(self):
        self.failUnlessEqual(util.tag("~#year"), "Year")

    def test_two(self):
        self.failUnlessEqual(util.tag("title~version"), "Title / Version")

    def test_two_nocap(self):
        self.failUnlessEqual(
            util.tag("title~version", False), "title / version")

    def test_precap_handling(self):
        self.failUnlessEqual(util.tag("labelid"), "Label ID")
        self.failUnlessEqual(util.tag("labelid", False), "label ID")


class Ttagsplit(TestCase):

    def test_single_tag(self):
        self.failUnlessEqual(util.tagsplit("foo"), ["foo"])

    def test_synth_tag(self):
        self.failUnlessEqual(util.tagsplit("~foo"), ["~foo"])

    def test_two_tags(self):
        self.failUnlessEqual(util.tagsplit("foo~bar"), ["foo", "bar"])

    def test_two_prefix(self):
        self.failUnlessEqual(util.tagsplit("~foo~bar"), ["foo", "bar"])

    def test_synth(self):
        self.failUnlessEqual(util.tagsplit("~foo~~bar"), ["foo", "~bar"])

    def test_numeric(self):
        self.failUnlessEqual(util.tagsplit("~#bar"), ["~#bar"])

    def test_two_numeric(self):
        self.failUnlessEqual(util.tagsplit("~#foo~~#bar"), ["~#foo", "~#bar"])

    def test_two_synth_start(self):
        self.failUnlessEqual(
            util.tagsplit("~~people~album"), ["~people", "album"])


class Tpattern(TestCase):

    def test_empty(self):
        self.failUnlessEqual(util.pattern(""), "")

    def test_basic(self):
        self.failUnlessEqual(util.pattern("<title>"), "Title")

    def test_basic_nocap(self):
        self.failUnlessEqual(util.pattern("<title>", False), "title")

    def test_internal(self):
        self.failUnlessEqual(util.pattern("<~plays>"), "Plays")

    def test_tied(self):
        self.failUnlessEqual(util.pattern("<~title~album>"), "Title - Album")

    def test_unknown(self):
        self.failUnlessEqual(util.pattern("<foobarbaz>"), "Foobarbaz")

    def test_condition(self):
        self.failUnlessEqual(util.pattern("<~year|<~year> - <album>|<album>>"),
                             "Year - Album")

    def test_escape(self):
        self.failUnlessEqual(util.pattern("\<i\><&>\</i\>", esc=True),
                            "<i>&amp;</i>")

    def test_invalid(self):
        self.failUnlessEqual(util.pattern("<date"), "")
        util.pattern("<d\\")


class Tformat_time_long(TestCase):

    def test_second(s):
        s.assertEquals(f_t_l(1).split(", ")[0], _("1 second"))

    def test_seconds(s):
        s.assertEquals(f_t_l(2).split(", ")[0], _("%d seconds") % 2)

    def test_notminutes(s):
        s.assertEquals(f_t_l(59).split(", ")[0], _("%d seconds") % 59)

    def test_minute(s):
        s.assertEquals(f_t_l(60), _("1 minute"))

    def test_minutes(s):
        s.assertEquals(f_t_l(120).split(", ")[0], _("%d minutes") % 2)

    def test_nothours(s):
        s.assertEquals(f_t_l(3599).split(", ")[0], _("%d minutes") % 59)

    def test_hour(s):
        s.assertEquals(f_t_l(3600), _("1 hour"))

    def test_hours(s):
        s.assertEquals(f_t_l(7200), _("%d hours") % 2)

    def test_notdays(s):
        s.assertEquals(f_t_l(86399).split(", ")[0], _("%d hours") % 23)

    def test_seconds_dropped(s):
        s.assertEquals(len(f_t_l(3601).split(", ")), 2)

    def test_day(s):
        s.assertEquals(f_t_l(86400), _("1 day"))

    def test_days(s):
        s.assertEquals(f_t_l(172800).split(", ")[0], _("%d days") % 2)

    def test_notyears(s):
        s.assertEquals(f_t_l(31535999).split(", ")[0], _("%d days") % 364)

    def test_year(s):
        s.assertEquals(f_t_l(31536000), _("1 year"))

    def test_years(s):
        s.assertEquals(f_t_l(63072000).split(", ")[0], _("%d years") % 2)

    def test_drop_zero(s):
        s.assertEquals(f_t_l(3601), ", ".join([_("1 hour"), _("1 second")]))

    def test_limit_zero(s):
        s.assertEquals(f_t_l(1, limit=0), _("1 second"))

    def test_limit(s):
        s.assertEquals(len(f_t_l(2 ** 31).split(", ")), 2)


class Tspawn(TestCase):

    def test_simple(self):
        if is_win:
            return
        self.failUnless(util.spawn(["ls", "."], stdout=True))

    def test_invalid(self):
        from gi.repository import GLib
        self.failUnlessRaises(GLib.GError, util.spawn, ["not a command"])

    def test_types(self):
        if is_win:
            return
        self.failUnlessRaises(TypeError, util.spawn, [u"ls"])

    def test_get_output(self):
        if is_win:
            return
        fileobj = util.spawn(["echo", "'$1'", '"$2"', ">3"], stdout=True)
        self.failUnlessEqual(fileobj.read().split(), ["'$1'", '"$2"', ">3"])


class Txdg_dirs(TestCase):

    def test_system_data_dirs_posix(self):
        if is_win:
            return

        os.environ["XDG_DATA_DIRS"] = "/xyz"
        self.failUnlessEqual(xdg_get_system_data_dirs()[0], "/xyz")
        del os.environ["XDG_DATA_DIRS"]
        dirs = xdg_get_system_data_dirs()
        self.failUnlessEqual(dirs[0], "/usr/local/share/")
        self.failUnlessEqual(dirs[1], "/usr/share/")

    def test_data_home(self):
        if is_win:
            return

        os.environ["XDG_DATA_HOME"] = "/xyz"
        self.failUnlessEqual(xdg_get_data_home(), "/xyz")
        del os.environ["XDG_DATA_HOME"]
        should = os.path.join(os.path.expanduser("~"), ".local", "share")
        self.failUnlessEqual(xdg_get_data_home(), should)

    def test_get_user_dirs(self):
        xdg_get_user_dirs()

    def test_parse_xdg_user_dirs(self):
        data = '# foo\nBLA="$HOME/blah"\n'
        vars_ = parse_xdg_user_dirs(data)
        self.assertTrue("BLA" in vars_)
        expected = os.path.join(os.environ.get("HOME", ""), "blah")
        self.assertEqual(vars_["BLA"], expected)

        vars_ = parse_xdg_user_dirs('BLA="$HOME/"')
        self.assertTrue("BLA" in vars_)
        self.assertEqual(vars_["BLA"], os.environ.get("HOME", ""))

        # some invalid
        self.assertFalse(parse_xdg_user_dirs("foo"))
        self.assertFalse(parse_xdg_user_dirs("foo=foo bar"))
        self.assertFalse(parse_xdg_user_dirs("foo='foo"))

    def test_on_windows(self):
        self.assertTrue(xdg_get_system_data_dirs())
        self.assertTrue(xdg_get_cache_home())
        self.assertTrue(xdg_get_data_home())
        self.assertTrue(xdg_get_config_home())


class Tlibrary(TestCase):
    def setUp(self):
        config.init()

    def tearDown(self):
        config.quit()

    def test_basic(self):
        self.failIf(get_scan_dirs())
        if os.name == "nt":
            set_scan_dirs([u"C:\\foo", u"D:\\bar", ""])
            self.failUnlessEqual(get_scan_dirs(), [u"C:\\foo", u"D:\\bar"])
        else:
            set_scan_dirs(["foo", "bar", ""])
            self.failUnlessEqual(get_scan_dirs(), ["foo", "bar"])


class TNormalizePath(TestCase):

    def test_default(self):
        from quodlibet.util.path import _normalize_path as norm

        name = norm(tempfile.mkdtemp())
        try:
            self.failUnlessEqual(norm(name), name)
            self.failUnlessEqual(norm(os.path.join(name, "foo", "..")), name)
        finally:
            os.rmdir(name)

    def test_canonicalise(self):
        from quodlibet.util.path import _normalize_path, _normalize_darwin_path
        self._test_canonicalise(_normalize_path)
        if sys.platform == "darwin":
            self._test_canonicalise(_normalize_darwin_path)

    def _test_canonicalise(self, norm):
        f, path = tempfile.mkstemp()
        os.close(f)
        path = norm(path)

        link = None
        if not is_win:
            link = str(uuid.uuid4())
            os.symlink(path, link)
        try:
            self.failUnlessEqual(norm(path, canonicalise=True), path)
            self.failUnlessEqual(norm(os.path.join(path, "foo", ".."), True),
                                 path)
            if link:
                self.failUnlessEqual(norm(link, True), path)
                # A symlink shouldn't be resolved unless asked for
                self.failIfEqual(norm(link, False), path)
                # And the other behaviour should also work
                unnormalised_path = os.path.join(link, "foo", "..")
                self.failUnlessEqual(norm(unnormalised_path, True), path)
        finally:
            if link:
                os.remove(link)
            os.remove(path)


class Tatomic_save(TestCase):

    def test_basic(self):
        fd, filename = mkstemp(".cfg")
        os.close(fd)

        with open(filename, "wb") as fobj:
            fobj.write("nope")
        with open(filename + ".tmp", "wb") as fobj:
            fobj.write("temp_nope")

        with util.atomic_save(filename, ".tmp", "wb") as fobj:
            fobj.write("foo")

        with open(filename, "rb") as fobj:
            self.assertEqual(fobj.read(), "foo")
        self.assertFalse(os.path.exists(filename + ".tmp"))


class Tescape_filename(TestCase):

    def test_str(self):
        result = escape_filename("\x00\x01")
        self.assertEqual(result, "%00%01")
        self.assertTrue(is_fsnative(result))

    def test_unicode(self):
        result = escape_filename(u'abc\xe4')
        self.assertEqual(result, "abc%C3%A4")
        self.assertTrue(is_fsnative(result))


@skipIf(is_win)
class Tload_library(TestCase):

    def test_libc(self):
        lib, name = util.load_library(["c"])
        self.assertEqual(name, "c")

        lib2, name = util.load_library(["c"])
        self.assertTrue(lib is lib2)

        lib3, name = util.load_library(["c"], shared=False)
        self.assertTrue(lib2 is not lib3)

    def test_glib(self):
        if sys.platform == "darwin":
            fn = "libglib-2.0.0.dylib"
        else:
            fn = "libglib-2.0.so.0"
        lib, name = util.load_library([fn])
        self.assertEqual(name, fn)
        self.assertTrue(lib)


class Tstrip_win32_incompat_from_path(TestCase):

    def test_types(self):
        v = strip_win32_incompat_from_path("")
        self.assertTrue(isinstance(v, bytes))
        v = strip_win32_incompat_from_path("foo")
        self.assertTrue(isinstance(v, bytes))

        v = strip_win32_incompat_from_path(u"")
        self.assertTrue(isinstance(v, unicode))
        v = strip_win32_incompat_from_path(u"foo")
        self.assertTrue(isinstance(v, unicode))

    def test_basic(self):
        if is_win:
            v = strip_win32_incompat_from_path(u"C:\\foo\\<>/a")
            self.assertEqual(v, u"C:\\foo\\___a")
        else:
            v = strip_win32_incompat_from_path("/foo/<>a")
            self.assertEqual(v, "/foo/__a")


class TPathHandling(TestCase):

    def test_main(self):
        v = fsnative(u"foo")
        self.assertTrue(is_fsnative(v))

        v2 = glib2fsnative(fsnative2glib(v))
        self.assertTrue(is_fsnative(v2))
        self.assertEqual(v, v2)

        v3 = bytes2fsnative(fsnative2bytes(v))
        self.assertTrue(is_fsnative(v3))
        self.assertEqual(v, v3)


class Tget_temp_cover_file(TestCase):

    def test_main(self):
        fobj = get_temp_cover_file(b"foobar")
        try:
            self.assertTrue(is_fsnative(fobj.name))
        finally:
            fobj.close()


class Tsplit_escape(TestCase):

    def test_split_escape(self):
        # from mutagen

        inout = [
            (("", ":"), [""]),
            ((":", ":"), ["", ""]),
            ((":", ":", 0), [":"]),
            ((":b:c:", ":", 0), [":b:c:"]),
            ((":b:c:", ":", 1), ["", "b:c:"]),
            ((":b:c:", ":", 2), ["", "b", "c:"]),
            ((":b:c:", ":", 3), ["", "b", "c", ""]),
            (("a\\:b:c", ":"), ["a:b", "c"]),
            (("a\\\\:b:c", ":"), ["a\\", "b", "c"]),
            (("a\\\\\\:b:c\\:", ":"), ["a\\:b", "c:"]),
            (("\\", ":"), [""]),
            (("\\\\", ":"), ["\\"]),
            (("\\\\a\\b", ":"), ["\\a\\b"]),
        ]

        for inargs, out in inout:
            self.assertEqual(split_escape(*inargs), out)

    def test_types(self):
        parts = split_escape("\xff:\xff", ":")
        self.assertEqual(parts, ["\xff", "\xff"])
        self.assertTrue(isinstance(parts[0], bytes))

        parts = split_escape(u"a:b", u":")
        self.assertEqual(parts, [u"a", u"b"])
        self.assertTrue(all(isinstance(p, unicode) for p in parts))

        parts = split_escape(u"", u":")
        self.assertEqual(parts, [u""])
        self.assertTrue(all(isinstance(p, unicode) for p in parts))

        parts = split_escape(u":", u":")
        self.assertEqual(parts, [u"", u""])
        self.assertTrue(all(isinstance(p, unicode) for p in parts))

    def test_join_escape_types(self):
        self.assertEqual(join_escape([], ":"), "")
        self.assertTrue(isinstance(join_escape([], ":"), bytes))
        self.assertTrue(isinstance(join_escape([], u":"), unicode))
        self.assertEqual(join_escape(["\xff", "\xff"], ":"), "\xff:\xff")
        self.assertEqual(join_escape([u'\xe4', u'\xe4'], ":"), u'\xe4:\xe4')

    def test_join_escape(self):
        self.assertEqual(join_escape([":"], ":"), "\\:")
        self.assertEqual(join_escape(["\\:", ":"], ":"), "\\\\\\::\\:")

    def test_roundtrip(self):
        values = ["\\:", ":"]
        joined = join_escape(values, ":")
        self.assertEqual(split_escape(joined, ":"), values)


class TMainRunner(TestCase):

    def test_abort_before_call(self):
        runner = util.MainRunner()

        def worker():
            self.assertRaises(
                util.MainRunnerAbortedError, runner.call, lambda: None)

        thread = threading.Thread(target=worker)
        runner.abort()
        thread.start()
        thread.join()

    def test_timeout(self):
        runner = util.MainRunner()

        def worker():
            self.assertRaises(
                util.MainRunnerTimeoutError, runner.call, lambda: None,
                timeout=0.00001)

        for i in range(3):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
        runner.abort()

    def test_call_exception(self):
        from gi.repository import GLib

        runner = util.MainRunner()
        loop = GLib.MainLoop()

        def func():
            raise KeyError

        def worker():
            try:
                self.assertRaises(util.MainRunnerError, runner.call, func)
            finally:
                loop.quit()

        thread = threading.Thread(target=worker)
        thread.start()
        loop.run()
        runner.abort()
        thread.join()

    def test_from_main_loop(self):
        from gi.repository import GLib

        runner = util.MainRunner()
        loop = GLib.MainLoop()

        def in_main_loop():
            try:
                self.assertRaises(
                    util.MainRunnerError, runner.call, lambda: None, foo=0)
                self.assertEqual(
                    runner.call(lambda i: i + 1, 42, priority=0), 43)
                self.assertEqual(runner.call(lambda i: i - 1, 42), 41)
            finally:
                loop.quit()

        GLib.idle_add(in_main_loop)
        loop.run()

    def test_ok(self):
        from gi.repository import GLib

        runner = util.MainRunner()
        loop = GLib.MainLoop()

        def func(i):
            self.assertTrue(util.is_main_thread())
            return i + 1

        def worker():
            try:
                self.assertEqual(runner.call(func, 42), 43)
            finally:
                loop.quit()

        thread = threading.Thread(target=worker)
        thread.start()

        loop.run()
        thread.join()
        runner.abort()

    def test_multi_abort(self):
        runner = util.MainRunner()
        runner.abort()
        runner.abort()

        def worker():
            self.assertRaises(util.MainRunnerError, runner.call, lambda: None)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()


class Tconnect_destroy(TestCase):

    def test_main(self):
        from gi.repository import Gtk

        b = Gtk.Button()

        class A(Gtk.Button):

            def foo(self):
                pass

        a = A()
        ref = sys.getrefcount(a)
        util.connect_destroy(b, "clicked", a.foo)
        self.assertEqual(sys.getrefcount(a), ref + 1)
        a.destroy()
        self.assertEqual(sys.getrefcount(a), ref)


class Tcached_property(TestCase):

    def test_main(self):

        class A(object):
            @util.cached_property
            def foo(self):
                return object()

        a = A()
        first = a.foo
        self.assertTrue(first is a.foo)
        del a.__dict__["foo"]
        self.assertFalse(first is a.foo)

    def test_dunder(self):

        def define_class():

            class A(object):
                @util.cached_property
                def __foo_(self):
                    return object()

        self.assertRaises(AssertionError, define_class)


class Tenum(TestCase):

    def test_main(self):

        @util.enum
        class Foo(object):
            FOO = 0
            BAR = 1

        self.assertTrue(issubclass(Foo, int))
        self.assertTrue(isinstance(Foo.BAR, Foo))
        self.assertTrue(isinstance(Foo.FOO, Foo))
        self.assertEqual(Foo.FOO, 0)
        self.assertEqual(Foo.BAR, 1)


class Tlist_unique(TestCase):

    def test_main(self):
        self.assertEqual(util.list_unique([]), [])
        self.assertEqual(util.list_unique(iter([])), [])
        self.assertEqual(util.list_unique([1, 2, 3]), [1, 2, 3])
        self.assertEqual(util.list_unique([1, 2, 1, 4]), [1, 2, 4])
        self.assertEqual(util.list_unique([1, 1, 1, 2]), [1, 2])
