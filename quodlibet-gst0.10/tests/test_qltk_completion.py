import os, gtk
from tests import add, TestCase
from qltk.completion import EntryWordCompletion, LibraryTagCompletion
from qltk.watcher import SongWatcher
from library import Library

class TEntryWordCompletion(TestCase):
    def test_ctr(self):
        w = EntryWordCompletion()
        e = gtk.Entry()
        e.set_completion(w)
        self.failUnlessEqual(w.get_entry(), e)
        self.failUnlessEqual(e.get_completion(), w)
        e.destroy()
add(TEntryWordCompletion)

class TLibraryTagCompletion(TestCase):
    def test_ctr(self):
        w = LibraryTagCompletion(SongWatcher(), Library()).destroy()
        e = gtk.Entry()
        e.set_completion(w)
        self.failUnlessEqual(w.get_entry(), e)
        self.failUnlessEqual(e.get_completion(), w)
        e.destroy()
add(TEntryWordCompletion)
    