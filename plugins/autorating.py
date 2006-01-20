# Copyright 2005 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

class AutoRating(object):
    PLUGIN_NAME = "Automatic Rating"
    PLUGIN_VERSION = "0.1"
    PLUGIN_DESC = ("Rate songs automatically when they are played or "
                   "skipped. This uses the 'accelerated' algorithm from "
                   "vux by Brian Nelson.")

    def plugin_on_song_ended(self, song, skipped):
        rating = song["~#rating"]
        invrating = 1.0 - rating
        delta = min(rating, invrating) / 2.0
        if skipped: rating -= delta
        else: rating += delta
        song["~#rating"] = rating