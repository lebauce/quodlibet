# Copyright 2006 Federico Pelloni <federico.pelloni@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.

import dbus
import dbus.service
import dbus.glib

from dbus.dbus_bindings import DBusException

import player

class DBusHandler(dbus.service.Object):
    def __init__(self, player):
        try:
            bus = dbus.SessionBus()
            name = dbus.service.BusName('net.sacredchao.QuodLibet', bus=bus)
            path = '/net/sacredchao/QuodLibet'
            super(DBusHandler, self).__init__(name, path)
        except DBusException:
            pass
        else:
            player.connect('song-started', self.__song_started)
            player.connect('song-ended', self.__song_ended)
            player.connect('paused', lambda player: self.Paused())
            player.connect('unpaused', lambda player: self.Unpaused())

    def __dict(self, song):
        dict = {}
        for key, value in song.items():
            if isinstance(value, unicode):
                dict[key] = value.encode('utf-8')
            elif not isinstance(value, str):
                dict[key] = str(value)
        return dict

    def __song_started(self, player, song):
        if song is None:
            return
        else:
            song = self.__dict(song)
        self.SongStarted(song)

    def __song_ended(self, player, song, skipped):
        if song is None:
            return
        else:
            song = self.__dict(song)
        self.SongEnded(song, skipped)

    @dbus.service.signal('net.sacredchao.QuodLibet')
    def SongStarted(self, song):
        pass

    @dbus.service.signal('net.sacredchao.QuodLibet')
    def SongEnded(self, song, skipped):
        pass

    @dbus.service.signal('net.sacredchao.QuodLibet')
    def Paused(self): pass

    @dbus.service.signal('net.sacredchao.QuodLibet')
    def Unpaused(self):
        pass

    @dbus.service.method('net.sacredchao.QuodLibet')
    def Next(self):
        player.playlist.next()

    @dbus.service.method('net.sacredchao.QuodLibet')
    def Previous(self):
        player.playlist.previous()

    @dbus.service.method('net.sacredchao.QuodLibet')
    def Pause(self):
        player.playlist.paused = True

    @dbus.service.method('net.sacredchao.QuodLibet')
    def Play(self):
        player.playlist.paused = False

    @dbus.service.method('net.sacredchao.QuodLibet')
    def PlayPause(self):
        player.playlist.paused = not player.playlist.paused
        return player.playlist.paused