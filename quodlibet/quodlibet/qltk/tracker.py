# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#           2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import time

from gi.repository import GObject, GLib

from quodlibet import config
from quodlibet import const


class TimeTracker(GObject.GObject):
    """Emits tick every second (with up to one second jitter) as long
    as the player is activly playing.

    Uses timeout_add_seconds, so multiple instances of this should
    sync and not produce more wakeups.
    """

    __gsignals__ = {
        'tick': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, player):
        super(TimeTracker, self).__init__()

        self.__player = player
        self.__id = None
        self.__sigs = [
            player.connect("paused", self.__paused),
            player.connect("unpaused", self.__unpaused),
        ]

    def destroy(self):
        for signal_id in self.__sigs:
            self.__player.disconnect(signal_id)
        self.__source_remove()

    def __source_remove(self):
        if self.__id is not None:
            GLib.source_remove(self.__id)
            self.__id = None

    def __update(self):
        if self.__stop:
            self.__source_remove()
            return False

        self.emit("tick")
        return True

    def __paused(self, *args):
        # By removing the timeout only in the callback we are safe from
        # huge deviation caused by lots of pause/unpause actions.
        self.__stop = True

    def __unpaused(self, *args):
        self.__stop = False
        if self.__id is None:
            self.__id = GLib.timeout_add_seconds(1, self.__update)


class SongTracker(object):

    def __init__(self, librarian, player, pl):
        self.__player_ids = [
            player.connect('song-ended', self.__end, librarian, pl),
            player.connect('song-started', self.__start, librarian),
        ]
        self.__player = player
        timer = TimeTracker(player)
        timer.connect("tick", self.__timer)
        self.elapsed = 0
        self.__to_change = set()
        self.__change_id = None

    def destroy(self):
        for id_ in self.__player_ids:
            self.__player.disconnect(id_)
        self.__player = None

        if self.__change_id:
            GLib.source_remove(self.__change_id)
            self.__change_id = None

    def __changed(self, librarian, song):
        # try to combine changed events and process them if QL is idle
        self.__to_change.add(song)

        if self.__change_id is not None:
            GLib.source_remove(self.__change_id)
            self.__change_id = None

        def idle_change():
            librarian.changed(list(self.__to_change))
            self.__to_change.clear()
            self.__change_id = None

        self.__change_id = GLib.idle_add(idle_change,
                                         priority=GLib.PRIORITY_LOW)

    def __start(self, player, song, librarian):
        self.elapsed = 0
        if song is not None:
            if song.multisong:
                song["~#lastplayed"] = int(time.time())
                song["~#playcount"] = song.get("~#playcount", 0) + 1
            else:
                config.set("memory", "song", song["~filename"])
            song["~#laststarted"] = int(time.time())
            self.__changed(librarian, song)
        else:
            config.set("memory", "song", "")

    def __end(self, player, song, ended, librarian, pl):
        if song is not None and not song.multisong:
            if ended:
                config.set("memory", "seek", player.get_position())
            else:
                config.set("memory", "seek", 0)

            if self.elapsed > 0.5 * song.get("~#length", 1):
                song["~#lastplayed"] = int(time.time())
                song["~#playcount"] = song.get("~#playcount", 0) + 1
                self.__changed(librarian, song)
            elif pl.current is not song:
                if not player.error:
                    song["~#skipcount"] = song.get("~#skipcount", 0) + 1
                    self.__changed(librarian, song)
        else:
            config.set("memory", "seek", 0)

    def __timer(self, timer):
        self.elapsed += 1


class FSInterface(object):
    """Provides a file in ~/.quodlibet to indicate what song is playing."""

    def __init__(self, player):
        self._player = player
        self._ids = [
            player.connect('song-started', self.__started),
            player.connect('song-ended', self.__ended),
        ]

    def destroy(self):
        for id_ in self._ids:
            self._player.disconnect(id_)

        try:
            os.unlink(const.CURRENT)
        except EnvironmentError:
            pass

    def __started(self, player, song):
        if song:
            try:
                f = file(const.CURRENT, "w")
            except EnvironmentError:
                pass
            else:
                f.write(song.to_dump())
                f.close()

    def __ended(self, player, song, stopped):
        try:
            os.unlink(const.CURRENT)
        except EnvironmentError:
            pass
