# -*- coding: utf-8 -*-
# Copyright 2012 - 2014 Christoph Reiter, Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from quodlibet import config
from quodlibet import util
from quodlibet.util.modulescanner import ModuleScanner
from quodlibet.util.dprint import print_d
from quodlibet.qltk.ccb import ConfigCheckButton


def init(folders=None, disable_plugins=False):
    """folders: list of paths to look for plugins
    disable_plugins: disables all plugins, but does not forget which
    plugins are enabled.
    """
    if disable_plugins:
        folders = []
    manager = PluginManager.instance = PluginManager(folders)
    return manager


def quit():
    PluginManager.instance.save()
    PluginManager.instance.quit()
    PluginManager.instance = None


class PluginImportException(Exception):
    desc = ""

    def __init__(self, desc, *args, **kwargs):
        super(PluginImportException, self).__init__(desc)
        self.desc = desc

    def should_show(self):
        """If the error description should be shown to the user"""

        return True


class PluginNotSupportedError(PluginImportException):
    """To hide the plugin (e.g. on Windows)"""

    def __init__(self, msg=None):
        msg = "not supported: %s" % (msg or "unknown reason")
        super(PluginNotSupportedError, self).__init__(msg)

    def should_show(self):
        return False


class MissingModulePluginException(PluginImportException):
    """Consistent Exception for reporting missing modules for plugins"""
    def __init__(self, module_name):
        msg = (_("Couldn't find module '{module}'. Perhaps you need to "
                 "install the package?").format(module=module_name))
        super(MissingModulePluginException, self).__init__(msg)


class MissingGstreamerElementPluginException(PluginImportException):
    """Consistent Exception for reporting missing Gstreamer elements for
    plugins"""
    def __init__(self, element_name):
        msg = (_("Couldn't find GStreamer element '{element}'.")
                 .format(element=element_name))
        super(MissingGstreamerElementPluginException, self).__init__(msg)


def migrate_old_config():
    active = []
    old_keys = ["songsmenuplugins", "eventplugins", "editingplugins",
                "playorderplugins"]
    for key in old_keys:
        key = "active_" + key
        try:
            active.extend(config.get("plugins", key).splitlines())
        except config.Error:
            pass
        else:
            config._config.remove_option("plugins", key)

    if active:
        config.set("plugins", "active_plugins", "\n".join(active))


def list_plugins(module):
    """Return all objects of the module that satisfy the basic
    plugin needs: id, name and don't start with '_'

    If '__all__' is defined, only plugins in '__all__' will be loaded.
    """

    try:
        objs = [getattr(module, attr) for attr in module.__all__]
    except AttributeError:
        objs = [getattr(module, attr) for attr in vars(module)
                if not attr.startswith("_")]

    ok = []
    for obj in objs:
        if hasattr(obj, "PLUGIN_ID"):
            if not hasattr(obj, "PLUGIN_NAME"):
                obj.PLUGIN_NAME = obj.PLUGIN_ID
            ok.append(obj)

    return ok


class PluginModule(object):

    def __init__(self, name, module):
        self.name = name
        self.module = module
        self.plugins = [Plugin(cls) for cls in list_plugins(module)]


class Plugin(object):

    def __init__(self, plugin_cls):
        self.cls = plugin_cls
        self.handlers = []
        self.instance = None

    def __repr__(self):
        return "<%s id=%r name=%r>" % (type(self).__name__, self.id, self.name)

    @property
    def id(self):
        return self.cls.PLUGIN_ID

    @property
    def name(self):
        return self.cls.PLUGIN_NAME

    @property
    def description(self):
        return getattr(self.cls, "PLUGIN_DESC", None)

    @property
    def tags(self):
        tags = getattr(self.cls, "PLUGIN_TAGS", [])
        if isinstance(tags, basestring):
            tags = [tags]
        return tags

    @property
    def icon(self):
        return getattr(self.cls, "PLUGIN_ICON", None)

    def get_instance(self):
        """A singleton"""

        if not getattr(self.cls, "PLUGIN_INSTANCE", False):
            return

        if self.instance is None:
            try:
                obj = self.cls()
            except:
                util.print_exc()
                return
            self.instance = obj

        return self.instance


