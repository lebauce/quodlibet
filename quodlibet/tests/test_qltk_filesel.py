# -*- coding: utf-8 -*-
from tests import TestCase, mkdtemp

import os
import sys
sys.modules['dircache'] = os # cheat the dircache effects

from quodlibet.qltk.filesel import DirectoryTree, FileSelector, get_drives
from quodlibet.qltk.filesel import MainDirectoryTree, MainFileSelector
from quodlibet.util.path import fsnative, is_fsnative
from quodlibet import const
import quodlibet.config


class TDirectoryTree(TestCase):

    if os.name == "nt":
        ROOTS = [const.HOME, u"C:\\"]
    else:
        ROOTS = [const.HOME, "/"]

    def setUp(self):
        quodlibet.config.init()

    def tearDown(self):
        quodlibet.config.quit()

    def test_initial(self):
        paths = ["/", const.HOME, "/usr/bin"]
        if os.name == "nt":
            paths = [u"C:\\", const.HOME]

        for path in paths:
            dirlist = DirectoryTree(path, folders=self.ROOTS)
            model, rows = dirlist.get_selection().get_selected_rows()
            selected = [model[row][0] for row in rows]
            dirlist.destroy()
            self.failUnlessEqual([path], selected)

    def test_bad_initial(self):
        invalid = os.path.join("bin", "file", "does", "not", "exist")
        for path in self.ROOTS:
            newpath = os.path.join(path, invalid)
            dirlist = DirectoryTree(newpath, folders=self.ROOTS)
            selected = dirlist.get_selected_paths()
            dirlist.destroy()
            # select the last valid parent directory
            self.assertEqual(len(selected), 1)
            self.assertTrue(selected[0].startswith(path))

    def test_bad_go_to(self):
        newpath = fsnative(u"/woooooo/bar/fun/broken")
        dirlist = DirectoryTree(fsnative(u"/"), folders=self.ROOTS)
        dirlist.go_to(newpath)
        dirlist.destroy()

    def test_main(self):
        folders = ["/"]
        if os.name == "nt":
            folders = [u"C:\\"]
        main = MainDirectoryTree(folders=folders)
        self.assertTrue(len(main.get_model()))

        main = MainDirectoryTree()
        self.assertTrue(len(main.get_model()))

    def test_get_drives(self):
        for path in get_drives():
            self.assertTrue(is_fsnative(path))


class TFileSelector(TestCase):

    def setUp(self):
        quodlibet.config.init()
        self.ROOTS = [mkdtemp(), mkdtemp()]
        self.INITIAL = self.ROOTS[0]
        self.PATHS = [
            os.path.join(self.ROOTS[0], "a"),
            os.path.join(self.ROOTS[0], "b"),
        ]

        for path in self.PATHS:
            open(path, "wb").close()

        self.fs = FileSelector(
            initial=self.INITIAL, filter=(lambda s: s in self.PATHS),
            folders=self.ROOTS)
        self.fs.connect('changed', self._changed)
        self.files = None
        self.fs.rescan()

    def tearDown(self):
        self.fs.destroy()
        quodlibet.config.quit()

        for file_ in self.PATHS:
            os.unlink(file_)
        for dir_ in self.ROOTS:
            os.rmdir(dir_)

    def _changed(self, fs, selection):
        self.selection = selection
        self.files = fs.get_selected_paths()
        self.files.sort()

    def test_select(self):
        expected = self.PATHS
        expected.sort()

        self.selection.select_all()
        self.assertEqual(self.files, expected)

    def test_select_rescan(self):
        expected = self.PATHS
        expected.sort()

        self.selection.select_all()
        self.assertEqual(self.files, expected)

        files_prev = self.fs.get_selected_paths()
        self.fs.rescan()
        self.assertEqual(self.files, expected)
        self.assertEqual(self.files, files_prev)

    def test_main(self):
        MainFileSelector()
