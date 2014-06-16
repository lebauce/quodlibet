# Copyright 2005 Joe Wreschnig, Michael Urman
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk
from quodlibet import app

from quodlibet.qltk import get_top_parent


class Message(Gtk.MessageDialog):
    """A message dialog that destroys itself after it is run, uses
    markup, and defaults to an 'OK' button."""

    def __init__(
        self, kind, parent, title, description, buttons=Gtk.ButtonsType.OK):
        parent = get_top_parent(parent)
        text = ("<span weight='bold' size='larger'>%s</span>\n\n%s"
                % (title, description))
        super(Message, self).__init__(
            transient_for=parent, modal=True, destroy_with_parent=True,
            message_type=kind, buttons=buttons)
        self.set_markup(text)

    def run(self, destroy=True):
        resp = super(Message, self).run()
        if destroy:
            self.destroy()
        return resp


class ConfirmAction(Message):
    """A message dialog that asks a yes/no question."""

    def __init__(self, *args, **kwargs):
        kwargs["buttons"] = Gtk.ButtonsType.YES_NO
        super(ConfirmAction, self).__init__(
            Gtk.MessageType.WARNING, *args, **kwargs)

    def run(self, destroy=True):
        """Returns True if yes was clicked, False otherwise."""
        resp = super(Message, self).run()
        if destroy:
            self.destroy()
        if resp == Gtk.ResponseType.YES:
            return True
        else:
            return False


def confirm_action(msg):
    """Ultra-lightweight confirmation dialog"""
    return ConfirmAction(app.window, _("Are you sure?"), msg).run()


class CancelRevertSave(Gtk.MessageDialog):
    def __init__(self, parent):
        title = _("Discard tag changes?")
        description = _("Tags have been changed but not saved. Save these "
                        "files, or revert and discard changes?")
        text = ("<span weight='bold' size='larger'>%s</span>\n\n%s"
                % (title, description))
        parent = get_top_parent(parent)
        super(CancelRevertSave, self).__init__(
            transient_for=parent, flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE)
        self.add_buttons(Gtk.STOCK_SAVE, Gtk.ResponseType.YES,
                         Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_REVERT_TO_SAVED, Gtk.ResponseType.NO)
        self.set_default_response(Gtk.ResponseType.NO)
        self.set_markup(text)

    def run(self):
        resp = super(CancelRevertSave, self).run()
        self.destroy()
        return resp


class ErrorMessage(Message):
    """Like Message, but uses an error-indicating picture."""
    def __init__(self, *args, **kwargs):
        super(ErrorMessage, self).__init__(
            Gtk.MessageType.ERROR, *args, **kwargs)


class WarningMessage(Message):
    """Like Message, but uses an warning-indicating picture."""
    def __init__(self, *args, **kwargs):
        super(WarningMessage, self).__init__(
            Gtk.MessageType.WARNING, *args, **kwargs)