class PluginHandler(object):
    """A plugin handler can choose to handle plugins, as well as control
    their enabled state."""

    def plugin_handle(self, plugin):
        """Returns `True` IFF this handler can handle `plugin`"""
        raise NotImplementedError

    def plugin_enable(self, plugin):
        """Called to enable / register `plugin`"""
        raise NotImplementedError

    def plugin_disable(self, plugin):
        """Called to disable / de-register `plugin`"""
        raise NotImplementedError


class PluginManager(object):
    """
    The manager takes care of plugin loading/reloading. Interested plugin
    handlers can register them self to get called when plugins get enabled
    or disabled.

    Plugins get exposed when at least one handler shows interest
    in them (by returning True in the handle method).

    Plugins have to be a class which defines PLUGIN_ID, PLUGIN_NAME.
    Plugins that have a true PLUGIN_INSTANCE attribute get instantiated on
    enable and the enabled/disabled methods get called.

    If plugin handlers want a plugin instance, they have to call
    Plugin.get_instance() to get a singleton.

    handlers need to implement the following methods:

        handler.plugin_handle(plugin)
            Needs to return True if the handler should be called
            whenever the plugin's enabled status changes.

        handler.plugin_enable(plugin)
            Gets called if the plugin gets enabled.

        handler.plugin_disable(plugin)
            Gets called if the plugin gets disabled.
            Should remove all references.
    """

    CONFIG_SECTION = "plugins"
    CONFIG_OPTION = "active_plugins"

    instance = None  # default instance

    def __init__(self, folders=None):
        """folders is a list of paths that will be scanned for plugins.
        Plugins in later paths will be preferred if they share a name.
        """

        super(PluginManager, self).__init__()

        if folders is None:
            folders = []

        self.__scanner = ModuleScanner(folders)
        self.__modules = {}     # name: PluginModule
        self.__handlers = []    # handler list
        self.__enabled = set()  # (possibly) enabled plugin IDs

        self.__restore()

    def rescan(self):
        """Scan for plugin changes or to initially load all plugins"""

        print_d("Rescanning..")

        removed, added = self.__scanner.rescan()

        # remember IDs of enabled plugin that get reloaded, so we can enable
        # them again
        reload_ids = []
        for name in removed:
            if name not in added:
                continue
            mod = self.__modules[name]
            for plugin in mod.plugins:
                if self.enabled(plugin):
                    reload_ids.append(plugin.id)

        for name in removed:
            # share the namespace with ModuleScanner for now
            self.__remove_module(name)

        # restore enabled state
        self.__enabled.update(reload_ids)

        for name in added:
            new_module = self.__scanner.modules[name]
            self.__add_module(name, new_module.module)

        print_d("Rescanning done.")

    @property
    def _modules(self):
        return self.__scanner.modules.itervalues()

    @property
    def _plugins(self):
        """All registered plugins"""

        plugins = []
        for module in self.__modules.itervalues():
            for plugin in module.plugins:
                plugins.append(plugin)
        return plugins

    @property
    def plugins(self):
        """Returns a list of plugins with active handlers"""

        return [p for p in self._plugins if p.handlers]

    def register_handler(self, handler):
        """
        Registers a handler, attaching it to any current plugins it
        advertises that it can handle

        `handler` should probably be a `PluginHandler`
        """
        print_d("Registering handler: %r" % type(handler).__name__)

        self.__handlers.append(handler)

        for plugin in self._plugins:
            if not handler.plugin_handle(plugin):
                continue
            if plugin.handlers:
                plugin.handlers.append(handler)
                if self.enabled(plugin):
                    handler.plugin_enable(plugin)
            else:
                plugin.handlers.append(handler)
                if self.enabled(plugin):
                    self.enable(plugin, True, force=True)

    def save(self):
        print_d("Saving plugins: %d active" % len(self.__enabled))
        config.set(self.CONFIG_SECTION,
                   self.CONFIG_OPTION,
                   "\n".join(self.__enabled))

    def enabled(self, plugin):
        """Returns if the plugin is enabled."""

        if not plugin.handlers:
            return False

        return plugin.id in self.__enabled

    def enable(self, plugin, status, force=False):
        """Enable or disable a plugin."""

        if not force and self.enabled(plugin) == bool(status):
            return

        if not status:
            print_d("Disable %r" % plugin.id)
            for handler in plugin.handlers:
                handler.plugin_disable(plugin)

            self.__enabled.discard(plugin.id)

            instance = plugin.instance
            if instance and hasattr(instance, "disabled"):
                try:
                    instance.disabled()
                except Exception:
                    util.print_exc()
        else:
            print_d("Enable %r" % plugin.id)
            obj = plugin.get_instance()
            if obj and hasattr(obj, "enabled"):
                try:
                    obj.enabled()
                except Exception:
                    util.print_exc()
            for handler in plugin.handlers:
                handler.plugin_enable(plugin)
            self.__enabled.add(plugin.id)

    @property
    def failures(self):
        """module name: list of error message text lines"""

        errors = {}
        for name, error in self.__scanner.failures.iteritems():
            exception = error.exception
            if isinstance(exception, PluginImportException):
                if not exception.should_show():
                    continue
                errors[name] = [exception.desc]
            else:
                errors[name] = error.traceback

        return errors

    def quit(self):
        """Disable plugins and tell all handlers to clean up"""

        for name in self.__modules.keys():
            self.__remove_module(name)

    def __remove_module(self, name):
        plugin_module = self.__modules.pop(name)
        for plugin in plugin_module.plugins:
            if plugin.handlers:
                self.enable(plugin, False)

    def __add_module(self, name, module):
        plugin_mod = PluginModule(name, module)
        self.__modules[name] = plugin_mod

        for plugin in plugin_mod.plugins:
            handlers = []
            for handler in self.__handlers:
                if handler.plugin_handle(plugin):
                    handlers.append(handler)
            if handlers:
                plugin.handlers = handlers
                if self.enabled(plugin):
                    self.enable(plugin, True, force=True)

    def __restore(self):
        migrate_old_config()
        active = config.get(self.CONFIG_SECTION,
                            self.CONFIG_OPTION, "").splitlines()

        self.__enabled.update(active)
        print_d("Restoring plugins: %d" % len(self.__enabled))

        for plugin in self._plugins:
            if self.enabled(plugin):
                self.enable(plugin, True, force=True)


