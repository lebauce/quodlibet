# -*- coding: utf-8 -*-
# Copyright 2004-2012 Joe Wreschnig, Michael Urman, Iñigo Serna, Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import sys

from gi.repository import Gtk, Pango, Gdk

from quodlibet import qltk

from quodlibet import config
from quodlibet import util

from quodlibet.util import massagers

from quodlibet.qltk.completion import LibraryValueCompletion
from quodlibet.qltk.tagscombobox import TagsComboBox, TagsComboBoxEntry
from quodlibet.qltk.views import RCMHintedTreeView, TreeViewColumn
from quodlibet.qltk.wlw import WritingWindow
from quodlibet.qltk.window import Dialog
from quodlibet.qltk.models import ObjectStore
from quodlibet.qltk.ccb import ConfigCheckButton
from quodlibet.qltk.x import SeparatorMenuItem
from quodlibet.qltk._editutils import EditingPluginHandler, OverwriteWarning
from quodlibet.qltk._editutils import WriteFailedError
from quodlibet.plugins import PluginManager
from quodlibet.util import connect_obj
from quodlibet.util.tags import USER_TAGS, MACHINE_TAGS, sortkey as tagsortkey
from quodlibet.util.string.splitters import (split_value, split_title,
    split_people, split_album)


class Comment(object):
    """A summary of a collection of values for one tag"""

    def __init__(self, text, have=1, total=1, shared=True):
        """
        Args:
            text: the first or only text value
            have: amount of songs that have a value
            total: total amount of songs
            shared: if all songs that have a value, have the same one
        """

        self.complete = have == total
        self.shared = shared
        self.total = total
        self.missing = total - have
        self.have = have
        self.text = text

    def _paren(self):
        if self.shared:
            return ngettext('missing from %d song',
                            'missing from %d songs',
                            self.missing) % self.missing
        elif self.complete:
            return ngettext('different across %d song',
                            'different across %d songs',
                            self.total) % self.total
        else:
            d = ngettext('different across %d song',
                          'different across %d songs',
                          self.have) % self.have
            m = ngettext('missing from %d song',
                          'missing from %d songs',
                          self.missing) % self.missing
            return ", ".join([d, m])

    def is_special(self):
        return not self.shared or not self.complete

    def is_missing(self):
        return not self.complete

    def get_markup(self):
        """Returns pango markup for displaying"""

        if self.shared and self.complete:
            return util.escape(self.text)
        elif self.shared:
            return "\n".join(
                ['%s<i> (%s)</i>' % (util.escape(s),
                                     util.escape(self._paren()))
                 for s in self.text.split("\n")])
        else:
            return '<i>(%s)</i>' % util.escape(self._paren())


def get_default_tags():
    """Returns a list of tags that should be displayed even if not present
    in the file.
    """

    text = config.get("editing", "default_tags").strip()
    if not text:
        return []
    return text.split(",")


class AudioFileGroup(dict):
    """Values are a list of Comment instances"""

    def __init__(self, songs, real_keys_only=True):
        keys = {}
        first = {}
        all = {}
        total = len(songs)
        self.songs = songs
        self.is_file = True
        can_multi = True
        can_change = True

        for song in songs:
            self.is_file &= song.is_file

            if real_keys_only:
                iter_func = song.iterrealitems
            else:
                iter_func = song.iteritems

            for comment, val in iter_func():
                keys[comment] = keys.get(comment, 0) + 1
                first.setdefault(comment, val)
                all[comment] = all.get(comment, True) and first[comment] == val

            song_can_multi = song.can_multiple_values()
            if song_can_multi is not True:
                if can_multi is True:
                    can_multi = set(song_can_multi)
                else:
                    can_multi.intersection_update(song_can_multi)

            song_can_change = song.can_change()
            if song_can_change is not True:
                if can_change is True:
                    can_change = set(song_can_change)
                else:
                    can_change.intersection_update(song_can_change)

        self._can_multi = can_multi
        self._can_change = can_change

        # collect comment representations
        for tag, count in keys.iteritems():
            first_value = first[tag]
            if not isinstance(first_value, basestring):
                first_value = unicode(first_value)
            shared = all[tag]
            complete = count == total
            if shared and complete:
                values = first_value.split("\n")
            else:
                values = [first_value]
            for v in values:
                self.setdefault(tag, []).append(
                    Comment(v, count, total, shared))

    def can_multiple_values(self, key=None):
        """If no arguments passed returns a set of tags that have multi
        value support for all contained songs. If key is given returns
        if all songs support multi value tags for that key.
        """

        if key is None:
            return self._can_multi
        return all(song.can_multiple_values(key) for song in self.songs)

    def can_change(self, key=None):
        """See can_multiple_values()"""

        if key is None:
            return self._can_change
        return all(song.can_change(key) for song in self.songs)


