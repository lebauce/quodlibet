# -*- coding: utf-8 -*-
from tests import TestCase, init_fake_app, destroy_fake_app
from helper import capture_output

from gi.repository import Gtk

from quodlibet import config
from quodlibet import app

from quodlibet.commands import registry


class TCommands(TestCase):
    def setUp(self):
        config.init()
        init_fake_app()

    def tearDown(self):
        destroy_fake_app()
        config.quit()

    def __send(self, command):
        return registry.handle_line(app, command)

    def test_player(self):
        self.__send("previous")
        self.__send("force-previous")
        self.__send("next")
        self.__send("pause")
        self.__send("play-pause")
        self.__send("play")
        self.__send("stop")
        self.__send("volume +1000")
        self.__send("volume 40")
        self.__send("volume -10")

        self.__send("seek -10")
        self.__send("seek +10")
        self.__send("seek 0")

    def test_misc(self):
        with capture_output():
            self.__send("play-file /dev/null")
        self.__send("dump-playlist")
        self.__send("dump-queue")
        self.__send("enqueue /dev/null")
        self.__send("enqueue-files /dev/null")
        self.__send("filter album=test")
        self.__send("query '/foobar/'")
        self.__send("focus")
        self.__send("hide-window")
        self.__send("dump-browsers")
        self.__send("open-browser SearchBar")
        from quodlibet.qltk.browser import LibraryBrowser
        for window in Gtk.Window.list_toplevels():
            if isinstance(window, LibraryBrowser):
                window.destroy()
        self.__send("order shuffle")
        self.__send("properties")
        self.__send("queue 1")
        self.__send("quit")
        self.__send("random album")
        self.__send("refresh")
        self.__send("repeat 0")
        self.__send("set-browser 1")
        self.__send("set-rating 0.5")
        self.__send("show-window")
        self.__send("song-list 1")
        self.__send("status")
        self.__send("toggle-window")
        self.__send("unqueue /dev/null")
