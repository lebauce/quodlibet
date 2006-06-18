# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

from plugins.events import EventPlugin

class IRadioLog(EventPlugin):
    PLUGIN_NAME = "Internet Radio Log"
    PLUGIN_DESC = ("Record the last 10 songs played on radio stations, "
                   "and list them in the seek context menu.")
    PLUGIN_ICON = 'gtk-edit'
    PLUGIN_VERSION = "0.21"

    def plugin_on_song_started(self, song):
        if song is None: return

        from player import playlist as player

        if player.song.multisong and not song.multisong:
            time = player.get_position()
            title = song("title")
            bookmarks = player.song.bookmarks
            bookmarks.append([time // 1000, title])
            try: bookmarks.pop(-10)
            except IndexError: pass
            player.song.bookmarks = bookmarks
        elif song.multisong:
            song.bookmarks = []