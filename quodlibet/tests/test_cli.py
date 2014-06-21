# Copyright 2014 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import sys

from helper import capture_output
from quodlibet import cli
from tests import TestCase


def call_safely(func, *args, **kwargs):
    """
    Calls a function with arbitrary args,
    returning a tuple (return code, stdout, stderr).

    `ret_code` is a string sometimes here.

    Safe for QL-style SystemExits.
    """
    with capture_output() as (out, err):
        try:
            ret_code = func(*args, **kwargs)
        except SystemExit as e:
            ret_code = e.code
    return ret_code, out.getvalue(), err.getvalue()


class Tcli(TestCase):

    def test_process_no_arguments_works(self):
        code, out, err = call_safely(cli.process_arguments)
        self.failIf(code, msg="Error: %s" % err)

    def test_process_arguments_errors_on_invalid_opt(self):
        arg = "--wrong-thing"
        old_arg = sys.argv
        sys.argv = ["", arg]
        try:
            code, out, err = call_safely(cli.process_arguments)
            self.failUnless(code, msg="Should have errored for '%s'" % arg)
        finally:
            sys.argv = old_arg

    def test_print_query_standard(self):
        # Have to work in cases of no library and real library, probably
        code, out, err = call_safely(cli.print_query, "badtag=value")
        # A new line is currently added
        self.failIf(out.strip())

    def test_print_playing(self):
        code, out, err = call_safely(cli.print_playing)
        # Nothing should be playing.
        self.failUnless(code, msg="Was expecting error code, not %d" % code)
        self.failUnless("No song is currently playing" in out)
        self.failIf(err, msg="There was STDERR output: %s" % err)
