from gi.repository import Gtk, Gdk

from tests import TestCase, skipIf
from quodlibet.qltk.getstring import GetStringDialog
from quodlibet.qltk import is_wayland


class _ClipboadTestClass(GetStringDialog):
    _OK = True

    def _verify_clipboard(self, text):
        if self._OK:
            return text


@skipIf(is_wayland(), "blocks under wayland for some reason")
class TGetStringDialog(TestCase):
    def setUp(self):
        parent = Gtk.Window()
        self.gsd1 = GetStringDialog(parent, "title", "enter a string")
        self.gsd2 = _ClipboadTestClass(parent, "title", "enter a string")

    def test_getstring(self):
        ret = self.gsd1.run(text="foobar", test=True)
        self.failUnlessEqual(ret, "foobar")

    def test_clipboard(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("42", -1)
        ret = self.gsd2.run(text="24", clipboard=True, test=True)
        self.failUnlessEqual(ret, "42")

    def tearDown(self):
        self.gsd1.destroy()
        self.gsd2.destroy()
