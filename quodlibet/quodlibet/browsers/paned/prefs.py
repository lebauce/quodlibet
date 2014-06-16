# Copyright 2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk

from quodlibet import util
from quodlibet import qltk

from quodlibet.qltk.views import BaseView
from quodlibet.qltk.tagscombobox import TagsComboBoxEntry
from quodlibet.qltk.x import SymbolicIconImage, MenuItem
from quodlibet.qltk.menubutton import MenuButton
from quodlibet.qltk.ccb import ConfigCheckMenuItem

from .util import get_headers, save_headers


class PatternEditor(Gtk.VBox):

    PRESETS = [
        ["genre", "~people", "album"],
        ["~people", "album"],
    ]
    COMPLETION = ["genre", "grouping", "~people", "artist", "album", "~year"]

    def __init__(self):
        super(PatternEditor, self).__init__(spacing=6)

        self.__headers = headers = {}
        buttons = []

        group = None
        for tags in self.PRESETS:
            tied = "~" + "~".join(tags)
            group = Gtk.RadioButton(group=group, label="_" + util.tag(tied),
                                    use_underline=True)
            headers[group] = tags
            buttons.append(group)

        group = Gtk.RadioButton(group=group, label=_("_Custom"),
                                use_underline=True)
        self.__custom = group
        headers[group] = []
        buttons.append(group)

        button_box = Gtk.HBox(spacing=6)
        self.__model = model = Gtk.ListStore(str)

        radio_box = Gtk.VBox(spacing=6)
        for button in buttons:
            radio_box.pack_start(button, False, True, 0)
            button.connect('toggled', self.__toggled, button_box, model)

        self.pack_start(radio_box, False, True, 0)

        cb = TagsComboBoxEntry(self.COMPLETION)

        view = BaseView(model=model)
        view.set_reorderable(True)
        view.set_headers_visible(False)

        ctrl_box = Gtk.VBox(spacing=6)

        add = Gtk.Button(stock=Gtk.STOCK_ADD)
        ctrl_box.pack_start(add, False, True, 0)
        add.connect('clicked', self.__add, model, cb)

        remove = Gtk.Button(stock=Gtk.STOCK_REMOVE)
        ctrl_box.pack_start(remove, False, True, 0)
        remove.connect('clicked', self.__remove, view)

        selection = view.get_selection()
        selection.connect('changed', self.__selection_changed, remove)
        selection.emit('changed')

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(view)

        edit_box = Gtk.VBox(spacing=6)
        edit_box.pack_start(cb, False, True, 0)
        edit_box.pack_start(sw, True, True, 0)

        button_box.pack_start(edit_box, True, True, 0)
        button_box.pack_start(ctrl_box, False, True, 0)
        self.pack_start(button_box, True, True, 0)

        render = Gtk.CellRendererText()
        render.set_property("editable", True)

        def edited_cb(render, path, text, model):
            model[path][0] = text
        render.connect("edited", edited_cb, model)

        column = Gtk.TreeViewColumn(None, render, text=0)
        view.append_column(column)

    def __get_headers(self):
        for button in self.__headers.iterkeys():
            if button.get_active():
                if button == self.__custom:
                    model_headers = [row[0] for row in self.__model]
                    self.__headers[self.__custom] = model_headers
                return self.__headers[button]

    def __set_headers(self, new_headers):
        for button, headers in self.__headers.iteritems():
            if headers == new_headers:
                button.set_active(True)
                button.emit("toggled")
                break
        else:
            self.__headers[self.__custom] = new_headers
            self.__custom.set_active(True)

    headers = property(__get_headers, __set_headers)

    def __selection_changed(self, selection, remove):
        remove.set_sensitive(bool(selection.get_selected()[1]))

    def __add(self, button, model, cb):
        if cb.tag:
            model.append(row=[cb.tag])

    def __remove(self, button, view):
        view.remove_selection()

    def __toggled(self, button, edit_widget, model):
        tags = self.__headers[button]

        if tags:
            model.clear()
            for h in tags:
                model.append(row=[h])

        edit_widget.set_sensitive(
            button.get_active() and button is self.__custom)


class PreferencesButton(Gtk.HBox):
    def __init__(self, browser):
        super(PreferencesButton, self).__init__()

        self._menu = menu = Gtk.Menu()

        wide_mode = ConfigCheckMenuItem(
            _("_Wide Mode"), "browsers", "pane_wide_mode", True)
        wide_mode.connect("toggled", self.__wide_mode_changed, browser)
        menu.append(wide_mode)

        pref_item = MenuItem(_("_Preferences"), Gtk.STOCK_PREFERENCES)

        def preferences_cb(menu_item):
            window = Preferences(browser)
            window.show()
        pref_item.connect("activate", preferences_cb)
        menu.append(pref_item)

        menu.show_all()

        button = MenuButton(
                SymbolicIconImage("emblem-system", Gtk.IconSize.MENU),
                arrow=True)
        button.set_menu(menu)
        button.show()
        self.pack_start(button, True, True, 0)

    def __wide_mode_changed(self, menu_item, browser):
        browser.set_all_wide_mode(menu_item.get_active())


class Preferences(qltk.UniqueWindow):
    def __init__(self, browser):
        if self.is_not_unique():
            return
        super(Preferences, self).__init__()

        self.set_transient_for(qltk.get_top_parent(browser))
        self.set_default_size(350, 270)
        self.set_border_width(12)

        self.set_title(_("Paned Browser Preferences") + " - Quod Libet")

        vbox = Gtk.VBox(spacing=12)

        editor = PatternEditor()
        editor.headers = get_headers()

        apply_ = Gtk.Button(stock=Gtk.STOCK_APPLY)
        apply_.connect_object("clicked", self.__apply, editor, browser, False)

        cancel = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel.connect("clicked", lambda x: self.destroy())

        ok = Gtk.Button(stock=Gtk.STOCK_OK)
        ok.connect_object("clicked", self.__apply, editor, browser, True)

        box = Gtk.HButtonBox()
        box.set_spacing(6)
        box.set_layout(Gtk.ButtonBoxStyle.END)
        box.pack_start(apply_, True, True, 0)
        box.pack_start(cancel, True, True, 0)
        box.pack_start(ok, True, True, 0)

        vbox.pack_start(editor, True, True, 0)
        vbox.pack_start(box, False, True, 0)

        self.add(vbox)

        ok.grab_focus()
        self.get_child().show_all()

    def __apply(self, editor, browser, close):
        if editor.headers != get_headers():
            save_headers(editor.headers)
            browser.set_all_panes()

        if close:
            self.destroy()
