# -*- coding: utf-8 -*-
# Copyright 2005 Joe Wreschnig, Michael Urman
#           2012, 2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import contextlib
from cStringIO import StringIO

from gi.repository import Gtk, Gdk, GObject, Pango, GLib
import cairo

from quodlibet import config
from quodlibet.qltk import get_top_parent, is_accel, is_wayland, gtk_version, \
    menu_popup
from quodlibet.qltk.image import get_scale_factor


class TreeViewHints(Gtk.Window):
    """Handle 'hints' for treeviews. This includes expansions of truncated
    columns, and in the future, tooltips."""

    class _MinLabel(Gtk.Label):

        def do_get_preferred_width(*args):
            return (0, Gtk.Label.do_get_preferred_width(*args)[0])

    # input_shape_combine_region does not work under Windows, we have
    # to pass all events to the treeview. In case it does work, this handlers
    # will never be called.
    __gsignals__ = dict.fromkeys(
        ['button-press-event', 'button-release-event',
         'motion-notify-event', 'scroll-event',
         'enter-notify-event', 'leave-notify-event'],
        'override')

    def __init__(self):
        super(TreeViewHints, self).__init__(type=Gtk.WindowType.POPUP)
        self.__clabel = Gtk.Label()
        self.__clabel.show()
        self.__clabel.set_alignment(0, 0.5)
        self.__clabel.set_ellipsize(Pango.EllipsizeMode.NONE)

        screen = self.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba is not None:
            self.set_visual(rgba)

        self.__label = label = self._MinLabel()
        label.set_alignment(0, 0.5)
        label.set_ellipsize(Pango.EllipsizeMode.NONE)
        label.show()
        self.add(label)

        self.add_events(
            Gdk.EventMask.BUTTON_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.KEY_PRESS_MASK |
            Gdk.EventMask.KEY_RELEASE_MASK |
            Gdk.EventMask.ENTER_NOTIFY_MASK |
            Gdk.EventMask.LEAVE_NOTIFY_MASK |
            Gdk.EventMask.SCROLL_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK)

        context = self.get_style_context()
        context.add_class("tooltip")
        context.add_class("ql-tooltip")

        self.set_accept_focus(False)
        self.set_resizable(False)
        self.set_name("gtk-tooltip")
        if gtk_version < (3, 13):
            self.set_border_width(1)

        self.connect('leave-notify-event', self.__undisplay)

        self.__handlers = {}
        self.__current_path = self.__current_col = None
        self.__current_renderer = None
        self.__view = None
        self.__hide_id = None

    def connect_view(self, view):

        # don't depend on padding set by theme, we need the text coordinates
        # to match in all cases
        self._style_provider = style_provider = Gtk.CssProvider()
        style_provider.load_from_data("""
            .ql-tooltip * {
                border-width: 0px;
                padding: 0px;
            }
            .ql-tooltip {
                padding: 0px;
            }
        """)

        # somehow this doesn't apply if we set it on the window, only
        # if set for the screen. gets reverted again in disconnect_view()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.__handlers[view] = [
            view.connect('motion-notify-event', self.__motion),
            view.connect('leave-notify-event', self.__motion),
            view.connect('scroll-event', self.__undisplay),
            view.connect('key-press-event', self.__undisplay),
            view.connect('unmap', self.__undisplay),
            view.connect('destroy', self.disconnect_view),
        ]

    def disconnect_view(self, view):
        try:
            for handler in self.__handlers[view]:
                view.disconnect(handler)
            del self.__handlers[view]
        except KeyError:
            pass
        # Hide if the active treeview is going away
        if view is self.__view:
            self.__undisplay()
        self.set_transient_for(None)

        if self.__hide_id:
            GLib.source_remove(self.__hide_id)
            self.__hide_id = None
            self.hide()

        Gtk.StyleContext.remove_provider_for_screen(
            Gdk.Screen.get_default(), self._style_provider)

    def __motion(self, view, event):
        label = self.__label
        clabel = self.__clabel

        # trigger over row area, not column headers
        if event.window is not view.get_bin_window():
            self.__undisplay()
            return False

        x, y = map(int, [event.x, event.y])

        # For gtk3.16 overlay scrollbars: if our event x coordinate
        # is contained in the scrollbar, hide the tooltip. Unlike other
        # hiding events we don't want to send a leave event to the scrolled
        # window so the overlay scrollbar does't hide and can be interacted
        # with.
        parent = view.get_parent()
        # We only need to check if the tooltip is there since events
        # on the scrollbars don't get forwarded to us anyway.
        if self.__view and parent and isinstance(parent, Gtk.ScrolledWindow):
            vscrollbar = parent.get_vscrollbar()
            res = vscrollbar.translate_coordinates(view, 0, 0)
            if res is not None:
                x_offset = res[0]
                vbar_width = vscrollbar.get_allocation().width
                if x_offset <= x <= x_offset + vbar_width:
                    self.__undisplay(send_leave=False)
                    return False

        # hide if any modifier is active
        if event.get_state() & Gtk.accelerator_get_default_mod_mask():
            self.__undisplay()
            return False

        # get the cell at the mouse position
        try:
            path, col, cellx, celly = view.get_path_at_pos(x, y)
        except TypeError:
            # no hints where no rows exist
            self.__undisplay()
            return False

        col_area = view.get_cell_area(path, col)
        # make sure we are on the same level
        if x < col_area.x:
            self.__undisplay()
            return False

        # hide for partial hidden rows at the bottom
        if y > view.get_visible_rect().height:
            self.__undisplay()
            return False

        # get the renderer at the mouse position and get the xpos/width
        renderers = col.get_cells()
        pos = sorted(zip(map(col.cell_get_position, renderers), renderers))
        pos = filter(lambda ((x, w), r): x < cellx, pos)
        if not pos:
            self.__undisplay()
            return False
        (render_offset, render_width), renderer = pos[-1]

        if self.__current_renderer == renderer and self.__current_path == path:
            return False

        # only ellipsized text renderers
        if not isinstance(renderer, Gtk.CellRendererText):
            self.__undisplay()
            return False

        ellipsize = renderer.get_property('ellipsize')
        if ellipsize == Pango.EllipsizeMode.END:
            expand_left = False
        elif ellipsize == Pango.EllipsizeMode.MIDDLE:
            # depending on where the cursor is
            expand_left = x > col_area.x + render_offset + render_width / 2
        elif ellipsize == Pango.EllipsizeMode.START:
            expand_left = True
        else:
            self.__undisplay()
            return False

        # don't display if the renderer is in editing mode
        if renderer.props.editing:
            self.__undisplay()
            return False

        # set the cell renderer attributes for the active cell
        model = view.get_model()
        col.cell_set_cell_data(model, model.get_iter(path), False, False)

        # the markup attribute is write only, so the markup text needs
        # to be saved on the python side, so we can copy it to the label
        markup = getattr(renderer, "markup", None)
        if markup is None:
            text = renderer.get_property('text')
            set_text = lambda l: l.set_text(text)
        else:
            # markup can also be column index
            if isinstance(markup, int):
                markup = model[path][markup]
            set_text = lambda l: l.set_markup(markup)

        # Use the renderer padding as label padding so the text offset matches
        render_xpad = renderer.get_property("xpad")

        # the renderer xpad is not enough for the tooltip, especially with
        # rounded corners the label gets nearly clipped.
        MIN_HINT_X_PAD = 4
        if render_xpad < MIN_HINT_X_PAD:
            extra_xpad = MIN_HINT_X_PAD - render_xpad
        else:
            extra_xpad = 0

        label.set_padding(render_xpad + extra_xpad, 0)
        set_text(clabel)
        clabel.set_padding(render_xpad, 0)
        label_width = clabel.get_layout().get_pixel_size()[0]
        label_width += clabel.get_layout_offsets()[0] or 0
        # layout offset includes the left padding, so add one more
        label_width += render_xpad

        # CellRenderer width is too large if it's the last one in a column.
        # Use cell_area width as a maximum and limit render_width.
        max_width = col_area.width
        if render_width + render_offset > max_width:
            render_width = max_width - render_offset

        # don't display if it doesn't need expansion
        if label_width < render_width:
            self.__undisplay()
            return False

        dummy, ox, oy = view.get_window().get_origin()
        bg_area = view.get_background_area(path, None)

        # save for adjusting passthrough events
        self.__dx, self.__dy = col_area.x + render_offset, bg_area.y
        self.__dx -= extra_xpad
        if expand_left:
            # shift to the left
            # FIXME: ellipsize start produces a space at the end depending
            # on the text. I don't know how to compute it..
            self.__dx -= (label_width - render_width)

        # final window coordinates/size
        x = ox + self.__dx
        y = oy + self.__dy
        x, y = view.convert_bin_window_to_widget_coords(x, y)

        w = label_width + extra_xpad * 2
        h = bg_area.height

        if not is_wayland():
            # clip if it's bigger than the screen
            screen_border = 5  # leave some space

            if not expand_left:
                space_right = Gdk.Screen.width() - x - w - screen_border

                if space_right < 0:
                    w += space_right
                    label.set_ellipsize(Pango.EllipsizeMode.END)
                else:
                    label.set_ellipsize(Pango.EllipsizeMode.NONE)
            else:
                space_left = x - screen_border
                if space_left < 0:
                    x -= space_left
                    self.__dx -= space_left
                    w += space_left
                    label.set_ellipsize(Pango.EllipsizeMode.START)
                else:
                    label.set_ellipsize(Pango.EllipsizeMode.NONE)
        else:
            label.set_ellipsize(Pango.EllipsizeMode.NONE)

        # Don't show if the resulting tooltip would be smaller
        # than the visible area (if not all is on the display)
        if w < render_width:
            self.__undisplay()
            return False

        self.__view = view
        self.__current_renderer = renderer
        self.__edit_id = renderer.connect('editing-started', self.__undisplay)
        self.__current_path = path
        self.__current_col = col

        if self.__hide_id:
            GLib.source_remove(self.__hide_id)
            self.__hide_id = None

        self.set_transient_for(get_top_parent(view))
        set_text(label)
        self.set_size_request(w, h)

        window = self.get_window()
        if self.get_visible() and window:
            window.move_resize(x, y, w, h)
        else:
            self.move(x, y)
            self.resize(w, h)
            self.show()

        return False

    def __undisplay(self, *args, **kwargs):
        if not self.__view:
            return

        send_leave = kwargs.pop("send_leave", True)

        # XXXXXXXX!: for overlay scrollbars the parent scrolled window
        # listens to notify-leave events to hide them. In case we show
        # the tooltip and leave the SW through the tooltip the SW will never
        # get an event and the scrollbar stays visible forever.
        # This creates a half broken leave event which is just enough
        # to make this work.
        parent = self.__view.get_parent()
        fake_event = None
        if parent and isinstance(parent, Gtk.ScrolledWindow) and send_leave:
            fake_event = Gdk.Event.new(Gdk.EventType.LEAVE_NOTIFY)
            fake_event.any.window = parent.get_window()
            struct = fake_event.crossing
            struct.time = Gtk.get_current_event_time()
            ok, state = Gtk.get_current_event_state()
            if ok:
                struct.state = state
            device = Gtk.get_current_event_device()
            if device is not None:
                struct.set_device(device)

        if self.__current_renderer and self.__edit_id:
            self.__current_renderer.disconnect(self.__edit_id)
        self.__current_renderer = self.__edit_id = None
        self.__current_path = self.__current_col = None
        self.__view = None

        def hide(fake_event):
            if fake_event is not None:
                Gtk.main_do_event(fake_event)

            self.__hide_id = None
            self.hide()
            return False

        if gtk_version < (3, 13):
            # https://bugzilla.gnome.org/show_bug.cgi?id=731055
            # Work around Gnome Shell redraw bugs: it doesn't like
            # multiple hide()/show(), so we try to reduce calls to hide
            # by aborting it if the pointer is on a new cell shortly after.
            self.__hide_id = GLib.timeout_add(20, hide, fake_event)
        else:
            # mutter3.12 and gtk3.14 are a bit broken together, so it's safe
            # to assume we have a fixed mutter release..
            hide(fake_event)

    def __event(self, event):
        if not self.__view:
            return True

        # hack: present the main window on key press
        if event.type == Gdk.EventType.BUTTON_PRESS:
            # hack: present is overridden to present all windows.
            # bypass to only select one
            if not is_wayland():  # present duplicates windows in weston
                Gtk.Window.present(get_top_parent(self.__view))

        def translate_enter_leave_event(event):
            # enter/leave events have different x/y values as motion events
            # so it makes sense to push them to the underlying view as
            # additional motion events.
            # Warning: this may result in motion events outside of the
            # view window.. ?
            new_event = Gdk.Event.new(Gdk.EventType.MOTION_NOTIFY)
            struct = new_event.motion
            for attr in ["x", "y", "x_root", "y_root", "time", "window",
                         "state", "send_event"]:
                setattr(struct, attr, getattr(event.crossing, attr))
            device = Gtk.get_current_event_device()
            if device is not None:
                struct.set_device(device)
            return new_event

        # FIXME: We should translate motion events on the tooltip
        # to crossing events for the underlying view.
        # (I think, no tested) Currently the hover scrollbar stays visible
        # if the mouse leaves the view through the tooltip without the
        # knowledge of the view.

        type_ = event.type
        real_event = None
        if type_ == Gdk.EventType.BUTTON_PRESS:
            real_event = event.button
        elif type_ == Gdk.EventType.BUTTON_RELEASE:
            real_event = event.button
        elif type_ == Gdk.EventType.MOTION_NOTIFY:
            real_event = event.motion
        elif type_ == Gdk.EventType.ENTER_NOTIFY:
            event = translate_enter_leave_event(event)
            real_event = event.motion
        elif type_ == Gdk.EventType.LEAVE_NOTIFY:
            event = translate_enter_leave_event(event)
            real_event = event.motion

        if real_event:
            real_event.x += self.__dx
            real_event.y += self.__dy

        # modifying event.window is a necessary evil, made okay because
        # nobody else should tie to any TreeViewHints events ever.
        event.any.window = self.__view.get_bin_window()

        Gtk.main_do_event(event)

        return True

    def do_button_press_event(self, event):
        return self.__event(event)

    def do_button_release_event(self, event):
        return self.__event(event)

    def do_motion_notify_event(self, event):
        return self.__event(event)

    def do_enter_notify_event(self, event):
        return self.__event(event)

    def do_leave_notify_event(self, event):
        return self.__event(event)

    def do_scroll_event(self, event):
        return self.__event(event)


