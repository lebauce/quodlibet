# Copyright 2011-2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import re

from quodlibet import app
from quodlibet.plugins.events import EventPlugin


class RadioAdMute(EventPlugin):
    PLUGIN_ID = "radio_ad_mute"
    PLUGIN_NAME = _("Mute radio ads")
    PLUGIN_VERSION = "0.1"
    PLUGIN_DESC = ("Mute while radio advertisements are playing.\n"
                   "Stations: di.fm")

    SPAM = ["www.webex.co.uk",
            "di.fm/premium",
            "There's more to Digitally Imported!",
            "Digitally Imported AMTAG_60 ADWTAG_30000_START=0",
            "Digitally Imported TSTAG_60 ADWTAG",
            "PhotonVPS.com",
            "Get Digitally Imported Premium",
            "More of the show after these messages",
            "Choose premium for the best audio experience",
            "www.di.fm/jobs",
            ]

    RE_SPAM = ["Sponsored Message\s+\([0-9]+\)",
            ]

    SPAM = map(re.escape, SPAM) + RE_SPAM
    SPAM = [re.compile(s, re.I) for s in SPAM]

    __old_volume = 0
    __muted = False

    def disabled(self):
        self.plugin_on_song_ended()

    def plugin_on_song_started(self, song):
        # only check stream info songs
        if not song or not song.streamsong:
            return

        player = app.player
        data = song("~title~artist")
        for spam in self.SPAM:
            if spam.search(data):
                self.__old_volume = player.volume
                self.__muted = True
                player.volume = 0
                break

    def plugin_on_song_ended(self, *args):
        if not self.__muted:
            return
        self.__muted = False

        player = app.player
        if player.volume != 0:  # volume changed, do nothing
            return

        # restore old volume
        player.volume = self.__old_volume