class SplitValues(Gtk.ImageMenuItem):
    tags = False
    needs = []
    _order = 0.0

    def __init__(self, tag, value):
        super(SplitValues, self).__init__(
            label=_("Split into _Multiple Values"), use_underline=True)
        self.set_image(Gtk.Image.new_from_stock(
            Gtk.STOCK_FIND_AND_REPLACE, Gtk.IconSize.MENU))
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        self.set_sensitive(len(split_value(value, spls)) > 1)

    def activated(self, tag, value):
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        return [(tag, v) for v in split_value(value, spls)]


class SplitDisc(Gtk.ImageMenuItem):
    tags = ["album"]
    needs = ["discnumber"]
    _order = 0.5

    def __init__(self, tag, value):
        super(SplitDisc, self).__init__(
            label=_("Split Disc out of _Album"), use_underline=True)
        self.set_image(Gtk.Image.new_from_stock(
            Gtk.STOCK_FIND_AND_REPLACE, Gtk.IconSize.MENU))
        self.set_sensitive(split_album(value)[1] is not None)

    def activated(self, tag, value):
        album, disc = split_album(value)
        return [(tag, album), ("discnumber", disc)]


class SplitTitle(Gtk.ImageMenuItem):
    tags = ["title"]
    needs = ["version"]
    _order = 0.5

    def __init__(self, tag, value):
        super(SplitTitle, self).__init__(
            label=_("Split _Version out of Title"), use_underline=True)
        self.set_image(Gtk.Image.new_from_stock(
            Gtk.STOCK_FIND_AND_REPLACE, Gtk.IconSize.MENU))
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        self.set_sensitive(bool(split_title(value, spls)[1]))

    def activated(self, tag, value):
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        title, versions = split_title(value, spls)
        return [(tag, title)] + [("version", v) for v in versions]


class SplitPerson(Gtk.ImageMenuItem):
    tags = ["artist"]
    _order = 0.5

    def __init__(self, tag, value):
        super(SplitPerson, self).__init__(label=self.title, use_underline=True)
        self.set_image(Gtk.Image.new_from_stock(
            Gtk.STOCK_FIND_AND_REPLACE, Gtk.IconSize.MENU))
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        self.set_sensitive(bool(split_people(value, spls)[1]))

    def activated(self, tag, value):
        spls = config.get("editing", "split_on").decode(
            'utf-8', 'replace').split()
        artist, others = split_people(value, spls)
        return [(tag, artist)] + [(self.needs[0], o) for o in others]


class SplitArranger(SplitPerson):
    needs = ["arranger"]
    title = _("Split Arranger out of Ar_tist")


class SplitPerformer(SplitPerson):
    needs = ["performer"]
    title = _("Split _Performer out of Artist")


class SplitPerformerFromTitle(SplitPerson):
    tags = ["title"]
    needs = ["performer"]
    title = _("Split _Performer out of Title")


class SplitOriginalArtistFromTitle(SplitPerson):
    tags = ["title"]
    needs = ["originalartist"]
    title = _("Split _Originalartist out of Title")