class DragScroll(object):
    """A treeview mixin for smooth drag and scroll (needs BaseView).

    Call scroll_motion in the 'drag-motion' handler and
    scroll_disable in the 'drag-leave' handler.

    """

    __scroll_delay = None
    __scroll_periodic = None
    __scroll_args = (0, 0, 0, 0)
    __scroll_length = 0
    __scroll_last = None

    def __enable_scroll(self):
        """Start scrolling if it hasn't already"""
        if self.__scroll_periodic is not None or \
                self.__scroll_delay is not None:
            return

        def periodic_scroll():
            """Get the tree coords for 0,0 and scroll from there"""
            wx, wy, dist, ref = self.__scroll_args
            x, y = self.convert_widget_to_tree_coords(0, 0)
            x, y = self.convert_bin_window_to_widget_coords(x, y)

            # We reached an end, stop
            if self.__scroll_last == y:
                self.scroll_disable()
                return
            self.__scroll_last = y

            # If we went full speed for a while.. speed up
            # .. every number is made up here
            if self.__scroll_length >= 50 * ref:
                dist *= self.__scroll_length / (ref * 10)
            if self.__scroll_length < 2000 * ref:
                self.__scroll_length += abs(dist)

            try:
                self.scroll_to_point(-1, y + dist)
            except OverflowError:
                pass
            self.set_drag_dest(wx, wy)
            # we have to re-add the timeout.. otherwise they could add up
            # because scroll can last longer than 50ms
            GLib.source_remove(self.__scroll_periodic)
            self.__scroll_periodic = None
            enable_periodic_scroll()

        def enable_periodic_scroll():
            self.__scroll_periodic = GLib.timeout_add(50, periodic_scroll)
            self.__scroll_delay = None

        self.__scroll_delay = GLib.timeout_add(350, enable_periodic_scroll)

    def scroll_disable(self):
        """Disable all scrolling"""
        if self.__scroll_periodic is not None:
            GLib.source_remove(self.__scroll_periodic)
            self.__scroll_periodic = None
        if self.__scroll_delay is not None:
            GLib.source_remove(self.__scroll_delay)
            self.__scroll_delay = None
        self.__scroll_length = 0
        self.__scroll_last = None

    def scroll_motion(self, x, y):
        """Call with current widget coords during a dnd action to update
           scrolling speed"""

        visible_rect = self.get_visible_rect()
        if visible_rect is None:
            self.scroll_disable()
            return

        # I guess the bin to visible_rect difference is the header height
        # but this could be wrong
        start = self.convert_bin_window_to_widget_coords(0, 0)[1]
        end = visible_rect.height + start

        # Get the font height as size reference
        reference = max(self.create_pango_layout("").get_pixel_size()[1], 1)

        # If the drag is in the scroll area, adjust the speed
        scroll_offset = int(reference * 3)
        in_upper_scroll = (start < y < start + scroll_offset)
        in_lower_scroll = (y > end - scroll_offset)

        # thanks TI200
        def accel(x):
            try:
                return int(1.1 ** (x * 12 / reference)) - (x / reference)
            except ValueError:
                return 0

        if in_lower_scroll:
            diff = accel(y - end + scroll_offset)
        elif in_upper_scroll:
            diff = - accel(start + scroll_offset - y)
        else:
            self.scroll_disable()
            return

        # The area where we can go to full speed
        full_offset = int(reference * 0.8)
        in_upper_full = (start < y < start + full_offset)
        in_lower_full = (y > end - full_offset)
        if not in_upper_full and not in_lower_full:
            self.__scroll_length = 0

        # For the periodic scroll function
        self.__scroll_args = (x, y, diff, reference)

        # The area to trigger a scroll is a bit smaller
        trigger_offset = int(reference * 2.5)
        in_upper_trigger = (start < y < start + trigger_offset)
        in_lower_trigger = (y > end - trigger_offset)

        if in_upper_trigger or in_lower_trigger:
            self.__enable_scroll()


