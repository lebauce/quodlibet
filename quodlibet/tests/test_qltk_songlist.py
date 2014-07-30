from tests import TestCase

from quodlibet.library import SongLibrary
from quodlibet.qltk.songlist import SongList, set_columns, get_columns
from quodlibet.formats._audio import AudioFile
from quodlibet import config


class TSongList(TestCase):
    HEADERS = ["acolumn", "~#lastplayed", "~foo~bar", "~#rating",
               "~#length", "~dirname", "~#track"]

    def setUp(self):
        config.init()
        self.songlist = SongList(SongLibrary())

        self.orders_changed = 0

        def orders_changed_cb(*args):
            self.orders_changed += 1

        self.songlist.connect("orders-changed", orders_changed_cb)

    def test_set_all_column_headers(self):
        SongList.set_all_column_headers(self.HEADERS)
        headers = [col.header_name for col in self.songlist.get_columns()]
        self.failUnlessEqual(headers, self.HEADERS)

    def test_set_column_headers(self):
        self.songlist.set_column_headers(self.HEADERS)
        headers = [col.header_name for col in self.songlist.get_columns()]
        self.failUnlessEqual(headers, self.HEADERS)

    def test_drop(self):
        self.songlist.enable_drop()
        self.songlist.disable_drop()

    def test_sort_by(self):
        self.songlist.set_column_headers(["one", "two", "three"])
        for key, order in [("one", True),
                           ("two", False),
                           ("three", False)]:
            self.songlist.set_sort_orders([(key, order)])
            self.failUnlessEqual(
                self.songlist.get_sort_orders(), [(key, order)])

        self.songlist.toggle_column_sort(self.songlist.get_columns()[-1])
        self.failUnlessEqual(
            self.songlist.get_sort_orders(), [("three", True)])

    def test_sort_orders(self):
        s = self.songlist

        s.set_column_headers(["foo", "quux", "bar"])
        values = [("foo", True), ("bar", False)]
        s.set_sort_orders(values)
        self.assertEqual(s.get_sort_orders(), values)

        s.toggle_column_sort(s.get_columns()[1], replace=False)
        self.assertEqual(s.get_sort_orders(), values + [("quux", False)])

        s.toggle_column_sort(s.get_columns()[1], replace=True)
        self.assertEqual(s.get_sort_orders(), [("quux", False)])

    def test_toggle_sort(self):
        s = self.songlist

        s.set_column_headers(["foo"])
        self.assertEqual(self.orders_changed, 1)
        s.toggle_column_sort(s.get_columns()[0], replace=True)
        self.assertEqual(self.orders_changed, 2)
        self.assertEqual(s.get_sort_orders(), [("foo", False)])
        s.toggle_column_sort(s.get_columns()[0], replace=True)
        self.assertEqual(self.orders_changed, 3)
        self.assertEqual(s.get_sort_orders(), [("foo", True)])

    def test_clear_sort(self):
        s = self.songlist
        s.set_column_headers(["foo"])
        s.toggle_column_sort(s.get_columns()[0], replace=True)
        self.assertTrue(s.get_sort_orders())
        s.clear_sort()
        self.assertFalse(s.get_sort_orders())

    def test_not_sortable(self):
        s = self.songlist
        s.sortable = False
        s.set_column_headers(["foo"])
        s.toggle_column_sort(s.get_columns()[0])
        self.assertEqual(self.orders_changed, 0)
        self.assertFalse(s.get_sort_orders())

    def test_find_default_sort_column(self):
        s = self.songlist
        self.assertTrue(s.find_default_sort_column() is None)
        s.set_column_headers(["~#track"])
        self.assertTrue(s.find_default_sort_column())

    def test_inline_search_state(self):
        self.assertEqual(self.songlist.get_search_column(), 0)
        self.assertTrue(self.songlist.get_enable_search())

    def test_set_songs(self):
        self.songlist.set_songs([], sorted=True)
        self.songlist.set_songs([], sorted=False)

    def test_add_songs(self):
        song = AudioFile({"~filename": "/dev/null"})

        # unsorted
        self.songlist.add_songs([song])
        self.songlist.add_songs([song])

        # sorted
        self.songlist.set_column_headers(["foo"])
        self.songlist.toggle_column_sort(self.songlist.get_columns()[0])
        self.songlist.add_songs([])
        self.songlist.add_songs([song])
        self.songlist.add_songs([song])

        self.assertEqual(self.songlist.get_songs(), [song] * 4)

    def test_header_menu(self):
        from quodlibet import browsers
        from quodlibet.library import SongLibrary, SongLibrarian

        song = AudioFile({"~filename": "/dev/null"})
        song.sanitize()
        self.songlist.set_songs([song])

        library = SongLibrary()
        library.librarian = SongLibrarian()
        browser = browsers.get("EmptyBar")(library, True)

        self.songlist.set_column_headers(["foo"])

        self.assertFalse(self.songlist.Menu("foo", browser, library))
        sel = self.songlist.get_selection()
        sel.select_all()
        self.assertTrue(self.songlist.Menu("foo", browser, library))

    def test_get_columns_migrates(self):
        self.failIf(config.get("settings", "headers", None))
        self.failIf(config.get("settings", "columns", None))

        headers = "~album ~#replaygain_track_gain foobar"
        config.set("settings", "headers", headers)
        columns = get_columns()
        self.failUnlessEqual(columns, ["~album", "~#replaygain_track_gain",
                                       "foobar"])
        self.failIf(config.get("settings", "headers", None))

    def test_get_set_columns(self):
        self.failIf(config.get("settings", "headers", None))
        self.failIf(config.get("settings", "columns", None))
        columns = ["first", "won't", "two words", "4"]
        set_columns(columns)
        self.failUnlessEqual(columns, get_columns())
        columns += ["~~another~one"]
        set_columns(columns)
        self.failUnlessEqual(columns, get_columns())
        self.failIf(config.get("settings", "headers", None))

    def tearDown(self):
        self.songlist.destroy()
        config.quit()
