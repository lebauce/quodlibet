# -*- coding: utf-8 -*-
import shutil
import os
from quodlibet import config

from tests import TestCase, mkdtemp
from quodlibet.formats._audio import AudioFile as Fakesong
from quodlibet.formats._audio import INTERN_NUM_DEFAULT, PEOPLE
from quodlibet.util.collection import Album, Playlist, avg, bayesian_average
from quodlibet.library.libraries import FileLibrary
from quodlibet.util import format_rating
from quodlibet.util.path import fsnative

config.RATINGS = config.HardCodedRatingsPrefs()

NUMERIC_SONGS = [
    Fakesong({"~filename": fsnative(u"fake1-\xf0.mp3"),
              "~#length": 4, "~#added": 5, "~#lastplayed": 1,
              "~#bitrate": 200, "date": "100", "~#rating": 0.1,
              "originaldate": "2004-01-01", "~#filesize": 101}),
    Fakesong({"~filename": fsnative(u"fake2.mp3"),
              "~#length": 7, "~#added": 7, "~#lastplayed": 88,
              "~#bitrate": 220, "date": "99", "~#rating": 0.3,
              "originaldate": "2002-01-01", "~#filesize": 202}),
    Fakesong({"~filename": fsnative(u"fake3.mp3"),
              "~#length": 1, "~#added": 3, "~#lastplayed": 43,
              "~#bitrate": 60, "date": "33", "~#rating": 0.5,
              "tracknumber": "4/6", "discnumber": "1/2"})
]
AMAZING_SONG = Fakesong({"~#length": 123, "~#rating": 1.0})