class BaseView(Gtk.TreeView):

    def __init__(self, *args, **kwargs):
        super(BaseView, self).__init__(*args, **kwargs)
        self.connect("key-press-event", self.__key_pressed)

    def __key_pressed(self, view, event):
        def get_first_selected():
            selection = self.get_selection()
            model, paths = selection.get_selected_rows()
            return paths and paths[0] or None

        if is_accel(event, "Right") or is_accel(event, "<ctrl>Right"):
            first = get_first_selected()
            if first:
                self.expand_row(first, False)
        elif is_accel(event, "Left") or is_accel(event, "<ctrl>Left"):
            first = get_first_selected()
            if first:
                if self.row_expanded(first):
                    self.collapse_row(first)
                else:
                    # if we can't collapse, move the selection to the parent,
                    # so that a second attempt collapses the parent
                    model = self.get_model()
                    parent = model.iter_parent(model.get_iter(first))
                    if parent:
                        self.set_cursor(model.get_path(parent))

    def remove_paths(self, paths):
        """Remove rows and restore the selection if it got removed"""

        self.remove_iters(map(self.get_model().get_iter, paths))

    def remove_iters(self, iters):
        """Remove rows and restore the selection if it got removed"""

        self.__remove_iters(iters)

    def remove_selection(self):
        """Remove all currently selected rows and select the position
        of the first removed one."""

        selection = self.get_selection()
        mode = selection.get_mode()
        if mode in (Gtk.SelectionMode.SINGLE, Gtk.SelectionMode.BROWSE):
            model, iter_ = selection.get_selected()
            if iter_:
                self.__remove_iters([iter_], force_restore=True)
        elif mode == Gtk.SelectionMode.MULTIPLE:
            model, paths = selection.get_selected_rows()
            iters = map(model.get_iter, paths or [])
            self.__remove_iters(iters, force_restore=True)

    def select_by_func(self, func, scroll=True, one=False):
        """Calls func with every Gtk.TreeModelRow in the model and selects
        it if func returns True. In case func never returned True,
        the selection will not be changed.

        Returns True if the selection was changed."""

        model = self.get_model()
        if not model:
            return False

        selection = self.get_selection()
        first = True
        for row in model:
            if func(row):
                if not first:
                    selection.select_path(row.path)
                    continue
                self.set_cursor(row.path)
                if scroll:
                    self.scroll_to_cell(row.path, use_align=True,
                                        row_align=0.5)
                first = False
                if one:
                    break
        return not first

    def set_drag_dest(self, x, y, into_only=False):
        """Sets a drag destination for widget coords

        into_only will only highlight rows or the whole widget and no
        lines between rows.
        """

        dest_row = self.get_dest_row_at_pos(x, y)
        if dest_row is None:
            rows = len(self.get_model())
            if not rows:
                (self.get_parent() or self).drag_highlight()
            else:
                self.set_drag_dest_row(Gtk.TreePath(rows - 1),
                                       Gtk.TreeViewDropPosition.AFTER)
        else:
            path, pos = dest_row
            if into_only:
                if pos == Gtk.TreeViewDropPosition.BEFORE:
                    pos = Gtk.TreeViewDropPosition.INTO_OR_BEFORE
                elif pos == Gtk.TreeViewDropPosition.AFTER:
                    pos = Gtk.TreeViewDropPosition.INTO_OR_AFTER
            self.set_drag_dest_row(path, pos)

    def __remove_iters(self, iters, force_restore=False):
        if not iters:
            return

        selection = self.get_selection()
        model = self.get_model()

        if force_restore:
            for iter_ in iters:
                model.remove(iter_)
        else:
            old_count = selection.count_selected_rows()
            for iter_ in iters:
                model.remove(iter_)
            # only restore a selection if all selected rows are gone afterwards
            if not old_count or selection.count_selected_rows():
                return

        # model.remove makes the removed iter point to the next row if possible
        # so check if the last iter is a valid one and select it or
        # simply select the last row
        if model.iter_is_valid(iters[-1]):
            selection.select_iter(iters[-1])
        elif len(model):
            selection.select_path(model[-1].path)

    @contextlib.contextmanager
    def without_model(self):
        """Conext manager which removes the model from the view
        and adds it back afterwards.

        Tries to preserve all state that gets reset on a model change.
        """

        old_model = self.get_model()
        search_column = self.get_search_column()
        sorts = [column.get_sort_indicator() for column in self.get_columns()]
        self.set_model(None)

        yield old_model

        self.set_model(old_model)
        self.set_search_column(search_column)
        for column, value in zip(self.get_columns(), sorts):
            column.set_sort_indicator(value)