class AddTagDialog(Dialog):

    def __init__(self, parent, can_change, library):
        super(AddTagDialog, self).__init__(
            title=_("Add a Tag"), transient_for=qltk.get_top_parent(parent),
            use_header_bar=True)
        self.set_border_width(6)
        self.set_resizable(False)
        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        add = self.add_button(Gtk.STOCK_ADD, Gtk.ResponseType.OK)
        self.vbox.set_spacing(6)
        self.set_default_response(Gtk.ResponseType.OK)
        table = Gtk.Table(n_rows=2, n_columns=2)
        table.set_row_spacings(12)
        table.set_col_spacings(6)
        table.set_border_width(6)

        self.__tag = (TagsComboBoxEntry() if can_change is True
                      else TagsComboBox(can_change))

        label = Gtk.Label()
        label.set_alignment(0.0, 0.5)
        label.set_text(_("_Tag:"))
        label.set_use_underline(True)
        label.set_mnemonic_widget(self.__tag)
        table.attach(label, 0, 1, 0, 1)
        table.attach(self.__tag, 1, 2, 0, 1)

        self.__val = Gtk.Entry()
        self.__val.set_completion(LibraryValueCompletion("", library))
        label = Gtk.Label()
        label.set_text(_("_Value:"))
        label.set_alignment(0.0, 0.5)
        label.set_use_underline(True)
        label.set_mnemonic_widget(self.__val)
        valuebox = Gtk.EventBox()
        table.attach(label, 0, 1, 1, 2)
        table.attach(valuebox, 1, 2, 1, 2)
        hbox = Gtk.HBox()
        valuebox.add(hbox)
        hbox.pack_start(self.__val, True, True, 0)
        hbox.set_spacing(6)
        invalid = Gtk.Image.new_from_stock(
            Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.SMALL_TOOLBAR)
        hbox.pack_start(invalid, True, True, 0)

        self.vbox.pack_start(table, True, True, 0)
        self.get_child().show_all()
        invalid.hide()

        for entry in [self.__tag, self.__val]:
            entry.connect(
                'changed', self.__validate, add, invalid, valuebox)
        self.__tag.connect('changed', self.__set_value_completion, library)
        self.__set_value_completion(self.__tag, library)

        if can_change is True:
            connect_obj(self.__tag.get_child(),
                'activate', Gtk.Entry.grab_focus, self.__val)

    def __set_value_completion(self, tag, library):
        completion = self.__val.get_completion()
        if completion:
            completion.set_tag(self.__tag.tag, library)

    def get_tag(self):
        try:
            return self.__tag.tag
        except AttributeError:
            return self.__tag.tag

    def get_value(self):
        return self.__val.get_text().decode("utf-8")

    def __validate(self, editable, add, invalid, box):
        tag = self.get_tag()
        value = self.get_value()
        fmt = massagers.tags.get(tag)
        if fmt:
            valid = fmt.is_valid(value)
        else:
            valid = True
        add.set_sensitive(valid)
        if valid:
            invalid.hide()
            box.set_tooltip_text("")
        else:
            invalid.show()
            box.set_tooltip_text(fmt.error)

    def run(self):
        self.show()
        self.__val.set_activates_default(True)
        self.__tag.grab_focus()
        return super(AddTagDialog, self).run()


class EditTagsPluginHandler(EditingPluginHandler):
    from quodlibet.plugins.editing import EditTagsPlugin
    Kind = EditTagsPlugin


class ListEntry(object):
    """Holds a Comment and some state for the editing process"""

    tag = None
    value = None
    edited = False
    canedit = True
    deleted = False
    origvalue = None
    renamed = False
    origtag = None

    def __init__(self, tag, value):
        self.tag = tag
        self.value = value


