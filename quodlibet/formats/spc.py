# Copyright 2007 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

import os
import wave

import gst

from formats._audio import AudioFile

extensions = [".spc"]

if gst.registry_get_default().find_plugin("spcdec") is None:
    extensions = []

class SPCFile(AudioFile):
    format = "SPC700 DSP Data"

    def __init__(self, filename):
        self["~#length"] = 0
        self.sanitize(filename)

    def sanitize(self, filename):
        super(SPCFile, self).sanitize(filename)
        self["title"] = os.path.basename(self["~filename"])[:-4]

    def write(self):
        pass

    def can_change(self, k=None):
        if k is None: return ["artist"]
        else: return k == "artist"

info = SPCFile