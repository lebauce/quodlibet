import os

if os.name == "nt":
    from quodlibet.plugins import PluginNotSupportedError
    raise PluginNotSupportedError

from gi.repository import Gtk, GObject

from quodlibet import util
from quodlibet.plugins.editing import RenameFilesPlugin
from quodlibet.util.path import iscommand


class Kakasi(RenameFilesPlugin, Gtk.CheckButton):
    PLUGIN_ID = "Kana/Kanji Simple Inverter"
    PLUGIN_NAME = _("Kana/Kanji Simple Inverter")
    PLUGIN_DESC = _("Convert kana/kanji to romaji before renaming.")
    PLUGIN_ICON = Gtk.STOCK_CONVERT
    PLUGIN_VERSION = "1"

    __gsignals__ = {
        "preview": (GObject.SignalFlags.RUN_LAST, None, ())
    }

    def __init__(self):
        super(Kakasi, self).__init__(
            _("Romanize _Japanese text"), use_underline=True)
        self.connect_object('toggled', self.emit, 'preview')

    active = property(lambda s: s.get_active())

    # Use filter list rather than filter to avoid starting a new process
    # for each filename.
    def filter_list(self, originals, values):
        value = "\n".join(values)
        try:
            data = value.encode('shift-jis', 'replace')
        except None:
            return value
        line = ("kakasi -isjis -osjis -Ha -Ka -Ja -Ea -ka -s")
        w, r = os.popen2(line.split())
        w.write(data)
        w.close()
        try:
            return r.read().decode('shift-jis').strip().split("\n")
        except:
            return values


if not iscommand("kakasi"):
    from quodlibet import plugins
    raise plugins.PluginImportException(
        "Couldn't find the 'Kanji Kana Simple Inverter' (kakasi).")