def _get_surface_size(surface, scale_factor):
    """Returns (width, height) of a surface or None."""

    # X11
    try:
        w, h = surface.get_width(), surface.get_height()
    except AttributeError:
        pass
    else:
        return w / scale_factor, h / scale_factor

    # Everything else: pycairo doesn't expose get_image() so we have
    # do it the ugly way through png
    fobj = StringIO()
    try:
        surface.write_to_png(fobj)
        fobj.seek(0, 0)
        image_surface = cairo.ImageSurface.create_from_png(fobj)
    except EnvironmentError:
        return
    else:
        try:
            w, h = image_surface.get_width(), image_surface.get_height()
        except AttributeError:
            pass
        else:
            return w / scale_factor, h / scale_factor


class DragIconTreeView(BaseView):
    """TreeView that sets the selected rows as drag icons

    - Drag icons include 3 rows/2 plus a "and more" count
    """

    def __init__(self, *args, **kwargs):
        super(DragIconTreeView, self).__init__(*args, **kwargs)
        self.connect('drag-begin', self.__begin)

    def __begin(self, view, drag_ctx):
        model, paths = view.get_selection().get_selected_rows()
        surface = self.create_multi_row_drag_icon(paths, max_rows=3)
        if surface is not None:
            Gtk.drag_set_icon_surface(drag_ctx, surface)

    def create_multi_row_drag_icon(self, paths, max_rows):
        """Similar to create_row_drag_icon() but creates a drag icon
        for multiple paths or None.

        The resulting surface will draw max_rows rows and point out
        if there are more rows selected.
        """

        if not paths:
            return

        if len(paths) == 1:
            return self.create_row_drag_icon(paths[0])

        # create_row_drag_icon can return None
        icons = [self.create_row_drag_icon(p) for p in paths[:max_rows]]
        icons = [i for i in icons if i is not None]
        if not icons:
            return

        scale_factor = get_scale_factor(self)
        sizes = [_get_surface_size(s, scale_factor) for s in icons]
        if None in sizes:
            return
        width = max([s[0] for s in sizes])
        height = sum([s[1] for s in sizes])

        layout = None
        if len(paths) > max_rows:
            more = _(u"and %d more…") % (len(paths) - max_rows)
            more = "<i>%s</i>" % more
            layout = self.create_pango_layout("")
            layout.set_markup(more)
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_width(Pango.SCALE * (width - 2))
            lw, lh = layout.get_pixel_size()
            height += lh
            height += 6  # padding

        surface = icons[0].create_similar(
            cairo.CONTENT_COLOR_ALPHA, width, height)
        ctx = cairo.Context(surface)

        # render background
        style_ctx = self.get_style_context()
        Gtk.render_background(style_ctx, ctx, 0, 0, width, height)

        # render rows
        count_y = 0
        for icon, (icon_width, icon_height) in zip(icons, sizes):
            ctx.save()
            ctx.set_source_surface(icon, 2, count_y + 2)
            ctx.rectangle(2, count_y + 2, icon_width - 4, icon_height - 4)
            ctx.clip()
            ctx.paint()
            ctx.restore()
            count_y += icon_height

        if layout:
            Gtk.render_layout(style_ctx, ctx, 1, count_y, layout)

        # render border
        Gtk.render_line(style_ctx, ctx, 0, 0, 0, height - 1)
        Gtk.render_line(style_ctx, ctx, 0, height - 1, width - 1, height - 1)
        Gtk.render_line(style_ctx, ctx, width - 1, height - 1, width - 1, 0)
        Gtk.render_line(style_ctx, ctx, width - 1, 0, 0, 0)

        return surface


