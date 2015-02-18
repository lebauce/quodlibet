# -*- coding: utf-8 -*-
# Copyright 2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from ._audio import AudioFile

extensions = [".aac", ".adif", ".adts"]
try:
    # since mutagen 1.27
    from mutagen.aac import AAC
except ImportError:
    extensions = []


class AACFile(AudioFile):
    """ADTS/ADIF files"""

    format = "AAC"
    mimes = ["audio/x-aac"]
    fill_length = True

    def __init__(self, filename):
        audio = AAC(filename)
        self["~#length"] = audio.info.length
        self["~#bitrate"] = int(audio.info.bitrate / 1000)
        self.sanitize(filename)

    def write(self):
        pass

    def reload(self, *args):
        title = self.get("title")
        super(AACFile, self).reload(*args)
        if title is not None:
            self.setdefault("title", title)

    def can_change(self, k=None):
        if k is None:
            return ["title"]
        else:
            return k == "title"


info = AACFile
types = [AACFile]
