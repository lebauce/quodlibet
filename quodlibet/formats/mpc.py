# Copyright 2004-2005 Joe Wreschnig, Michael Urman
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

from formats.audio import AudioFile, AudioPlayer

try: import musepack
except ImportError: extensions = []
else: extensions = [".mpc", ".mp+"]

class MPCFile(AudioFile):
    # Map APE names to QL names. APE tags are also usually capitalized.
    # Also blacklist a number of tags.
    IGNORE = ["file", "index", "introplay", "dummy",
              "replaygain_track_peak", "replaygain_album_peak",
              "replaygain_track_gain", "replaygain_album_gain"]
    TRANS = { "subtitle": "version",
              "track": "tracknumber",
              "catalog": "labelid",
              "year": "date",
              "record location": "location"
              }
    SNART = dict([(v, k) for k, v in TRANS.iteritems()])
    
    def __init__(self, filename):
        tag = musepack.APETag(filename)
        for key, value in tag:
            key = MPCFile.TRANS.get(key.lower(), key.lower())
            if (value.kind == musepack.apev2.TEXT and
                key not in MPCFile.IGNORE):
                self[key] = "\n".join(list(value))
        f = musepack.MPCFile(filename)
        self["~#length"] = int(f.length / 1000)
        self.sanitize(filename)

    def can_change(self, key = None):
        if key is None: return True
        else: return (AudioFile.can_change(self, key) and
                      key not in MPCFile.IGNORE)

    def write(self):
        import musepack
        tag = musepack.APETag(self['~filename'])

        keys = tag.keys()
        for key in keys:
            # remove any text keys we read in
            value = tag[key]
            if (value.kind == musepack.apev2.TEXT and
                key not in MPCFile.IGNORE):
                del(tag[key])
        for key in self.realkeys():
            value = self[key]
            key = MPCFile.SNART.get(key, key)
            if key in ["isrc", "isbn", "ean/upc"]: key = key.upper()
            else: key = key.title()
            tag[key] = value.split("\n")
        tag.write()
        self.sanitize()

class MPCPlayer(AudioPlayer):
    def __init__(self, dev, song):
        AudioPlayer.__init__(self)
        self.audio = musepack.MPCFile(song["~filename"])
        self.length = self.audio.length
        self.pos = 0
        self.dev = dev
        self.dev.set_info(self.audio.frequency, 2)

    def __iter__(self): return self

    def seek(self, ms):
        self.audio.seek(ms)
        self.pos = ms

    def next(self):
        if self.stopped: raise StopIteration
        else:
            s = self.audio.read()
            if s: self.dev.play(s)
            else: raise StopIteration
        return int(self.audio.position)

info = MPCFile
player = MPCPlayer
