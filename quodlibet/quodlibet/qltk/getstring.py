# -*- coding: utf-8 -*-
# Copyright 2005 Joe Wreschnig, Michael Urman
#           2013 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, Gdk

from quodlibet.qltk.entry import UndoEntry
from quodlibet.qltk.window import Dialog


class GetStringDialog(Dialog):
    """Simple dialog to return a string from the user"""
    _WIDTH = 300

    def __init__(self, parent, title, text, okbutton=Gtk.STOCK_OPEN):
        super(GetStringDialog, self).__init__(
            title=title, transient_for=parent, use_header_bar=True)

        self.set_border_width(6)
        self.set_default_size(width=self._WIDTH, height=0)
        self.set_resizable(True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         okbutton, Gtk.ResponseType.OK)
        self.vbox.set_spacing(6)
        self.set_default_response(Gtk.ResponseType.OK)

        box = Gtk.VBox(spacing=6)
        lab = Gtk.Label(label=text)
        box.set_border_width(6)
        lab.set_line_wrap(True)
        lab.set_justify(Gtk.Justification.CENTER)
        box.pack_start(lab, True, True, 0)

        self._val = UndoEntry()
        box.pack_start(self._val, True, True, 0)

        self.vbox.pack_start(box, True, True, 0)
        self.get_child().show_all()

    def _verify_clipboard(self, text):
        """Return an altered text or None if the content was invalid."""
        return

    def run(self, text="", clipboard=False, test=False):
        """Shows the dialog and returns the entered value.

        If clipboard is set, the initial value will be pulled from the
        clipboard and can be verified/altered by _verify_clipboard. In case the
        verification fails text will be used as fallback"""

        self.show()
        if clipboard:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clip = clipboard.wait_for_text()
            if clip is not None:
                clip = self._verify_clipboard(clip)
            if clip is not None:
                text = clip

        self._val.set_text(text)
        self._val.set_activates_default(True)
        self._val.grab_focus()
        resp = Gtk.ResponseType.OK
        if not test:
            resp = super(GetStringDialog, self).run()
        if resp == Gtk.ResponseType.OK:
            value = self._val.get_text()
        else:
            value = None
        self.destroy()
        return value
