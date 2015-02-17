# -*- coding: utf-8 -*-
# Copyright 2009-2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import tempfile
import hashlib

from gi.repository import GdkPixbuf, GLib

from quodlibet.const import USERDIR
from quodlibet.util.path import mtime, mkdir, pathname2url, \
    xdg_get_cache_home, is_fsnative
from quodlibet.util import enum
from quodlibet.qltk.image import scale


def get_thumbnail_folder():
    """Returns a path to the thumbnail folder.

    The returned path might not exist.
    """

    if os.name == "nt":
        thumb_folder = os.path.join(USERDIR, "thumbnails")
    else:
        cache_folder = os.path.join(xdg_get_cache_home(), "thumbnails")
        thumb_folder = os.path.expanduser('~/.thumbnails')
        if os.path.exists(cache_folder) or not os.path.exists(thumb_folder):
            thumb_folder = cache_folder

    return thumb_folder


@enum
class ThumbSize(object):
    NORMAL = 128
    LARGE = 256
    LARGEST = LARGE


def get_cache_info(path, boundary):
    """For an image at `path` return (cache_path, thumb_size)

    cache_path points to a potential cache file
    thumb size is either 128 or 256
    """

    assert is_fsnative(path)

    width, height = boundary

    if width <= ThumbSize.NORMAL and height <= ThumbSize.NORMAL:
        size_name = "normal"
        thumb_size = ThumbSize.NORMAL
    else:
        size_name = "large"
        thumb_size = ThumbSize.LARGE

    thumb_folder = get_thumbnail_folder()
    cache_dir = os.path.join(thumb_folder, size_name)

    uri = "file://" + pathname2url(path)
    thumb_name = hashlib.md5(uri).hexdigest() + ".png"
    thumb_path = os.path.join(cache_dir, thumb_name)

    return (thumb_path, thumb_size)


def get_thumbnail_from_file(fileobj, boundary):
    """Like get_thumbnail() but works with files that can't be reopened.

    This is needed on Windows where NamedTemporaryFile can't be reopened.

    Returns Pixbuf or None. Thread-safe.
    """

    assert fileobj

    try:
        path = fileobj.name
        assert is_fsnative(path), path
        return get_thumbnail(path, boundary)
    except GLib.GError:
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.set_size(*boundary)
            loader.write(fileobj.read())
            loader.close()
            fileobj.seek(0, 0)
            # can return None in case of partial data
            return loader.get_pixbuf()
        except (GLib.GError, EnvironmentError):
            pass


def get_thumbnail(path, boundary):
    """Get a thumbnail pixbuf of an image at `path`.

    Will create/use a thumbnail in the user's thumbnail directory if possible.
    Follows the Free Desktop specification:

    http://specifications.freedesktop.org/thumbnail-spec/

    Can raise GLib.GError. Thread-safe.
    """

    width, height = boundary
    new_from_file_at_size = GdkPixbuf.Pixbuf.new_from_file_at_size

    # larger than thumbnails, load directly
    if width > ThumbSize.LARGEST or height > ThumbSize.LARGEST:
        return new_from_file_at_size(path, width, height)

    path_mtime = mtime(path)
    if path_mtime == 0:
        return new_from_file_at_size(path, width, height)

    # embedded thumbnails come from /tmp/
    # FIXME: move this to another layer
    if path.startswith(tempfile.gettempdir()):
        return new_from_file_at_size(path, width, height)

    thumb_path, thumb_size = get_cache_info(path, boundary)
    cache_dir = os.path.dirname(thumb_path)
    try:
        mkdir(cache_dir, 0700)
    except OSError:
        return new_from_file_at_size(path, width, height)

    try:
        pb = new_from_file_at_size(thumb_path, width, height)
    except GLib.GError:
        # in case it fails to load, we recreate it
        pass
    else:
        meta_mtime = pb.get_option("tEXt::Thumb::MTime")
        if meta_mtime is not None:
            try:
                meta_mtime = int(meta_mtime)
            except ValueError:
                pass
            else:
                if meta_mtime == int(path_mtime):
                    return pb

    info, pw, ph = GdkPixbuf.Pixbuf.get_file_info(path)

    # Too small picture, no thumbnail needed
    if pw < thumb_size and ph < thumb_size:
        return new_from_file_at_size(path, width, height)

    thumb_pb = new_from_file_at_size(path, thumb_size, thumb_size)

    uri = "file://" + pathname2url(path)
    mime = info.get_mime_types()[0]
    options = {
        "tEXt::Thumb::Image::Width": str(pw),
        "tEXt::Thumb::Image::Height": str(ph),
        "tEXt::Thumb::URI": uri,
        "tEXt::Thumb::MTime": str(int(path_mtime)),
        "tEXt::Thumb::Size": str(os.path.getsize(path)),
        "tEXt::Thumb::Mimetype": mime,
        "tEXt::Software": "QuodLibet"
    }

    thumb_pb.savev(thumb_path, "png", options.keys(), options.values())
    try:
        os.chmod(thumb_path, 0600)
    except OSError:
        pass

    return scale(thumb_pb, boundary)