class TAlbum(TestCase):
    def setUp(self):
        config.init()

    def test_people_sort(s):
        songs = [
            Fakesong({"albumartist": "aa", "artist": "b\na"}),
            Fakesong({"albumartist": "aa", "artist": "a\na"})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.comma("~people"), "aa, a, b")

    def test_peoplesort_sort(s):
        songs = [
            Fakesong({"albumartistsort": "aa", "artist": "b\na"}),
            Fakesong({"albumartist": "aa", "artistsort": "a\na"})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.comma("~peoplesort"), "aa, a, b")

    def test_tied_tags(s):
        songs = [
            Fakesong({"artist": "a", "title": "c"}),
            Fakesong({"artist": "a", "dummy": "d\ne"})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.comma("~artist~dummy"), "a - e, d")

    def test_tied_num_tags(s):
        songs = [
            Fakesong({"~#length": 5, "title": "c", "~#rating": 0.4}),
            Fakesong({"~#length": 7, "dummy": "d\ne", "~#rating": 0.6}),
            Fakesong({"~#length": 0, "dummy2": 5, "~#rating": 0.5})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.comma("~foo~~s~~~"), "")
        s.failUnlessEqual(album.comma("~#length~dummy"), "12 - e, d")
        s.failUnlessEqual(album.comma("~#rating~dummy"), "0.50 - e, d")
        s.failUnlessEqual(album.comma("~#length:sum~dummy"), "12 - e, d")
        s.failUnlessEqual(album.comma("~#dummy2"), 5)
        s.failUnlessEqual(album.comma("~#dummy3"), "")

    def test_internal_tags(s):
        songs = [
            Fakesong({"~#length": 5, "discnumber": "1", "date": "2038"}),
            Fakesong({"~#length": 7, "dummy": "d\ne", "discnumber": "2"})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failIfEqual(album.comma("~long-length"), "")
        s.failIfEqual(album.comma("~tracks"), "")
        s.failIfEqual(album.comma("~discs"), "")
        s.failUnlessEqual(album.comma("~foo"), "")

        s.failUnlessEqual(album.comma(""), "")
        s.failUnlessEqual(album.comma("~"), "")
        s.failUnlessEqual(album.get("~#"), "")

    def test_numeric_ops(s):
        songs = NUMERIC_SONGS
        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.get("~#length"), 12)
        s.failUnlessEqual(album.get("~#length:sum"), 12)
        s.failUnlessEqual(album.get("~#length:max"), 7)
        s.failUnlessEqual(album.get("~#length:min"), 1)
        s.failUnlessEqual(album.get("~#length:avg"), 4)
        s.failUnlessEqual(album.get("~#length:foo"), 0)

        s.failUnlessEqual(album.get("~#added"), 7)
        s.failUnlessEqual(album.get("~#lastplayed"), 88)
        s.failUnlessEqual(album.get("~#bitrate"), 200)
        s.failUnlessEqual(album.get("~#year"), 33)
        s.failUnlessEqual(album.get("~#rating"), 0.3)
        s.failUnlessEqual(album.get("~#originalyear"), 2002)

    def test_numeric_comma(self):
        songs = [Fakesong({
            "~#added": long(1),
            "~#rating": 0.5,
            "~#bitrate": 42,
            "~#length": 1,
        })]

        album = Album(songs[0])
        album.songs = set(songs)

        self.assertEqual(album.comma("~#added"), 1)
        self.assertEqual(album.comma("~#rating"), 0.5)
        self.assertEqual(album.comma("~#bitrate"), 42)

    def test_numeric_funcs_text(self):
        songs = NUMERIC_SONGS
        album = Album(songs[0])
        album.songs = set(songs)

        self.assertEqual(album("~length:sum"), "0:12")
        self.assertEqual(album("~length:min"), "0:01")
        self.assertEqual(album("~long-length:min"), "1 second")
        self.assertEqual(album("~tracks:min"), "6 tracks")
        self.assertEqual(album("~discs:min"), "2 discs")
        self.assertEqual(album("~rating:min"), format_rating(0.1))
        self.assertEqual(album("~filesize:min"), "0 B")

    def test_single_rating(s):
        songs = [Fakesong({"~#rating": 0.75})]
        album = Album(songs[0])
        album.songs = set(songs)
        # One song should average to its own rating
        s.failUnlessEqual(album.get("~#rating:avg"), songs[0]("~#rating"))
        # BAV should now be default for rating
        s.failUnlessEqual(album.get("~#rating:bav"), album.get("~#rating:avg"))

    def test_multiple_ratings(s):
        r1, r2 = 1.0, 0.5
        songs = [Fakesong({"~#rating": r1}), Fakesong({"~#rating": r2})]
        album = Album(songs[0])
        album.songs = set(songs)
        # Standard averaging still available
        s.failUnlessEqual(album("~#rating:avg"), avg([r1, r2]))

        # C = 0.0 => emulate arithmetic mean
        config.set("settings", "bayesian_rating_factor", 0.0)
        s.failUnlessEqual(album("~#rating:bav"), album("~#rating:avg"))

    def test_bayesian_multiple_ratings(s):
        # separated from above to avoid caching
        c, r1, r2 = 5, 1.0, 0.5
        songs = [Fakesong({"~#rating": r1}), Fakesong({"~#rating": r2})]
        album = Album(songs[0])
        album.songs = set(songs)

        config.set("settings", "bayesian_rating_factor", float(c))
        s.failUnlessEqual(
            config.getfloat("settings", "bayesian_rating_factor"), float(c))
        expected = avg(c * [config.RATINGS.default] + [r1, r2])
        s.failUnlessEqual(album("~#rating:bav"), expected)
        s.failUnlessEqual(album("~#rating"), expected)

    def test_bayesian_average(s):
        bav = bayesian_average
        l = [1, 2, 3, 4]
        a = avg(l)
        # c=0 => this becomes a mean regardless of m
        s.failUnlessEqual(a, bav(l, 0, 0))
        s.failUnlessEqual(a, bav(l, 0, 999))
        # c=1, m = a (i.e. just adding another mean score) => no effect
        s.failUnlessEqual(a, bav(l, 1, a))
        # Harder ones
        s.failUnlessEqual(20.0 / 9, bav(l, 5, 2))
        expected = 40.0 / 14
        s.failUnlessEqual(expected, bav(l, 10, 3))
        # Also check another iterable
        s.failUnlessEqual(expected, bav(tuple(l), 10, 3))

    def test_defaults(s):
        failUnlessEq = s.failUnlessEqual
        song = Fakesong({})
        album = Album(song)

        failUnlessEq(album("foo", "x"), "x")

        album.songs.add(song)

        failUnlessEq(album("~#length", "x"), song("~#length", "x"))
        failUnlessEq(album("~#bitrate", "x"), song("~#bitrate", "x"))
        failUnlessEq(album("~#rating", "x"), song("~#rating", "x"))
        failUnlessEq(album("~#playcount", "x"), song("~#playcount", "x"))
        failUnlessEq(album("~#mtime", "x"), song("~#mtime", "x"))
        failUnlessEq(album("~#year", "x"), song("~#year", "x"))

        failUnlessEq(album("~#foo", "x"), song("~#foo", "x"))
        failUnlessEq(album("foo", "x"), song("foo", "x"))
        failUnlessEq(album("~foo", "x"), song("~foo", "x"))

        failUnlessEq(album("~people", "x"), song("~people", "x"))
        failUnlessEq(album("~peoplesort", "x"), song("~peoplesort", "x"))
        failUnlessEq(album("~performer", "x"), song("~performer", "x"))
        failUnlessEq(album("~performersort", "x"), song("~performersort", "x"))

        failUnlessEq(album("~cover", "x"), song("~cover", "x"))
        failUnlessEq(album("~rating", "x"), song("~rating", "x"))

        for p in PEOPLE:
            failUnlessEq(album(p, "x"), song(p, "x"))

        for p in INTERN_NUM_DEFAULT:
            failUnlessEq(album(p, "x"), song(p, "x"))

    def test_methods(s):
        songs = [
            Fakesong({"b": "bb4\nbb1\nbb1", "c": "cc1\ncc3\ncc3"}),
            Fakesong({"b": "bb1\nbb1\nbb4", "c": "cc3\ncc1\ncc3"})
        ]

        album = Album(songs[0])
        album.songs = set(songs)

        s.failUnlessEqual(album.list("c"), ["cc3", "cc1"])
        s.failUnlessEqual(album.list("~c~b"), ["cc3", "cc1", "bb1", "bb4"])

        s.failUnlessEqual(album.comma("c"), "cc3, cc1")
        s.failUnlessEqual(album.comma("~c~b"), "cc3, cc1 - bb1, bb4")

    def tearDown(self):
        config.quit()


