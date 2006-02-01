# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

import gobject, gtk, pango
import qltk
import util

class TextEditBox(gtk.VBox):
    """A simple text editing area with a default value, a revert button,
    and an apply button. The 'buffer' attribute is the text buffer, the
    'apply' attribute is the apply button.

    FIXME: Button text should changable (without poking the buttons directly).
    """

    def __init__(self, default=""):
        super(TextEditBox, self).__init__(spacing=12)

        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(gtk.TextView())
        self.pack_start(sw)
        self.buffer = sw.child.get_buffer()

        box = gtk.HButtonBox()
        box.set_spacing(12)
        box.set_layout(gtk.BUTTONBOX_END)
        rev = gtk.Button(stock=gtk.STOCK_REVERT_TO_SAVED)
        app = gtk.Button(stock=gtk.STOCK_APPLY)
        box.pack_start(rev)
        box.pack_start(app)
        self.pack_start(box, expand=False)
        rev.connect_object('clicked', self.buffer.set_text, default)
        self.revert = rev
        self.apply = app

    def __get_text(self):
        return self.buffer.get_text(*self.buffer.get_bounds()).decode('utf-8')
    text = property(__get_text,
                    lambda s, v: s.buffer.set_text(v))

class PatternEditBox(TextEditBox):
    """A TextEditBox that stops the apply button's clicked signal if
    the pattern is invalid. You need to use connect_after to connect to
    it, to get this feature."""

    def __init__(self, default=""):
        super(PatternEditBox, self).__init__(default)
        self.apply.connect('clicked', self.__check_markup)

    def __check_markup(self, apply):
        try:
            from formats._audio import AudioFile
            from parse import XMLFromPattern
            f = AudioFile({"~filename":"dummy"})
            pango.parse_markup(XMLFromPattern(self.text) % f, u"\u0000")
        except (ValueError, gobject.GError), e:
            qltk.ErrorMessage(
                self, _("Invalid pattern"),
                _("The pattern you entered was invalid. Make sure you enter "
                  "&lt; and &gt; as \\&lt; and \\&gt; and that your tags are "
                  "balanced.\n\n%s") % util.escape(str(e))).run()
            apply.stop_emission('clicked')
        return False

class TextEdit(gtk.Window):
    """A window with a text editing box in it."""

    Box = TextEditBox

    def __init__(self, parent, default=""):
        super(TextEdit, self).__init__()
        self.set_title(_("Edit Display"))
        self.set_transient_for(qltk.get_top_parent(parent))
        self.set_border_width(12)
        self.set_default_size(400, 200)
        self.add(self.Box(default))
        self.apply = self.child.apply
        self.revert = self.child.revert
        self.show_all()

    text = property(lambda s: s.child.text,
                    lambda s, v: setattr(s.child, 'text', v))

class PatternEdit(TextEdit):
    """A window with a pattern editing box in it."""
    Box = PatternEditBox
    