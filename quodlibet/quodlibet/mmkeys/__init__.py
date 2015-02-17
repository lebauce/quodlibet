# -*- coding: utf-8 -*-
# Copyright 2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from ._base import MMKeysAction, MMKeysImportError


def iter_backends():
    try:
        from .gnome import GnomeBackend, MateBackend
    except MMKeysImportError:
        pass
    else:
        yield GnomeBackend
        yield MateBackend

    try:
        from .keybinder import KeybinderBackend
    except MMKeysImportError:
        pass
    else:
        yield KeybinderBackend

    try:
        from .pyhook import PyHookBackend
    except MMKeysImportError:
        pass
    else:
        yield PyHookBackend

    try:
        from .osx import OSXBackend
    except MMKeysImportError:
        pass
    else:
        yield OSXBackend


def find_active_backend():
    print_d("Trying to find a mmkeys backend")
    for backend in iter_backends():
        if backend.is_active():
            print_d("Found %r" % backend.__name__)
            return backend


class MMKeysHandler(object):
    """Manages multiple keybinding backends and translates the generated
    events to actions on the player backend.
    """

    def __init__(self, app_name, window, player):
        self._backend = None
        self._window = window
        self._player = player
        self._app_name = app_name

    def start(self):
        kind = find_active_backend()
        if not kind:
            return
        self._backend = kind(self._app_name, self._callback)
        # grab on start for cases when the window is hidden on start
        self._backend.grab()

        self._window.connect("notify::is-active", self._focus_event)

    def quit(self):
        if self._backend:
            self._backend.cancel()
            self._backend = None
            self._window = None
            self._player = None

    def _focus_event(self, window, param):
        if window.get_property(param.name) and self._backend:
            self._backend.grab()

    def _callback(self, action):
        print_d("Event %r from %r" % (action, type(self._backend).__name__))

        player = self._player
        if action == MMKeysAction.PREV:
            player.previous()
        elif action == MMKeysAction.NEXT:
            player.next()
        elif action == MMKeysAction.STOP:
            player.stop()
        elif action == MMKeysAction.PLAY:
            if player.song is None:
                player.reset()
            else:
                player.paused = False
        elif action == MMKeysAction.PLAYPAUSE:
            if player.song is None:
                player.reset()
            else:
                player.paused ^= True
        elif action == MMKeysAction.PAUSE:
            player.paused = True
        else:
            assert 0, "unhandled event"