class MultiDragTreeView(BaseView):
    """TreeView with multirow drag support:

    - Selections don't change until button-release-event...
    - Unless they're a Shift/Ctrl modification, then they happen immediately
    - Drag icons include 3 rows/2 plus a "and more" count
    """

    def __init__(self, *args, **kwargs):
        super(MultiDragTreeView, self).__init__(*args, **kwargs)
        self.connect('button-press-event', self.__button_press)
        self.connect('button-release-event', self.__button_release)
        self.__pending_event = None

    def __button_press(self, view, event):
        if event.button == Gdk.BUTTON_PRIMARY:
            return self.__block_selection(event)

    def __block_selection(self, event):
        x, y = map(int, [event.x, event.y])
        try:
            path, col, cellx, celly = self.get_path_at_pos(x, y)
        except TypeError:
            return True
        self.grab_focus()
        selection = self.get_selection()
        is_selected = selection.path_is_selected(path)
        mod_active = event.get_state() & (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)

        if is_selected and not mod_active:
            self.__pending_event = [x, y]
            selection.set_select_function(lambda *args: False, None)
        elif event.type == Gdk.EventType.BUTTON_PRESS:
            self.__pending_event = None
            selection.set_select_function(lambda *args: True, None)

    def __button_release(self, view, event):
        if self.__pending_event:
            selection = self.get_selection()
            selection.set_select_function(lambda *args: True, None)
            oldevent = self.__pending_event
            self.__pending_event = None

            x, y = map(int, [event.x, event.y])
            if oldevent != [x, y]:
                return True

            try:
                path, col, cellx, celly = self.get_path_at_pos(x, y)
            except TypeError:
                return True
            self.set_cursor(path, col, 0)


