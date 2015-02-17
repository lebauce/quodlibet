# -*- coding: utf-8 -*-
# Copyright 2012 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from mutagen.monkeysaudio import MonkeysAudio

from quodlibet.formats._apev2 import APEv2File


class MonkeysAudioFile(APEv2File):
    format = "Monkey's Audio"

    def __init__(self, filename):
        audio = MonkeysAudio(filename)
        super(MonkeysAudioFile, self).__init__(filename, audio)
        self["~#length"] = int(audio.info.length)
        self.sanitize(filename)

info = MonkeysAudioFile
types = [MonkeysAudioFile]
extensions = [".ape"]
