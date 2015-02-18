# -*- coding: utf-8 -*-
# Copyright 2013 Simonas Kazlauskas
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os.path
import re

from quodlibet.plugins.cover import CoverSourcePlugin
from quodlibet.util.path import fsdecode
from quodlibet import config


class EmbedCover(CoverSourcePlugin):
    PLUGIN_ID = "embed-cover"
    PLUGIN_NAME = _("Embed cover")
    PLUGIN_DESC = _("Uses covers embedded into audio files.")

    embedded = True

    @classmethod
    def group_by(cls, song):
        # one group per song
        return song.key

    @staticmethod
    def priority():
        return 0.7001

    @property
    def cover(self):
        if self.song.has_images:
            image = self.song.get_primary_image()
            return image.file if image else None


class FilesystemCover(CoverSourcePlugin):
    PLUGIN_ID = "filesystem-cover"
    PLUGIN_NAME = _("Filesystem cover")
    PLUGIN_DESC = _("Uses commonly named images found in common directories " +
                    "alongside the song.")

    cover_subdirs = frozenset(
        ["scan", "scans", "images", "covers", "artwork"])
    cover_exts = frozenset(["jpg", "jpeg", "png", "gif"])

    cover_positive_words = ["front", "cover", "frontcover", "jacket",
                            "folder", "albumart", "edited"]
    cover_positive_regexes = frozenset(
        map(lambda s: re.compile(r'(\b|_)' + s + r'(\b|_)'),
                                 cover_positive_words))
    cover_negative_regexes = frozenset(
        map(lambda s: re.compile(r'(\b|_|)' + s + r'(\b|_)'),
            ["back", "inlay", "inset", "inside"]))

    @classmethod
    def group_by(cls, song):
        # in the common case this means we only search once per album
        return (song('~dirname'), song.album_key)

    @staticmethod
    def priority():
        return 0.80

    @property
    def cover(self):
        # TODO: Deserves some refactoring
        if not self.song.is_file:
            return None

        base = self.song('~dirname')
        images = []

        # Issue 374: Specify artwork filename
        if config.getboolean("albumart", "force_filename"):
            path = os.path.join(base, config.get("albumart", "filename"))
            if os.path.isfile(path):
                images = [(100, path)]
        else:
            get_ext = lambda s: os.path.splitext(s)[1].lstrip('.')

            entries = []
            try:
                entries = os.listdir(base)
            except EnvironmentError:
                pass

            fns = []
            for entry in entries:
                lentry = entry.lower()
                if get_ext(lentry) in self.cover_exts:
                    fns.append((None, entry))
                if lentry in self.cover_subdirs:
                    subdir = os.path.join(base, entry)
                    sub_entries = []
                    try:
                        sub_entries = os.listdir(subdir)
                    except EnvironmentError:
                        pass
                    for sub_entry in sub_entries:
                        lsub_entry = sub_entry.lower()
                        if get_ext(lsub_entry) in self.cover_exts:
                            fns.append((entry, sub_entry))

            for sub, fn in fns:
                dec_lfn = fsdecode(fn, False).lower()

                score = 0
                # check for the album label number
                labelid = self.song.get("labelid", "").lower()
                if labelid and labelid in dec_lfn:
                    score += 20

                # Track-related keywords
                keywords = [k.lower().strip() for k in [self.song("artist"),
                            self.song("albumartist"), self.song("album")]
                            if len(k) > 1]
                score += 2 * sum(map(dec_lfn.__contains__, keywords))

                # Generic keywords
                score += 3 * sum(r.search(dec_lfn) is not None
                                 for r in self.cover_positive_regexes)

                negs = sum(r.search(dec_lfn) is not None
                           for r in self.cover_negative_regexes)
                score -= 2 * negs
                #print("[%s - %s]: Album art \"%s\" scores %d (%s neg)." % (
                #        self("artist"), self("title"), fn, score, negs))
                if score > 0:
                    if sub is not None:
                        fn = os.path.join(sub, fn)
                    images.append((score, os.path.join(base, fn)))
            images.sort(reverse=True)

        for score, path in images:
            # could be a directory
            if not os.path.isfile(path):
                continue
            try:
                return file(path, "rb")
            except IOError:
                print_w("Failed reading album art \"%s\"" % path)

        return None