class RCMTreeView(BaseView):
    """Emits popup-menu when a row is right-clicked on."""

    def __init__(self, *args, **kwargs):
        super(RCMTreeView, self).__init__(*args, **kwargs)
        self.connect('button-press-event', self.__button_press)

    def __button_press(self, view, event):
        if event.button == Gdk.BUTTON_SECONDARY:
            return self.__check_popup(event)

    def __check_popup(self, event):
        x, y = map(int, [event.x, event.y])
        try:
            path, col, cellx, celly = self.get_path_at_pos(x, y)
        except TypeError:
            return True
        self.grab_focus()
        selection = self.get_selection()
        if not selection.path_is_selected(path):
            self.set_cursor(path, col, 0)
        else:
            col.focus_cell(col.get_cells()[0])
        self.__position_at_mouse = True
        self.emit('popup-menu')
        return True

    def ensure_popup_selection(self):
        try:
            self.__position_at_mouse
        except AttributeError:
            path, col = self.get_cursor()
            if path is None:
                return False
            self.scroll_to_cell(path, col)
            # ensure current cursor path is selected, just like right-click
            selection = self.get_selection()
            if not selection.path_is_selected(path):
                selection.unselect_all()
                selection.select_path(path)
            return True

    def popup_menu(self, menu, button, time):
        try:
            del self.__position_at_mouse
        except AttributeError:
            # suppress menu if the cursor isn't on a real path
            if not self.ensure_popup_selection():
                return False
            pos_func = self.__popup_position
        else:
            pos_func = None

        # force attach the menu to the view
        attached_widget = menu.get_attach_widget()
        if attached_widget != self:
            if attached_widget is not None:
                menu.detach()
            menu.attach_to_widget(self, None)

        menu_popup(menu, None, None, pos_func, None, button, time)
        return True

    def __popup_position(self, menu, *args):
        path, col = self.get_cursor()

        # get a rectangle describing the cell render area (assume 3 px pad)
        rect = self.get_cell_area(path, col)
        padding = 3
        rect.x += padding
        rect.width = max(rect.width - padding * 2, 0)
        rect.y += padding
        rect.height = max(rect.height - padding * 2, 0)

        x, y = self.get_window().get_origin()[1:]
        x, y = self.convert_bin_window_to_widget_coords(x + rect.x, y + rect.y)

        menu.realize()
        ma = menu.get_allocation()
        menu_y = rect.height + y
        if self.get_direction() == Gtk.TextDirection.LTR:
            menu_x = x
        else:
            menu_x = x - ma.width + rect.width

        # on X11/win32 we can use the screen size
        if not is_wayland():

            # fit menu to screen, aligned per text direction
            screen = self.get_screen()
            screen_width = screen.get_width()
            screen_height = screen.get_height()

            # show above row if no space below and enough above
            if menu_y + ma.height > screen_height and y - ma.height > 0:
                menu_y = y - ma.height

            # make sure it's not outside of the screen
            if self.get_direction() == Gtk.TextDirection.LTR:
                menu_x = max(0, min(menu_x, screen_width - ma.width))
            else:
                menu_x = min(max(0, menu_x), screen_width)

        return (menu_x, menu_y, True)  # x, y, move_within_screen


