# -*- coding: utf-8 -*-
from tests import TestCase, AbstractTestCase

from quodlibet.qltk.msg import *


class _TMessage(AbstractTestCase):
    def setUp(self):
        self.win = self.Kind(None, "title", "description")

    def test_ctr(self):
        pass

    def tearDown(self):
        self.win.destroy()


class TWarningMessage(_TMessage):
    Kind = WarningMessage


class TErrorMessage(_TMessage):
    Kind = ErrorMessage


class TCancelRevertSave(TestCase):
    def setUp(self):
        self.win = CancelRevertSave(None)

    def test_ctr(self):
        pass

    def tearDown(self):
        self.win.destroy()


class TFileReplace(TestCase):

    def setUp(self):
        self.win = ConfirmFileReplace(None, "")

    def test_ctr(self):
        pass

    def tearDown(self):
        self.win.destroy()
