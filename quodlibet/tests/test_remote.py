# -*- coding: utf-8 -*-
from tests import TestCase
from helper import temp_filename

from quodlibet.remote import QuodLibetUnixRemote


class Mock(object):
    def __init__(self, resp=None):
        self.lines = []
        self.resp = resp

    def handle_line(self, app, line):
        self.lines.append(line)
        return self.resp


class TUnixRemote(TestCase):

    def test_fifo(self):
        mock = Mock()
        remote = QuodLibetUnixRemote(None, mock)
        remote._callback(b"foo\n")
        remote._callback(b"bar\nbaz")
        self.assertEqual(mock.lines, [b"foo", b"bar", b"baz"])

    def test_response(self):
        with temp_filename() as fn:
            mock = Mock(resp=b"resp")
            remote = QuodLibetUnixRemote(None, mock)
            remote._callback(b"foo\x00%s" % fn)
            self.assertEqual(mock.lines, [b"foo"])
            with open(fn, "rb") as h:
                self.assertEqual(h.read(), b"resp")
