# -*- coding: utf-8 -*-
# Copyright 2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import shutil
import StringIO
import mutagen

from tests import TestCase, DATA_DIR, mkstemp
from quodlibet.formats.mp4 import MP4File
from quodlibet.formats._image import EmbeddedImage

import mutagen.mp4


class TMP4File(TestCase):

    def setUp(self):
        fd, self.f = mkstemp(".m4a")
        os.close(fd)
        shutil.copy(os.path.join(DATA_DIR, 'test.m4a'), self.f)
        self.song = MP4File(self.f)

    def tearDown(self):
        os.unlink(self.f)

    def test_format(self):
        if mutagen.version >= (1, 27):
            self.assertEqual(self.song("~format"), "MPEG-4 AAC LC")
        else:
            self.assertEqual(self.song("~format"), "MPEG-4 AAC")

    def test_basic(self):
        self.song["title"] = u"SomeTestValue"
        self.song.write()
        self.song.reload()
        self.assertEqual(self.song("title"), u"SomeTestValue")

    def test_length(self):
        self.assertEqual(self.song("~#length"), 3)

    def test_bitrate(self):
        self.assertEqual(self.song("~#bitrate"), 2)

    def test_write(self):
        self.song.write()

    def test_can_change(self):
        self.assertTrue(self.song.can_change("title"))
        self.assertFalse(self.song.can_change("foobar"))
        self.assertTrue("albumartist" in self.song.can_change())

    def test_invalid(self):
        path = os.path.join(DATA_DIR, 'empty.xm')
        self.assertTrue(os.path.exists(path))
        self.assertRaises(Exception, MP4File, path)

    def test_get_image(self):
        image = self.song.get_primary_image()
        self.assertTrue(image)
        self.assertEqual(image.mime_type, "image/png")

    def test_get_images(self):
        images = self.song.get_images()
        self.assertTrue(images and len(images) == 2)

    def test_get_image_non(self):
        tag = mutagen.mp4.MP4(self.f)
        tag.pop("covr", None)
        tag.save()
        self.song.reload()

        self.assertFalse(self.song.get_primary_image())

    def test_clear_images(self):
        self.assertTrue(self.song.valid())
        self.assertTrue(self.song.has_images)
        self.song.clear_images()
        self.assertFalse(self.song.has_images)
        self.assertFalse(self.song.get_primary_image())

        tag = mutagen.mp4.MP4(self.f)
        self.assertFalse("covr" in tag)

    def test_set_image(self):
        self.assertTrue(self.song.has_images)
        fileobj = StringIO.StringIO("foo")
        image = EmbeddedImage(fileobj, "image/jpeg", 10, 10, 8)
        self.song.set_image(image)
        image = self.song.get_primary_image()
        self.assertTrue(image)
        self.assertEqual(image.file.read(), "foo")
        self.assertTrue(self.song.has_images)

    def test_can_change_images(self):
        self.assertTrue(self.song.can_change_images)

    def test_can_multiple_values(self):
        self.assertEqual(self.song.can_multiple_values(), [])
        self.assertFalse(self.song.can_multiple_values("artist"))