class TPlaylist(TestCase):
    TWO_SONGS = [
        Fakesong({"~#length": 5, "discnumber": "1", "date": "2038"}),
        Fakesong({"~#length": 7, "dummy": "d\ne", "discnumber": "2"})
    ]

    def setUp(self):
        self.temp = mkdtemp()
        self.temp2 = mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp)
        shutil.rmtree(self.temp2)

    def test_make(self):
        p1 = Playlist.new(self.temp, "Does not exist")
        self.failUnlessEqual(0, len(p1))
        self.failUnlessEqual(p1.name, "Does not exist")
        p1.delete()

    def test_rename_working(self):
        p1 = Playlist.new(self.temp, "Foobar")
        p1.rename("Foo Quuxly")
        self.failUnlessEqual(p1.name, "Foo Quuxly")
        p1.delete()

    def test_rename_nothing(self):
        p1 = Playlist.new(self.temp, "Foobar")
        self.failUnlessRaises(ValueError, p1.rename, "")
        p1.delete()

    def test_rename_dup(self):
        p1 = Playlist.new(self.temp, "Foobar")
        p2 = Playlist.new(self.temp, "Crazy")
        self.failUnlessRaises(ValueError, p2.rename, "Foobar")
        p1.delete()
        p2.delete()

    def test_make_dup(self):
        p1 = Playlist.new(self.temp, "Does not exist")
        p2 = Playlist.new(self.temp, "Does not exist")
        self.failUnlessEqual(p1.name, "Does not exist")
        self.failUnless(p2.name.startswith("Does not exist"))
        self.failIfEqual(p1.name, p2.name)
        p1.delete()
        p2.delete()

    def test_masked_handling(self):
        if os.name == "nt":
            # FIXME: masking isn't properly implemented on Windows
            return
        # playlists can contain songs and paths for masked handling..
        lib = FileLibrary("foobar")
        pl = Playlist(self.temp, "playlist", lib)
        song = Fakesong({"date": "2038", "~filename": fsnative(u"/fake")})
        song.sanitize()
        lib.add([song])

        # mask and update
        lib.mask("/")
        pl.append(song)
        pl.remove_songs([song])
        self.failUnless("/fake" in pl)

        pl.extend(self.TWO_SONGS)

        # check if collections can handle the mix
        self.failUnlessEqual(pl("date"), "2038")

        # unmask and update
        lib.unmask("/")
        pl.add_songs(["/fake"], lib)
        self.failUnless(song in pl)

        pl.delete()
        lib.destroy()

    def test_equality(s):
        pl = Playlist(s.temp, "playlist")
        pl2 = Playlist(s.temp, "playlist")
        pl3 = Playlist(s.temp2, "playlist")
        s.failUnlessEqual(pl, pl2)
        # Debatable
        s.failUnlessEqual(pl, pl3)
        pl4 = Playlist(s.temp, "foobar")
        s.failIfEqual(pl, pl4)
        pl.delete()
        pl2.delete()
        pl3.delete()
        pl4.delete()

    def test_index(s):
        pl = Playlist(s.temp, "playlist")
        songs = s.TWO_SONGS
        pl.extend(songs)
        # Just a sanity check...
        s.failUnlessEqual(1, songs.index(songs[1]))
        # And now the happy paths..
        s.failUnlessEqual(0, pl.index(songs[0]))
        s.failUnlessEqual(1, pl.index(songs[1]))
        # ValueError is what we want here
        try:
            pl.index(Fakesong({}))
            s.fail()
        except ValueError:
            pass
        pl.delete()

    def test_internal_tags(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(s.TWO_SONGS)

        s.failIfEqual(pl.comma("~long-length"), "")
        s.failIfEqual(pl.comma("~tracks"), "")
        s.failIfEqual(pl.comma("~discs"), "")
        s.failUnlessEqual(pl.comma("~foo"), "")

        s.failUnlessEqual(pl.comma(""), "")
        s.failUnlessEqual(pl.comma("~"), "")
        s.failUnlessEqual(pl.get("~#"), "")
        pl.delete()

    def test_numeric_ops(s):
        songs = NUMERIC_SONGS
        pl = Playlist(s.temp, "playlist")
        pl.extend(songs)

        s.failUnlessEqual(pl.get("~#length"), 12)
        s.failUnlessEqual(pl.get("~#length:sum"), 12)
        s.failUnlessEqual(pl.get("~#length:max"), 7)
        s.failUnlessEqual(pl.get("~#length:min"), 1)
        s.failUnlessEqual(pl.get("~#length:avg"), 4)
        s.failUnlessEqual(pl.get("~#length:foo"), 0)

        s.failUnlessEqual(pl.get("~#rating:avg"), avg([0.1, 0.3, 0.5]))

        s.failUnlessEqual(pl.get("~#filesize"), 303)

        s.failUnlessEqual(pl.get("~#added"), 7)
        s.failUnlessEqual(pl.get("~#lastplayed"), 88)
        s.failUnlessEqual(pl.get("~#bitrate"), 200)
        s.failUnlessEqual(pl.get("~#year"), 33)
        s.failUnlessEqual(pl.get("~#rating"), 0.3)
        s.failUnlessEqual(pl.get("~#originalyear"), 2002)
        pl.delete()

    def test_write(self):
        pl = Playlist(self.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        pl.extend([fsnative(u"xf0xf0")])
        pl.write()

        with open(pl.filename, "rb") as h:
            self.assertEqual(len(h.read().splitlines()),
                             len(NUMERIC_SONGS) + 1)

    def test_read(self):
        pl = Playlist(self.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        pl.write()

        lib = FileLibrary("foobar")
        lib.add(NUMERIC_SONGS)
        pl = Playlist(self.temp, "playlist", lib)
        self.assertEqual(len(pl), len(NUMERIC_SONGS))

    def test_updating_aggregates_extend(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        old_length = pl.get("~#length")
        old_size = pl.get("~#filesize")

        # Double the playlist
        pl.extend(NUMERIC_SONGS)

        new_length = pl.get("~#length")
        new_size = pl.get("~#filesize")
        s.failUnless(new_length > old_length,
                     msg="Ooops, %d <= %d" % (new_length, old_length))

        s.failUnless(new_size > old_size,
                     msg="Ooops, %d <= %d" % (new_size, old_size))

    def test_updating_aggregates_append(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        old_rating = pl.get("~#rating")

        pl.append(AMAZING_SONG)

        new_rating = pl.get("~#filesize")
        s.failUnless(new_rating > old_rating)

    def test_updating_aggregates_clear(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        s.failUnless(pl.get("~#length"))

        pl.clear()
        s.failIf(pl.get("~#length"))

    def test_updating_aggregates_remove_songs(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        s.failUnless(pl.get("~#length"))

        pl.remove_songs(NUMERIC_SONGS)
        s.failIf(pl.get("~#length"))

    def test_listlike(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        s.failUnlessEqual(NUMERIC_SONGS[0], pl[0])
        s.failUnlessEqual(NUMERIC_SONGS[1:2], pl[1:2])
        s.failUnless(NUMERIC_SONGS[1] in pl)
        pl.delete()

    def test_playlists_featuring(s):
        pl = Playlist(s.temp, "playlist")
        pl.extend(NUMERIC_SONGS)
        playlists = Playlist.playlists_featuring(NUMERIC_SONGS[0])
        s.failUnlessEqual(set(playlists), set([pl]))
        # Now add a second one, check that instance tracking works
        pl2 = Playlist(s.temp, "playlist2")
        pl2.append(NUMERIC_SONGS[0])
        playlists = Playlist.playlists_featuring(NUMERIC_SONGS[0])
        s.failUnlessEqual(set(playlists), set([pl, pl2]))
        pl.delete()
        pl2.delete()

    def test_playlists_tag(self):
        # Arguably belongs in _audio
        songs = NUMERIC_SONGS
        pl_name = "playlist 123!"
        pl = Playlist(self.temp, pl_name)
        pl.extend(songs)
        for song in songs:
            self.assertEquals(pl_name, song("~playlists"))
        pl.delete()

    def test_duplicates_single_item(self):
        pl = Playlist(self.temp, "playlist")
        pl.append(self.TWO_SONGS[0])
        self.failIf(pl.has_duplicates)
        pl.append(self.TWO_SONGS[0])
        self.failUnless(pl.has_duplicates)

    def test_duplicates(self):
        pl = Playlist(self.temp, "playlist")
        pl.extend(self.TWO_SONGS)
        pl.extend(self.TWO_SONGS)
        self.failUnlessEqual(len(pl), 4)
        self.failUnless(pl.has_duplicates,
                        ("Playlist has un-detected duplicates: %s "
                         % "\n".join([str(s) for s in pl._list])))
