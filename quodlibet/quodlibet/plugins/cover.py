# -*- coding: utf-8 -*-
# Copyright 2013 Simonas Kazlauskas
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from os import path, makedirs
from hashlib import sha1

from gi.repository import GObject

from quodlibet.util.path import escape_filename, xdg_get_cache_home


class CoverSourcePlugin(GObject.Object):
    """
    Plugins that given a song should provide a cover art.

    The plugin should override following methods and properties:

        @staticmethod priority()
        @property cover_path(self)
        fetch_cover(self)

    Refer to default function implementation's documentation in order to
    understand their role.
    """

    __gsignals__ = {
        'fetch-success': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'fetch-failure': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'search-complete': (GObject.SignalFlags.RUN_LAST, None, (object,))
    }

    embedded = False
    """Whether the source is an embedded one"""

    def __init__(self, song, cancellable=None):
        self.song = song
        self.cancellable = cancellable
        super(CoverSourcePlugin, self).__init__()

    @classmethod
    def group_by(cls, song):
        """Returns a hashable for a song, for grouping songs in groups where
        only one song per group needs to be searched.

        Grouping might reduce the chance of finding covers in exchange
        for performance.

        This default implementation gives one group for all songs.
        """

        return

    @staticmethod
    def priority():
        """
        Should return float in range [0.0, 1.0] suggesting priority of the
        cover source. Whether value returned by this method is respected or
        not is not guaranteed.

        As a rule of thumb, source's reliability and quality should be
        compared with other sources and given score between two sources that
        come close in quality and reliability.

        There's a table of value ranges sources should respect:

        * (0.7, 1.0] - local covers;
        * (0.4, 0.7] - accurate (> 99%) source of high quality (>= 200x200)
                       covers;
        * (0.2, 0.4] - accurate (> 99%) source of low quality (< 200x200)
                       covers;
        * (0.0, 0.2] - not very accurate (<= 99%) source of covers, even if
                       they're high quality;
        *  0.0       - reserved for the fallback cover source.
        """
        return 0.0

    @property
    def cover_directory(self):
        return cover_dir

    @property
    def cover_filename(self):
        """
        Return the filename of the cover which hopefully should not change
        between songs in the same album and still be unique enough to
        uniquely identify most (or even better – all) of the albums.

        The string returned must not contain any characters illegal in
        most common filesystems. These include /, ?, <, >, \, :, *, |, ” and ^.
        Staying in the bounds of ASCII is highly encouraged.

        Perchance the song lacks data to generate the filename of cover for
        this provider, None shall be returned.
        """
        key = sha1()
        # Should be fine as long as the same interpreter is used.
        key.update(repr(self.song.album_key))
        return escape_filename(key.hexdigest())

    @property
    def cover_path(self):
        """
        Should return the path where cover is expected to be cached. The
        location should be based in common cache location available in variable
        `cover_dir` of this module.

        It doesn't necessarily mean the cover is actually at the returned
        location neither that it will be stored there at any later time.
        """
        return path.join(self.cover_directory, self.cover_filename)

    @property
    def cover(self):
        """
        Method to get cover file from cover provider for a specific song.

        Should always return a file-like object opened as read-only if any
        and None otherwise.
        """
        cp = self.cover_path
        try:
            return open(cp, 'rb') if cp and path.isfile(cp) else None
        except IOError:
            print_w('Failed reading album art "%s"'.format(path))

    def search(self):
        """
        Start searching for cover art from a source.

        After search is completed the `search-complete` event must be emitted
        regardless of search outcome with a list of dictionaries containing
        `album`, `artist` and `cover` keys as an argument. If search was
        unsuccessful, empty list should be returned.

        By convention better quality and more accurate covers are expected to
        appear first in the list.
        """
        self.emit('search-complete', [])

    def fetch_cover(self):
        """
        Method to ask source fetch the cover from its source into location at
        `self.cover_path`.

        If this method succeeds in putting the image from its source into
        `self.cover_path`, `fetch-success` signal shall be emitted and
        `fetch-failure` otherwise.

        Return value of this function doesn't have any meaning whatsoever.
        """
        self.fail('This source is incapable of fetching covers')

    def fail(self, message):
        """
        Shorthand method for emitting `fetch-failure` signals.

        Most common use pattern would be:
            return self.fail("Failure message")
        """
        self.emit('fetch-failure', message)


cover_dir = path.join(xdg_get_cache_home(), 'quodlibet', 'covers')

try:
    makedirs(cover_dir)
except OSError:
    pass