PM = PluginManager


class PluginConfigMixin(object):
    """
    Mixin for storage and editing of plugin config in a standard way
    Will use `CONFIG_SECTION`, if defined, for storing config, otherwise,
    it will base the keys on `PLUGIN_ID`.
    """

    @classmethod
    def _config_key(cls, name):
        try:
            prefix = cls.CONFIG_SECTION
        except AttributeError:
            prefix = cls.PLUGIN_ID.lower().replace(" ", "_")
        return "%s_%s" % (prefix, name)

    @classmethod
    def config_get(cls, name, default=""):
        """Gets a config string value for this plugin"""
        return config.get(PM.CONFIG_SECTION, cls._config_key(name), default)

    @classmethod
    def config_set(cls, name, value):
        """Saves a config string value for this plugin"""
        try:
            config.set(PM.CONFIG_SECTION, cls._config_key(name), value)
        except config.Error:
            print_d("Couldn't set config item '%s' to %r" % (name, value))

    @classmethod
    def config_get_bool(cls, name, default=False):
        """Gets a config boolean for this plugin"""
        return config.getboolean(PM.CONFIG_SECTION, cls._config_key(name),
                                 default)

    def config_entry_changed(self, entry, key):
        """React to a change in an gtk.Entry (by saving it to config)"""
        if entry.get_property('sensitive'):
            self.config_set(key, entry.get_text())

    @classmethod
    def ConfigCheckButton(cls, label, name, default=False):
        """
        Create a new `ConfigCheckButton` for `name`, pre-populated correctly
        """
        option = cls._config_key(name)
        try:
            config.getboolean(PM.CONFIG_SECTION, option)
        except config.Error:
            cls.config_set(name, default)
        return ConfigCheckButton(label, PM.CONFIG_SECTION,
                                 option, populate=True)
