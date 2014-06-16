# Copyright 2014 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk


class GetPlayerDialog(Gtk.Dialog):
    def __init__(self, parent, players, current=0):
        title = _("Choose Squeezebox player")
        super(GetPlayerDialog, self).__init__(title, parent)
        self.set_border_width(6)
        self.set_resizable(False)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.vbox.set_spacing(6)
        self.set_default_response(Gtk.ResponseType.OK)

        box = Gtk.VBox(spacing=6)
        label = Gtk.Label(
            label=_("Found Squeezebox server.\nPlease choose the player"))
        box.set_border_width(6)
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        box.pack_start(label, True, True, 0)

        player_combo = Gtk.ComboBoxText()
        for player in players:
            player_combo.append_text(player["name"])
        player_combo.set_active(current)
        self._val = player_combo
        box.pack_start(self._val, True, True, 0)
        self.vbox.pack_start(box, True, True, 0)
        self.get_child().show_all()

    def run(self, text=""):
        self.show()
        self._val.grab_focus()
        resp = super(GetPlayerDialog, self).run()
        if resp == Gtk.ResponseType.OK:
            value = self._val.get_active()
        else:
            value = None
        self.destroy()
        return value