class EditTags(Gtk.VBox):
    _SAVE_BUTTON_KEY = 'ql-save'
    _REVERT_BUTTON_KEY = 'ql-revert'
    # Translators: translate only to override the text
    # for the tag "save" button
    _SAVE_BUTTON_TEXT = _('ql-save')
    # Translators: translate only to override the  for the tag "revert" button
    _REVERT_BUTTON_TEXT = _('ql-revert')
    handler = EditTagsPluginHandler()

    @classmethod
    def init_plugins(cls):
        PluginManager.instance.register_handler(cls.handler)

    def __init__(self, parent, library):
        super(EditTags, self).__init__(spacing=12)
        self.title = _("Edit Tags")
        self.set_border_width(12)

        model = ObjectStore()
        view = RCMHintedTreeView(model=model)
        self._view = view
        selection = view.get_selection()
        render = Gtk.CellRendererPixbuf()
        column = TreeViewColumn(_("Write"), render)

        style = view.get_style()
        pixbufs = [style.lookup_icon_set(stock)
                   .render_icon(style, Gtk.TextDirection.NONE, state,
                                Gtk.IconSize.MENU, view, None)
                   for state in (Gtk.StateType.INSENSITIVE,
                                 Gtk.StateType.NORMAL)
                   for stock in (Gtk.STOCK_EDIT, Gtk.STOCK_DELETE)]

        def cdf_write(col, rend, model, iter_, *args):
            entry = model.get_value(iter_)
            if entry.canedit or entry.deleted:
                rend.set_property('stock-id', None)
                rend.set_property('pixbuf',
                    pixbufs[2 * entry.edited + entry.deleted])
            else:
                rend.set_property('stock-id', Gtk.STOCK_DIALOG_AUTHENTICATION)
        column.set_cell_data_func(render, cdf_write)
        view.append_column(column)

        render = Gtk.CellRendererText()
        column = TreeViewColumn(_('Tag'), render)

        def cell_data_tag(column, cell, model, iter_, data):
            entry = model.get_value(iter_)
            cell.set_property("text", entry.tag)
            cell.set_property("strikethrough", entry.deleted)

        column.set_cell_data_func(render, cell_data_tag)

        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        render.set_property('editable', True)
        render.connect('edited', self.__edit_tag_name, model)
        render.connect(
            'editing-started', self.__tag_editing_started, model, library)
        view.append_column(column)

        render = Gtk.CellRendererText()
        render.set_property('ellipsize', Pango.EllipsizeMode.END)
        render.set_property('editable', True)
        render.connect('edited', self.__edit_tag, model)
        render.connect(
            'editing-started', self.__value_editing_started, model, library)
        column = TreeViewColumn(_('Value'), render)

        def cell_data_value(column, cell, model, iter_, data):
            entry = model.get_value(iter_)
            markup = entry.value.get_markup()
            cell.markup = markup
            cell.set_property("markup", markup)
            cell.set_property("editable", entry.canedit)
            cell.set_property("strikethrough", entry.deleted)

        column.set_cell_data_func(render, cell_data_value)

        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        view.append_column(column)

        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(view)
        self.pack_start(sw, True, True, 0)

        cb = ConfigCheckButton(
            _("Show _programmatic tags"), 'editing', 'alltags', populate=True,
            tooltip=_("Access all tags, including machine-generated "
                      "ones e.g. MusicBrainz or Replay Gain tags"))
        cb.connect('toggled', self.__all_tags_toggled)
        self.pack_start(cb, False, True, 0)

        # Add and Remove [tags] buttons
        buttonbox = Gtk.HBox(spacing=18)
        bbox1 = Gtk.HButtonBox()
        bbox1.set_spacing(6)
        bbox1.set_layout(Gtk.ButtonBoxStyle.START)
        add = Gtk.Button(stock=Gtk.STOCK_ADD)
        add.set_focus_on_click(False)
        self._add = add
        add.connect('clicked', self.__add_tag, model, library)
        bbox1.pack_start(add, True, True, 0)
        # Remove button
        remove = Gtk.Button(stock=Gtk.STOCK_REMOVE)
        remove.set_focus_on_click(False)
        remove.connect('clicked', self.__remove_tag, view)
        remove.set_sensitive(False)
        self._remove = remove

        bbox1.pack_start(remove, True, True, 0)

        # Revert and save buttons
        # Both can have customised translated text (and thus accels)
        bbox2 = Gtk.HButtonBox()
        bbox2.set_spacing(6)
        bbox2.set_layout(Gtk.ButtonBoxStyle.END)
        revert = (Gtk.Button(stock=Gtk.STOCK_REVERT_TO_SAVED)
                  if self._REVERT_BUTTON_KEY == self._REVERT_BUTTON_TEXT
                  else Gtk.Button(label=self._REVERT_BUTTON_TEXT,
                                  use_underline=True))
        self._revert = revert
        revert.set_sensitive(False)
        # Save button.
        save = (Gtk.Button(stock=Gtk.STOCK_SAVE)
                if self._SAVE_BUTTON_TEXT == self._SAVE_BUTTON_KEY
                else Gtk.Button(label=self._SAVE_BUTTON_TEXT,
                                use_underline=True))
        save.set_sensitive(False)
        self._save = save
        bbox2.pack_start(revert, True, True, 0)
        bbox2.pack_start(save, True, True, 0)

        buttonbox.pack_start(bbox1, True, True, 0)
        buttonbox.pack_start(bbox2, True, True, 0)
        self.pack_start(buttonbox, False, True, 0)
        self._buttonbox = buttonbox

        parent.connect('changed', self.__parent_changed)
        revert.connect('clicked', lambda *x: self._update())
        connect_obj(revert, 'clicked', parent.set_pending, None)

        save.connect('clicked', self.__save_files, revert, model, library)
        connect_obj(save, 'clicked', parent.set_pending, None)
        for sig in ['row-inserted', 'row-deleted', 'row-changed']:
            model.connect(sig, self.__enable_save, [save, revert])
            connect_obj(model, sig, parent.set_pending, save)

        view.connect('popup-menu', self.__popup_menu, parent)
        view.connect('button-press-event', self.__button_press)
        view.connect('key-press-event', self.__view_key_press_event)
        selection.connect('changed', self.__tag_select, remove)
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)

        self._parent = parent

        for child in self.get_children():
            child.show_all()

    def __all_tags_toggled(self, *args):
        self._update()

    def __view_key_press_event(self, view, event):
        if qltk.is_accel(event, "Delete"):
            self.__remove_tag(view, view)
            return Gdk.EVENT_STOP
        elif qltk.is_accel(event, "<ctrl>s"):
            # Issue 697: allow Ctrl-s to save.
            self._save.emit('clicked')
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    def __enable_save(self, *args):
        buttons = args[-1]
        for b in buttons:
            b.set_sensitive(True)

    def __paste(self, clip, text, (rend, path)):
        if text:
            rend.emit('edited', path, text.strip())

    def __menu_activate(self, activator, view):
        model, (path,) = view.get_selection().get_selected_rows()
        entry = model[path][0]

        tag = entry.tag
        comment = entry.value
        value = comment.text
        vals = activator.activated(tag, value)
        replaced = False
        if vals and (len(vals) != 1 or vals[0][1] != value):
            for atag, aval in vals:
                if atag == tag and not replaced:
                    replaced = True
                    entry.value = Comment(aval)
                    entry.edited = True
                    model.path_changed(path)
                else:
                    self.__add_new_tag(model, atag, aval)
        elif vals:
            replaced = True

        if not replaced:
            entry.edited = entry.deleted = True
            model.path_changed(path)

    def __popup_menu(self, view, parent):
        menu = Gtk.Menu()

        view.ensure_popup_selection()
        model, rows = view.get_selection().get_selected_rows()
        can_change = min([model[path][0].canedit for path in rows])

        items = [SplitDisc, SplitTitle, SplitPerformer, SplitArranger,
                 SplitValues, SplitPerformerFromTitle,
                 SplitOriginalArtistFromTitle]
        items.extend(self.handler.plugins)
        items.sort(key=lambda item: (item._order, item.__name__))

        if len(rows) == 1:
            row = model[rows[0]]
            entry = row[0]

            comment = entry.value
            text = comment.text

            for Item in items:
                if Item.tags and entry.tag not in Item.tags:
                    continue

                try:
                    b = Item(entry.tag, text)
                except:
                    util.print_exc()
                else:
                    b.connect('activate', self.__menu_activate, view)

                    if (not min(map(self.__songinfo.can_change, b.needs) + [1])
                            or comment.is_special()):
                        b.set_sensitive(False)

                    menu.append(b)

            if menu.get_children():
                menu.append(SeparatorMenuItem())

        b = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_REMOVE, None)
        b.connect('activate', self.__remove_tag, view)
        qltk.add_fake_accel(b, "Delete")
        menu.append(b)

        menu.show_all()
        # Setting the menu itself to be insensitive causes it to not
        # be dismissed; see #473.
        for c in menu.get_children():
            c.set_sensitive(can_change and c.get_property('sensitive'))
        b.set_sensitive(True)
        menu.connect('selection-done', lambda m: m.destroy())

        # XXX: Keep reference
        self.__menu = menu
        return view.popup_menu(menu, 3, Gtk.get_current_event_time())

    def __tag_select(self, selection, remove):
        model, rows = selection.get_selected_rows()
        remove.set_sensitive(bool(rows))

    def __add_new_tag(self, model, tag, value):
        iters = [i for (i, v) in model.iterrows() if v.tag == tag]
        if iters and not self.__songinfo.can_multiple_values(tag):
            title = _("Unable to add tag")
            msg = _("Unable to add <b>%s</b>") % util.escape(tag)
            msg += "\n\n"
            msg += _("The files currently"
                    " selected do not support multiple values for <b>%s</b>."
                    ) % util.escape(tag)
            qltk.ErrorMessage(self, title, msg).run()
            return

        entry = ListEntry(tag, Comment(value))
        entry.edited = True

        if len(iters):
            model.insert_after(iters[-1], row=[entry])
        else:
            model.append(row=[entry])

    def __add_tag(self, activator, model, library):
        add = AddTagDialog(self, self.__songinfo.can_change(), library)

        while True:
            resp = add.run()
            if resp != Gtk.ResponseType.OK:
                break
            tag = add.get_tag()
            value = add.get_value()
            if tag in massagers.tags:
                value = massagers.tags[tag].validate(value)
            if not self.__songinfo.can_change(tag):
                title = _("Invalid tag")
                msg = _("Invalid tag <b>%s</b>\n\nThe files currently"
                        " selected do not support editing this tag."
                        ) % util.escape(tag)
                qltk.ErrorMessage(self, title, msg).run()
            else:
                self.__add_new_tag(model, tag, value)
                break

        add.destroy()

    def __remove_tag(self, activator, view):
        model, paths = view.get_selection().get_selected_rows()
        # Since the iteration can modify path numbers, we need accurate
        # rows (= iters) before we start.
        rows = [model[path] for path in paths]
        for row in rows:
            entry = row[0]
            if entry.origvalue is not None:
                entry.edited = entry.deleted = True
                model.row_changed(row.path, row.iter)
            else:
                model.remove(row.iter)

    def __save_files(self, save, revert, model, library):
        updated = {}
        deleted = {}
        added = {}
        renamed = {}

        for entry in model.itervalues():
            if entry.edited and not (entry.deleted or entry.renamed):
                if entry.origvalue is not None:
                    l = updated.setdefault(entry.tag, [])
                    l.append((entry.value, entry.origvalue))
                else:
                    l = added.setdefault(entry.tag, [])
                    l.append(entry.value)

            if entry.edited and entry.deleted:
                if entry.origvalue is not None:
                    l = deleted.setdefault(entry.tag, [])
                    l.append(entry.origvalue)

            if entry.edited and entry.renamed and not entry.deleted:
                l = renamed.setdefault(entry.tag, [])
                l.append((entry.origtag, entry.value, entry.origvalue))

        was_changed = set()
        songs = self.__songinfo.songs
        win = WritingWindow(self, len(songs))
        win.show()
        all_done = False
        for song in songs:
            if not song.valid():
                win.hide()
                dialog = OverwriteWarning(self, song)
                resp = dialog.run()
                win.show()
                if resp != OverwriteWarning.RESPONSE_SAVE:
                    break

            changed = False
            for key, values in updated.iteritems():
                for (new_value, old_value) in values:
                    if song.can_change(key):
                        if old_value is None:
                            song.add(key, new_value.text)
                        else:
                            song.change(key, old_value.text, new_value.text)
                        changed = True

            for key, values in added.iteritems():
                for value in values:
                    if song.can_change(key):
                        song.add(key, value.text)
                        changed = True

            for key, values in deleted.iteritems():
                for value in values:
                    if key in song:
                        song.remove(key, value.text)
                        changed = True

            save_rename = []
            for new_tag, values in renamed.iteritems():
                for old_tag, new_value, old_value in values:
                    if (song.can_change(new_tag) and old_tag in song):
                        if not new_value.is_special():
                            song.remove(old_tag, old_value.text)
                            save_rename.append((new_tag, new_value))
                        elif new_value.is_missing():
                            song.remove(old_tag, old_value)
                            save_rename.append((new_tag, new_value))
                        else:
                            save_rename.append(
                                (new_tag, Comment(song[old_tag])))
                            song.remove(old_tag, None)
                        changed = True

            for tag, value in save_rename:
                song.add(tag, value.text)

            if changed:
                try:
                    song.write()
                except:
                    util.print_exc()
                    WriteFailedError(self, song).run()
                    library.reload(song, changed=was_changed)
                    break
                was_changed.add(song)

            if win.step():
                break
        else:
            all_done = True

        win.destroy()
        library.changed(was_changed)
        for b in [save, revert]:
            b.set_sensitive(not all_done)

    def __edit_tag(self, renderer, path, new_value, model):
        new_value = ', '.join(new_value.splitlines())
        path = Gtk.TreePath.new_from_string(path)
        entry = model[path][0]

        if entry.tag in massagers.tags:
            fmt = massagers.tags[entry.tag]
            if not fmt.is_valid(new_value):
                qltk.WarningMessage(
                    self, _("Invalid value"),
                    _("Invalid value: <b>%(value)s</b>\n\n%(error)s") % {
                    "value": new_value, "error": fmt.error}).run()
                return
            else:
                new_value = fmt.validate(new_value)

        comment = entry.value
        if comment.text != new_value and (new_value or comment.shared):
            entry.value = Comment(new_value)
            entry.edited = True
            entry.deleted = False
            model.path_changed(path)

    def __edit_tag_name(self, renderer, path, new_tag, model):
        new_tag = ' '.join(new_tag.splitlines()).lower()
        path = Gtk.TreePath.new_from_string(path)
        entry = model[path][0]
        if new_tag == entry.tag:
            return
        elif not self.__songinfo.can_change(new_tag):
            # Can't add the new tag.
            title = _("Invalid tag")
            msg = _("Invalid tag <b>%s</b>\n\nThe files currently"
                    " selected do not support editing this tag."
                    ) % util.escape(new_tag)
            qltk.ErrorMessage(self, title, msg).run()
        else:
            # FIXME: In case this is a special one we only
            # validate one value and never write it back..

            text = entry.value.text
            if new_tag in massagers.tags:
                fmt = massagers.tags[new_tag]
                if not fmt.is_valid(text):
                    qltk.WarningMessage(
                        self, _("Invalid value"),
                        _("Invalid value: <b>%(value)s</b>\n\n%(error)s") % {
                          "value": text, "error": fmt.error}).run()
                    return
                text = fmt.validate(text)

            if entry.origvalue is None:
                # The tag hasn't been saved yet, so we can just update
                # the name in the model, and the value, since it
                # may have been re-validated.
                entry.tag = new_tag
                entry.value = Comment(text)
            else:
                # The tag has been saved, so delete the old tag and
                # add a new one with the old (or sanitized) value.
                entry.renamed = entry.edited = True
                entry.origtag = entry.tag
                entry.tag = new_tag
                if not entry.value.is_special():
                    entry.value = Comment(text)

            entry.canedit = True

            model.row_changed(path, model.get_iter(path))

    def __button_press(self, view, event):
        if event.button not in [Gdk.BUTTON_PRIMARY, Gdk.BUTTON_MIDDLE]:
            return Gdk.EVENT_PROPAGATE

        x, y = map(int, [event.x, event.y])
        try:
            path, col, cellx, celly = view.get_path_at_pos(x, y)
        except TypeError:
            return Gdk.EVENT_PROPAGATE

        if event.button == Gdk.BUTTON_PRIMARY and col is view.get_columns()[0]:
            model = view.get_model()
            row = model[path]
            entry = row[0]
            # In case we have a (partially) shared value, write it
            # to all songs. For unshared/incomplete do nothing
            if entry.value.shared:
                entry.edited = not entry.edited
                if entry.edited:
                    entry.value.complete = True
            model.row_changed(row.path, row.iter)
            return Gdk.EVENT_STOP
        elif event.button == Gdk.BUTTON_MIDDLE and \
                col == view.get_columns()[2]:
            display = Gdk.DisplayManager.get().get_default_display()
            selection = Gdk.SELECTION_PRIMARY
            if sys.platform == "win32":
                selection = Gdk.SELECTION_CLIPBOARD

            clipboard = Gtk.Clipboard.get_for_display(display, selection)
            for rend in col.get_cells():
                if rend.get_property('editable'):
                    clipboard.request_text(self.__paste,
                                           (rend, path.get_indices()[0]))
                    return Gdk.EVENT_STOP
            else:
                return Gdk.EVENT_PROPAGATE
        else:
            return Gdk.EVENT_PROPAGATE

    def _update(self, songs=None):
        if songs is None:
            songs = self.__songinfo.songs
        else:
            self.__songinfo = AudioFileGroup(songs)
        songinfo = self.__songinfo

        keys = songinfo.keys()
        default_tags = get_default_tags()
        keys = set(keys + default_tags)

        def custom_sort(key):
            try:
                prio = default_tags.index(key)
            except ValueError:
                prio = len(default_tags)
            return (prio, tagsortkey(key))

        if not config.getboolean("editing", "alltags"):
            keys = filter(lambda k: k not in MACHINE_TAGS, keys)

        if not songs:
            keys = []

        with self._view.without_model() as model:
            model.clear()

            for tag in sorted(keys, key=custom_sort):
                canedit = songinfo.can_change(tag)

                # default tags
                if tag not in songinfo:
                    entry = ListEntry(tag, Comment(u""))
                    entry.canedit = canedit
                    model.append(row=[entry])
                    continue

                for value in songinfo[tag]:
                    entry = ListEntry(tag, value)
                    entry.origvalue = value
                    entry.edited = False
                    entry.canedit = canedit
                    entry.deleted = False
                    entry.renamed = False
                    entry.origtag = ""
                    model.append(row=[entry])

        self._buttonbox.set_sensitive(bool(songinfo.can_change()))
        self._revert.set_sensitive(False)
        self._remove.set_sensitive(False)
        self._save.set_sensitive(False)
        self._add.set_sensitive(bool(songs))
        self._parent.set_pending(None)

    def __parent_changed(self, parent, songs):
        self._update(songs)

    def __value_editing_started(self, render, editable, path, model, library):
        if not editable.get_completion():
            tag = model[path][0].tag
            completion = LibraryValueCompletion(tag, library)
            editable.set_completion(completion)

        if isinstance(editable, Gtk.Entry):
            comment = model[path][0].value
            if comment.shared:
                editable.set_text(comment.text)
            else:
                editable.set_text(u"")

    def __tag_editing_started(self, render, editable, path, model, library):
        if not editable.get_completion():
            tags = self.__songinfo.can_change()
            if tags is True:
                tags = USER_TAGS
            completion = qltk.EntryCompletion(tags)
            editable.set_completion(completion)