class HintedTreeView(BaseView):
    """A TreeView that pops up a tooltip when you hover over a cell that
    contains ellipsized text."""

    def __init__(self, *args, **kwargs):
        super(HintedTreeView, self).__init__(*args, **kwargs)
        if self.supports_hints():
            try:
                tvh = HintedTreeView.hints
            except AttributeError:
                tvh = HintedTreeView.hints = TreeViewHints()
            tvh.connect_view(self)

    def supports_hints(self):
        """If the treeview hints support is enabled. Can be used to
        display scroll bars instead for example.
        """

        if "QUODLIBET_NO_HINTS" in os.environ:
            return False

        return not config.state('disable_hints')


class _TreeViewColumnLabel(Gtk.Label):
    """A label which fades  into the background at the end; for use
    only in TreeViewColumns.

    The hackery with using the parents allocation is needed because
    the label always gets the allocation it has requested, ignoring
    the actual width of the column header.
    """

    def do_draw(self, ctx):
        # TODO: doesn't do anything in RTL mode

        alloc = self.get_allocation()
        # in case there are no parents use the same alloc which should
        # result in no custom drawing.
        p1 = self.get_parent() or self
        p2 = p1.get_parent() or p1
        p3 = p2.get_parent() or p2
        p2_alloc = p2.get_allocation()
        p3_alloc = p3.get_allocation()

        available_width = p2_alloc.width
        # remove the space needed by the arrow and add the space
        # added by the padding so we only start drawing when we clip
        # the text directly
        available_width += (p2_alloc.x - alloc.x) + (p2_alloc.x - p3_alloc.x)

        if alloc.width <= available_width:
            return Gtk.Label.do_draw(self, ctx)

        req_height = self.get_requisition().height
        w, h = available_width, alloc.height

        # possible when adding new columns.... create_similar will fail
        # in this case below, so just skip.
        if min(w, h) < 0:
            return Gtk.Label.do_draw(self, ctx)

        surface = ctx.get_target()

        # draw label to image surface
        label_surface = surface.create_similar(cairo.CONTENT_COLOR_ALPHA, w, h)
        label_ctx = cairo.Context(label_surface)
        res = Gtk.Label.do_draw(self, label_ctx)

        # create a gradient.
        # make the gradient width depend roughly on the font size
        gradient_width = req_height * 0.8
        gradient_x0 = w - min(float(gradient_width), w)

        pat = cairo.LinearGradient(gradient_x0, 0, w, 0)
        pat.add_color_stop_rgba(0, 1, 1, 1, 1)
        pat.add_color_stop_rgba(w, 0, 0, 0, 0)

        # gradient surface
        grad_surface = surface.create_similar(cairo.CONTENT_COLOR_ALPHA, w, h)
        imgctx = cairo.Context(grad_surface)
        imgctx.set_source(pat)
        imgctx.paint()

        # draw label using the gradient as the alpha channel mask
        ctx.save()
        ctx.set_source_surface(label_surface)
        ctx.mask_surface(grad_surface)
        ctx.restore()

        return res


