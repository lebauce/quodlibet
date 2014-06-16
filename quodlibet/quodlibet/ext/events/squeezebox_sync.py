# Copyright 2011-2014 Nick Boultbee
#
# Inspired in parts by PySqueezeCenter (c) 2010 JingleManSweep
# SqueezeCenter and SqueezeBox are copyright Logitech
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk
import os

from quodlibet import qltk, app
from quodlibet.ext._shared.squeezebox.base import SqueezeboxPluginMixin
from quodlibet.util.dprint import print_d
from quodlibet.plugins.events import EventPlugin


if os.name == "nt":
    from quodlibet.plugins import PluginNotSupportedError
    raise PluginNotSupportedError


class SqueezeboxSyncPlugin(EventPlugin, SqueezeboxPluginMixin):
    PLUGIN_ID = 'Squeezebox Output'
    PLUGIN_NAME = _('Squeezebox Sync')
    PLUGIN_DESC = _("Make Logitech Squeezebox mirror Quod Libet output, "
                    "provided both read from an identical library")
    PLUGIN_ICON = Gtk.STOCK_MEDIA_PLAY
    PLUGIN_VERSION = '0.4'
    server = None
    active = False
    _debug = False

    def __init__(self):
        super(EventPlugin, self).__init__()
        super(SqueezeboxPluginMixin, self).__init__()

    @classmethod
    def post_reconnect(cls):
        cls.server.stop()
        SqueezeboxPluginMixin.post_reconnect()
        player = app.player
        cls.plugin_on_song_started(player.info)
        cls.plugin_on_seek(player.info, player.get_position())

    def enabled(self):
        print_d("Debug is set to %s" % self._debug)
        self.active = True
        self.init_server()
        self.server.pause()
        if not self.server.is_connected:
            qltk.ErrorMessage(
                None,
                _("Error finding Squeezebox server"),
                _("Error finding %s. Please check settings") %
                self.server.config
            ).run()

    def disabled(self):
        # Stopping might be annoying in some situations, but seems more correct
        if self.server:
            self.server.stop()
        self.active = False

    @classmethod
    def plugin_on_song_started(cls, song):
        # Yucky hack to allow some form of immediacy on re-configuration
        cls.server._debug = cls._debug = cls.config_get_bool("debug", False)
        if cls._debug:
            print_d("Paused" if app.player.paused else "Not paused")
        if song and cls.server and cls.server.is_connected:
            path = cls.get_sb_path(song)
            print_d("Requesting to play %s..." % path)
            if app.player.paused:
                cls.server.change_song(path)
            else:
                cls.server.playlist_play(path)

    @classmethod
    def plugin_on_paused(cls):
        if cls.server:
            cls.server.pause()

    @classmethod
    def plugin_on_unpaused(cls):
        if cls.server:
            cls.server.unpause()

    @classmethod
    def plugin_on_seek(cls, song, msec):
        if not app.player.paused:
            if cls.server:
                cls.server.seek_to(msec)
                cls.server.play()