class TreeViewColumn(Gtk.TreeViewColumn):
    def __init__(self, title="", *args, **kwargs):
        super(TreeViewColumn, self).__init__(None, *args, **kwargs)
        label = _TreeViewColumnLabel(label=title)
        label.set_padding(1, 1)
        label.show()
        self.set_widget(label)

        # the button gets created once the widget gets realized
        self._button = None
        label.__realize = label.connect('realize', self.__realized)
        self._tooltip_text = None

    def __realized(self, widget):
        widget.disconnect(widget.__realize)
        self._button = widget.get_ancestor(Gtk.Button)
        self.set_tooltip_text(self._tooltip_text)

    def set_tooltip_text(self, text):
        if self._button:
            # gtk3.4: set_tooltip_text didn't allow None
            self._button.props.tooltip_text = text
        else:
            self._tooltip_text = text

    def set_use_markup(self, value):
        widget = self.get_widget()
        if isinstance(widget, Gtk.Label):
            widget.set_use_markup(value)


class TreeViewColumnButton(TreeViewColumn):
    """A TreeViewColumn that forwards its header events:
        button-press-event and popup-menu"""

    __gsignals__ = {
        'button-press-event': (GObject.SignalFlags.RUN_LAST, bool, (object,)),
        'popup-menu': (GObject.SignalFlags.RUN_LAST, bool, ()),
    }

    def __init__(self, title="", *args, **kw):
        super(TreeViewColumnButton, self).__init__(title, *args, **kw)
        label = self.get_widget()
        label.__realize = label.connect('realize', self.__connect_menu_event)

    def __connect_menu_event(self, widget):
        widget.disconnect(widget.__realize)
        del widget.__realize
        button = widget.get_ancestor(Gtk.Button)
        if button:
            button.connect('button-press-event', self.button_press_event)
            button.connect('popup-menu', self.popup_menu)

    def button_press_event(self, widget, event):
        return self.emit('button-press-event', event)

    def popup_menu(self, widget):
        return self.emit('popup-menu')


class RCMHintedTreeView(HintedTreeView, RCMTreeView, DragIconTreeView):
    """A TreeView that has hints and a context menu."""
    pass


class AllTreeView(HintedTreeView, RCMTreeView, DragIconTreeView,
                  MultiDragTreeView):
    """A TreeView that has hints, a context menu, and multi-selection
    dragging support."""
    pass
