#!/usr/bin/env python2
# Copyright 2012,2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

"""A simple command line tagger"""

# TODO:
#  - unicode handling
#  - some commands missing

import sys
import os
import string
import stat
import re
import shlex
import shutil
import tempfile
import subprocess
from optparse import OptionParser

from quodlibet.formats import MusicFile, EmbeddedImage
from quodlibet import config
from quodlibet import const
from quodlibet import parse
from quodlibet import util
from quodlibet.util.path import mtime, fsdecode
from quodlibet.util.dprint import print_, Colorise
from quodlibet.util.tags import USER_TAGS, MACHINE_TAGS, sortkey
from quodlibet.util.tagsfrompath import TagsFromPattern


PROGRAM = os.path.basename(sys.argv[0])
VERSION = const.VERSION
COMMANDS = []


class CommandError(Exception):
    pass


class Command(object):
    """Base class for commands.

    Subclasses can override _add_options() and _execute()
    """

    NAME = None
    DESCRIPTION = None
    USAGE = None

    def __init__(self, options=None):
        usage = "%s %s %s" % (PROGRAM, self.NAME, self.USAGE)
        self.__parser = OptionParser(usage=usage, description=self.DESCRIPTION)
        if options is None:
            options = self.__parser.parse_args([])[0]
        self.__options = options
        self._add_options(self.__parser)

    def _add_options(self, parser):
        """Override to add options to the parser"""

        pass

    @property
    def verbose(self):
        return self.__options.verbose

    @verbose.setter
    def verbose(self, value):
        self.__options.verbose = bool(value)

    def log(self, text):
        """Print output if --verbose was passed"""

        if self.verbose:
            return print_(text, sys.stderr)

    def load_song(self, path):
        """Load a song. Raises CommandError in case it fails"""

        self.log("Load file: %r" % path)
        song = MusicFile(path)
        if not song:
            raise CommandError(_("Failed to load file: %r") % path)
        return song

    def save_songs(self, songs):
        """Save all passed songs"""

        self.log("Saving songs...")

        for song in songs:
            try:
                song.write()
            except Exception as e:
                raise CommandError(e)

    def _execute(self, options, args):
        """Override to execute something"""

        raise NotImplemented

    def print_help(self, file=None):
        """Print the help information about the comand"""

        if file is None:
            file = sys.stdout

        self.__parser.print_help(file=file)

    def execute(self, args):
        """Execute the command"""

        options, args = self.__parser.parse_args(args)
        self._execute(options, args)


class ListCommand(Command):
    NAME = "list"
    DESCRIPTION = _("List tags")
    USAGE = "[-a] [-t] [-c <c1>,<c2>...] <file>"

    def _add_options(self, p):
        p.add_option("-t", "--terse", action="store_true",
                     help=_("Print terse output"))
        p.add_option("-c", "--columns", action="store", type="string",
                     help=_("Columns to display and order in terse mode (%s)")
                     % "desc,value,tag")
        p.add_option("-a", "--all", action="store_true",
                     help=_("Also list programmatic tags"))

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 1:
            raise CommandError(_("Too many arguments"))

        path = args[0]
        headers = [_("Description"), _("Value"), _("Tag")]
        nicks = ["desc", "value", "tag"]

        if not options.columns:
            order = nicks
        else:
            order = map(str.strip, options.columns.split(","))

        song = self.load_song(path)
        tags = list_tags(song, machine=options.all, terse=options.terse)

        if options.terse:
            print_terse_table(tags, nicks, order)
        else:
            print_table(tags, headers, nicks, order)


class TagsCommand(Command):
    NAME = "tags"
    DESCRIPTION = _("List all common tags")
    USAGE = "[-t] [-c <c1>,<c2>...]"

    def _add_options(self, p):
        p.add_option("-t", "--terse", action="store_true",
                     help=_("Print terse output"))
        p.add_option("-c", "--columns", action="store", type="string",
                     help=_("Columns to display and order in terse mode (%s)")
                     % "tag,desc")

    def _execute(self, options, args):
        if len(args) != 0:
            raise CommandError(_("Too many arguments"))

        headers = [_("Tag"), _("Description")]
        nicks = ["tag", "desc"]

        if not options.columns:
            order = nicks
        else:
            order = map(str.strip, options.columns.split(","))

        tags = []
        for key in USER_TAGS:
            tags.append((key, util.tag(key)))
        tags.sort()

        if not options.terse:
            print_table(tags, headers, nicks, order)
        else:
            print_terse_table(tags, nicks, order)


class DumpCommand(Command):
    NAME = "dump"
    DESCRIPTION = _("Print all tags to stdout")
    USAGE = "<src-file>"

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 1:
            raise CommandError(_("Too many arguments"))

        # load file
        path = args[0]
        song = self.load_song(path)

        # dump, sort and skip internal tags
        lines = sorted(song.to_dump().splitlines())
        print_("\n".join((l for l in lines if not l.startswith("~"))))


class LoadCommand(Command):
    NAME = "load"
    DESCRIPTION = _("Load tags dumped with 'dump'")
    USAGE = "[--dry-run] [--ignore-errors] <dest-file> [<tag-file>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))
        p.add_option("--ignore-errors", action="store_true",
                     help=_("Skip tags that can't be written"))

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 2:
            raise CommandError(_("Too many arguments"))


class CopyCommand(Command):
    NAME = "copy"
    DESCRIPTION = _("Copy tags from one file to another")
    USAGE = "[--dry-run] [--ignore-errors] <source> <dest>"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))
        p.add_option("--ignore-errors", action="store_true",
                     help=_("Skip tags that can't be written"))

    def _execute(self, options, args):
        if len(args) < 2:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 2:
            raise CommandError(_("Too many arguments"))

        if options.dry_run:
            self.verbose = True

        source_path = args[0]
        dest_path = args[1]

        source = self.load_song(source_path)
        dest = self.load_song(dest_path)

        for key in source.realkeys():
            self.log("Copy %r" % key)
            if not options.ignore_errors and not dest.can_change(key):
                raise CommandError(_("Can't copy tag %r to file: %r") %
                                   (key, dest_path))
            for value in source.list(key):
                dest.add(key, value)

        if not options.dry_run:
            self.save_songs([dest])


def get_editor_args(fallback_command="nano"):
    """Returns a list starting with a command and optional arguments
    for editing text files.

    List is never empty.
    Can't fail, but the result might not be a valid/existing command.
    """

    if "VISUAL" in os.environ:
        editor = os.environ["VISUAL"]
    elif "EDITOR" in os.environ:
        editor = os.environ["EDITOR"]
    else:
        editor = fallback_command

    # to support VISUAL="geany -i"
    try:
        editor_args = shlex.split(editor)
    except ValueError:
        # well, no idea
        editor_args = [editor]

    if not editor_args:
        editor_args = [fallback_command]

    return editor_args


def copy_mtime(src, dst):
    """Copy mtime/atime from src to dst. Might raise OSError."""

    stat_src = os.stat(src)
    os.utime(dst, (stat_src[stat.ST_ATIME], stat_src[stat.ST_MTIME]))


class EditCommand(Command):
    NAME = "edit"
    DESCRIPTION = _("Edit tags in a text editor")
    USAGE = "[--dry-run] <file>"

    # TODO: support editing multiple files

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))

    def _song_to_text(self, song):
        # to text
        lines = []
        for key in sorted(song.realkeys(), key=sortkey):
            for value in song.list(key):
                lines.append(u"%s=%s" % (key, value))

        lines += [
            u"",
            u"#" * 80,
            u"# Lines that are empty or start with '#' will be ignored",
            u"# File: %r" % fsdecode(song("~filename")),
        ]

        return u"\n".join(lines)

    def _text_to_song(self, text, song):
        assert isinstance(text, unicode)

        # parse
        tags = {}
        for line in text.splitlines():
            if not line.strip() or line.startswith(u"#"):
                continue
            try:
                key, value = line.split(u"=", 1)
            except ValueError:
                continue

            tags.setdefault(key, []).append(value)

        # apply changes, sort to always have the same output
        for key in sorted(song.realkeys(), key=sortkey):
            new = tags.pop(key, [])
            old = song.list(key)
            for value in old:
                if value not in new:
                    self.log("Remove %s=%s" % (key, value))
                    song.remove(key, value)
            for value in new:
                if value not in old:
                    self.log("Add %s=%s" % (key, value))
                    song.add(key, value)

        for key, values in tags.iteritems():
            if not song.can_change(key):
                raise CommandError(
                    "Can't change key '%(key-name)s'." % {"key-name": key})
            for value in values:
                self.log("Add %s=%s" % (key, value))
                song.add(key, value)

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 1:
            raise CommandError(_("Too many arguments"))

        song = self.load_song(args[0])
        dump = self._song_to_text(song).encode("utf-8")

        # write to tmp file
        fd, path = tempfile.mkstemp(suffix=".txt")

        # XXX: copy mtime here so we can test for changes in tests by
        # setting a out of date mtime on the source song file
        copy_mtime(args[0], path)

        try:
            try:
                os.write(fd, dump)
            finally:
                os.close(fd)

            # only parse the result if the editor returns 0 and the mtime has
            # changed
            old_mtime = mtime(path)

            editor_args = get_editor_args()
            self.log("Using editor: %r" % editor_args)

            try:
                subprocess.check_call(editor_args + [path])
            except subprocess.CalledProcessError as e:
                self.log(unicode(e))
                raise CommandError(_("Editing aborted"))
            except OSError as e:
                self.log(unicode(e))
                raise CommandError(
                    _("Starting text editor '%(editor-name)s' failed.") % {
                        "editor-name": editor_args[0]})

            was_changed = mtime(path) != old_mtime
            if not was_changed:
                raise CommandError(_("No changes detected"))

            with open(path, "rb") as h:
                data = h.read()

        finally:
            os.unlink(path)

        try:
            text = data.decode("utf-8")
        except ValueError as e:
            raise CommandError("Invalid data: %r" % e)

        if options.dry_run:
            self.verbose = True
        self._text_to_song(text, song)

        if not options.dry_run:
            self.save_songs([song])


class SetCommand(Command):
    NAME = "set"
    DESCRIPTION = _("Set a tag and remove existing values")
    USAGE = "[--dry-run] <tag> <value> <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))

    def _execute(self, options, args):
        if len(args) < 3:
            raise CommandError(_("Not enough arguments"))

        tag = args[0]
        value = args[1].decode("utf-8")
        paths = args[2:]

        songs = []
        for path in paths:
            song = self.load_song(path)

            if not song.can_change(tag):
                raise CommandError(_("Can not set %r") % tag)

            self.log("Set %r to %r" % (value, tag))
            if tag in song:
                del song[tag]
            song.add(tag, value)
            songs.append(song)

        if not options.dry_run:
            self.save_songs(songs)


class ClearCommand(Command):
    NAME = "clear"
    DESCRIPTION = _("Remove tags")
    USAGE = "[--dry-run] [-a | -e <pattern> | <tag>] <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))
        p.add_option("-e", "--regexp", action="store", type="string",
                     help=_("Value is a regular expression"))
        p.add_option("-a", "--all", action="store_true",
                     help=_("Remove all tags"))

    def _execute(self, options, args):
        if options.all and options.regexp is not None:
            raise CommandError(_("Can't combine '--all' with '--regexp'"))

        if options.regexp is not None or options.all:
            if len(args) < 1:
                raise CommandError(_("Not enough arguments"))
            paths = args
        else:
            if len(args) < 2:
                raise CommandError(_("Not enough arguments"))
            paths = args[1:]

        if options.dry_run:
            self.verbose = True

        songs = []
        for path in paths:
            song = self.load_song(path)

            tags = []
            realkeys = song.realkeys()
            if options.all:
                tags.extend(realkeys)
            elif options.regexp is not None:
                e = re.compile(options.regexp)
                tags.extend(filter(e.match, realkeys))
            else:
                tag = args[0]
                if tag in realkeys:
                    tags.append(tag)

            for tag in tags:
                self.log("Remove tag %r" % tag)
                if not song.can_change(tag):
                    raise CommandError(
                        _("Can't remove %r from %r") % (tag, path))
                del song[tag]

            if tags:
                songs.append(song)

        if not options.dry_run:
            self.save_songs(songs)


class RemoveCommand(Command):
    NAME = "remove"
    DESCRIPTION = _("Remove a tag value")
    USAGE = "[--dry-run] <tag> [-e <pattern> | <value>] <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help=_("Show changes, don't apply them"))
        p.add_option("-e", "--regexp", action="store", type="string",
                     help=_("Value is a regular expression"))

    def _execute(self, options, args):
        if options.regexp is None:
            if len(args) < 3:
                raise CommandError(_("Not enough arguments"))
        else:
            if len(args) < 2:
                raise CommandError(_("Not enough arguments"))

        if options.dry_run:
            self.verbose = True

        tag = args[0]
        if options.regexp is not None:
            match = re.compile(options.regexp).match
            paths = args[1:]
        else:
            value = args[1]
            paths = args[2:]
            match = lambda v: v == value

        songs = []
        for path in paths:
            song = self.load_song(path)

            if tag not in song:
                continue

            for v in song.list(tag):
                if match(v):
                    self.log("Remove %r from %r" % (v, tag))
                    song.remove(tag, v)
            songs.append(song)

        if not options.dry_run:
            self.save_songs(songs)


class AddCommand(Command):
    NAME = "add"
    DESCRIPTION = _("Add a tag value")
    USAGE = "<tag> <value> <file> [<files>]"

    def _execute(self, options, args):
        if len(args) < 3:
            raise CommandError(_("Not enough arguments"))

        tag = args[0]
        value = args[1].decode("utf-8")
        paths = args[2:]

        songs = []
        for path in paths:
            song = self.load_song(path)

            if not song.can_change(tag):
                raise CommandError(_("Can not set %r") % tag)

            self.log("Add %r to %r" % (value, tag))
            song.add(tag, value)
            songs.append(song)

        self.save_songs(songs)


class InfoCommand(Command):
    NAME = "info"
    DESCRIPTION = _("List file information")
    USAGE = "[-t] [-c <c1>,<c2>...] <file>"

    def _add_options(self, p):
        p.add_option("-t", "--terse", action="store_true",
                     help=_("Print terse output"))
        p.add_option("-c", "--columns", action="store", type="string",
                     help=_("Columns to display and order in terse mode (%s)")
                     % "desc,value")

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))
        elif len(args) > 1:
            raise CommandError(_("Too many arguments"))

        path = args[0]
        song = self.load_song(path)

        headers = [_("Description"), _("Value")]
        nicks = ["desc", "value"]

        if not options.columns:
            order = nicks
        else:
            order = map(str.strip, options.columns.split(","))

        if not options.terse:
            tags = []
            for key in ["~format", "~length", "~#bitrate", "~filesize"]:
                tags.append((util.tag(key), unicode(song(key))))

            print_table(tags, headers, nicks, order)
        else:
            tags = []
            for key in ["~format", "~#length", "~#bitrate", "~#filesize"]:
                tags.append((key.lstrip("#~"), unicode(song(key))))

            print_terse_table(tags, nicks, order)


class ImageSetCommand(Command):
    NAME = "image-set"
    DESCRIPTION = _("Set the provided image as primary embedded image and "
                    "remove all other embedded images")
    USAGE = "<image-file> <file> [<files>]"

    def _execute(self, options, args):
        if len(args) < 2:
            raise CommandError(_("Not enough arguments"))

        image_path = args[0]
        paths = args[1:]

        image = EmbeddedImage.from_path(image_path)
        if not image:
            raise CommandError(_("Failed to load image file: %r") % image_path)

        songs = [self.load_song(p) for p in paths]

        for song in songs:
            if not song.can_change_images:
                raise CommandError(
                    _("Image editing not supported for %(file_name)s "
                      "(%(file_format)s)") % {
                      "file_name": song("~filename"),
                      "file_format": song("~format")
                    })

        for song in songs:
            song.set_image(image)


class ImageClearCommand(Command):
    NAME = "image-clear"
    DESCRIPTION = _("Remove all embedded images")
    USAGE = "<file> [<files>]"

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))

        paths = args
        songs = [self.load_song(p) for p in paths]

        for song in songs:
            if not song.can_change_images:
                raise CommandError(
                    _("Image editing not supported for %(file_name)s "
                      "(%(file_format)s)") % {
                      "file_name": song("~filename"),
                      "file_format": song("~format")
                    })

        for song in songs:
            song.clear_images()


class ImageExtractCommand(Command):
    NAME = "image-extract"
    DESCRIPTION = (
        _("Extract embedded images to %(filepath)s") % {
            "filepath": "<destination>/<filename>-<index>.(jpeg|png|..)"
        }
    )
    USAGE = "[--dry-run] [--primary] [-d <destination>] <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help="don't save images")
        p.add_option("--primary", action="store_true",
                     help="only extract the primary image")
        p.add_option("-d", "--destination", action="store", type="string",
                     help=_("Path to where the images will be saved to "
                            "(defaults to the working directory)"))

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError(_("Not enough arguments"))

        # dry run implies verbose
        if options.dry_run:
            self.verbose = True

        paths = args
        for path in paths:
            song = self.load_song(path)

            # get the primary one or all of them
            if options.primary:
                image = song.get_primary_image()
                images = [image] if image else []
            else:
                images = song.get_images()

            self.log("Images for %r: %r" % (path, images))

            if not images:
                continue

            # get the basename from the song without the extension
            basename = os.path.basename(path)
            name = os.path.splitext(basename)[0]

            # at least two places, but same length for all images
            number_pattern = "%%0%dd" % (max(2, len(images) - 1))

            for i, image in enumerate(images):
                # get a appropriate file extension or use fallback
                extensions = image.extensions
                ext = extensions[0] if extensions else ".image"

                if options.primary:
                    # mysong.mp3 -> mysong.jpeg
                    filename = "%s.%s" % (name, ext)
                else:
                    # mysong.mp3 -> mysong-00.jpeg
                    pattern = "%s-" + number_pattern + ".%s"
                    filename = pattern % (name, i, ext)

                if options.destination is not None:
                    filename = os.path.join(options.destination, filename)

                self.log("Saving image %r" % filename)
                if not options.dry_run:
                    with open(filename, "wb") as h:
                        shutil.copyfileobj(image.file, h)


class RenameCommand(Command):
    NAME = "rename"
    DESCRIPTION = _("Rename files based on tags")
    USAGE = "[--dry-run] <pattern> <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help="show changes, don't apply them")

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError("Not enough arguments")


class FillCommand(Command):
    NAME = "fill"
    DESCRIPTION = _("Fill tags based on the file path")
    USAGE = "[--dry-run] <pattern> <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help="show changes, don't apply them")

    def _execute(self, options, args):
        if len(args) < 2:
            raise CommandError("Not enough arguments")

        pattern_text = args[0]
        self.log("Using pattern: %r" % pattern_text)
        paths = args[1:]

        pattern = TagsFromPattern(pattern_text)

        songs = []
        for path in paths:
            song = self.load_song(path)
            for header in pattern.headers:
                if not song.can_change(header):
                    raise CommandError(_("Can not set %r") % header)
            songs.append(song)

        if options.dry_run:
            self.__preview(pattern, songs)
        else:
            self.__apply(pattern, songs)

    def __apply(self, pattern, songs):
        for song in songs:
            match = pattern.match(song)
            self.log("%r: %r" % (song("~basename"), match))
            for header in pattern.headers:
                if header in match:
                    value = match[header]
                    song[header] = value

        self.save_songs(songs)

    def __preview(self, pattern, songs):
        rows = []
        for song in songs:
            match = pattern.match(song)
            row = [fsdecode(song("~basename"))]
            for header in pattern.headers:
                row.append(match.get(header, u""))
            rows.append(row)

        headers = [_("File")] + pattern.headers
        nicks = ["file"] + pattern.headers
        print_table(rows, headers, nicks, nicks)


class FillTracknumberCommand(Command):
    NAME = "fill-tracknumber"
    DESCRIPTION = _("Fill tracknumbers for all files")
    USAGE = "[--dry-run] [--start] [--total] <file> [<files>]"

    def _add_options(self, p):
        p.add_option("--dry-run", action="store_true",
                     help="show changes, don't apply them")
        p.add_option("--start", action="store_true",
                     help="tracknumber to start with")
        p.add_option("--total", action="store_true",
                     help="total number of tracks")

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError("Not enough arguments")


class PrintCommand(Command):
    NAME = "print"
    DESCRIPTION = _("Print tags based on the given pattern")
    USAGE = "[-p <pattern>] <file> [<files>]"

    def _add_options(self, p):
        p.add_option("-p", "--pattern", action="store", type="string",
                     help="use a custom pattern")

    def _execute(self, options, args):
        if len(args) < 1:
            raise CommandError("Not enough arguments")

        pattern = options.pattern
        if pattern is None:
            pattern = "<artist~album~tracknumber~title>"

        self.log("Using pattern: %r" % pattern)

        try:
            pattern = parse.Pattern(pattern)
        except ValueError:
            raise CommandError("Invalid pattern: %r" % pattern)

        paths = args
        error = False
        for path in paths:
            try:
                print_(pattern % self.load_song(path))
            except CommandError:
                error = True

        if error:
            raise CommandError("One or more files failed to load.")


class HelpCommand(Command):
    NAME = "help"
    DESCRIPTION = _("Display help information")
    USAGE = "[<command>]"

    def _execute(self, options, args):
        if len(args) > 1:
            raise CommandError("Too many arguments")

        for cmd in COMMANDS:
            if cmd.NAME == args[0]:
                cmd().print_help()
                break
        else:
            raise CommandError("Unknown command")


def filter_table(rows, nicks, order):
    """Returns a new table with rows filtered and reordered"""

    if nicks == order:
        return rows

    mapping = []
    lower = [h.lower() for h in nicks]
    for o in order:
        try:
            index = lower.index(o.lower())
        except ValueError:
            raise CommandError(
                _("'%s' is not a valid column name (%s).") %
                (o, ",".join(nicks)))
        else:
            mapping.append(index)

    if not mapping:
        return []

    new_rows = []
    for row in rows:
        new_rows.append([row[i] for i in mapping])
    return new_rows


def print_table(rows, headers, nicks, order):
    """Print a fancy table"""

    rows.insert(0, headers)
    rows = filter_table(rows, nicks, order)
    if not rows:
        return

    widths = []
    for c in range(len(rows[0])):
        widths.append(max(map(lambda r: len(r[c]), rows)))

    seperator = " %s " % Colorise.gray("|")
    format_string = seperator.join(["%%-%ds" % w for w in widths])

    header = []
    for i, h in enumerate(rows.pop(0)):
        header.append(string.ljust(h, widths[i], " "))
    line_width = len("   ".join(header)) + 2
    header = [Colorise.bold(h) for h in header]
    header_line = " " + (" %s " % Colorise.gray("|")).join(header)

    print_(header_line.rstrip())
    print_(Colorise.gray("-" * line_width))

    for row in rows:
        print_(" " + (format_string % tuple(row)).rstrip())


def print_terse_table(rows, nicks, order):
    """Print a terse table"""

    for row in filter_table(rows, nicks, order):
        row = [r.replace("\\", "\\\\") for r in row]
        row = [r.replace(":", r"\:") for r in row]
        print_(":".join(row))


def list_tags(song, machine=False, terse=False):
    """Return a list of key, value pairs"""

    keys = set(song.realkeys())
    if not machine:
        keys.difference_update(MACHINE_TAGS)

    tags = []
    for key in sorted(keys, key=sortkey):
        for value in song.list(key):
            if not terse:
                # QL can't handle multiline values and splits them by \n.
                # Tags with Windows line endings leave a \r, messing up the
                # table layout
                value = value.rstrip("\r")
                # Normalize tab
                value = value.replace("\t", " ")
            tags.append((util.tag(key), value, key))
    return tags


def print_help(parser, file=None):
    """Print a short help list for all commands"""

    if file is None:
        file = sys.stdout

    parser.print_help(file=file)

    cl = ["", "Commands:"]
    for command in COMMANDS:
        cl.append("   %-17s %s" % (command.NAME, command.DESCRIPTION))
    cl.append("")
    cl.append("See '%s help <command>' for more information "
              "on a specific command." % PROGRAM)

    print_("\n".join(cl), file)


def run(argv=sys.argv):
    # the main optparser
    usage = "%s [--version] [--help] [--verbose] <command> [<args>]" % PROGRAM
    parser = OptionParser(usage=usage)

    parser.remove_option("--help")
    parser.add_option("-h", "--help", action="store_true")
    parser.add_option("--version", action="store_true",
                      help="print version")
    parser.add_option("-v", "--verbose", action="store_true",
                      help="verbose output")

    # no args, print help (might change in the future)
    if len(argv) <= 1:
        print_help(parser, file=sys.stderr)
        return 1

    # collect options for the main command and get the command offset
    offset = -1
    pre_command = []
    for i, a in enumerate(argv):
        if i == 0:
            continue
        elif a.startswith("-"):
            pre_command.append(a)
        else:
            offset = i
            break

    # parse the global options
    options = parser.parse_args(pre_command)[0]

    # --help somewhere
    if options.help:
        print_help(parser)
        return 0

    # --version somewhere
    if options.version:
        print_("%s version %s" % (PROGRAM, VERSION))
        return 0

    # no sub command followed, help to stderr
    if offset == -1:
        print_help(parser, file=sys.stderr)
        return 1
    arg = argv[offset]

    # special case help and list all commands
    if arg == "help":
        # no command, list all commands
        if len(argv) == 2:
            print_help(parser)
            return 0

    # get the right sub command and pass the remaining args
    for command in COMMANDS:
        if command.NAME == arg:
            cmd = command(options)
            try:
                cmd.execute(argv[offset + 1:])
            except CommandError as e:
                print_(u"%s: %s" % (command.NAME, e), sys.stderr)
                return 1
            break
    else:
        print_(u"Unknown command '%s'. See '%s help'." % (arg, PROGRAM),
               sys.stderr)
        return 1

    return 0


COMMANDS.extend([ListCommand, DumpCommand, CopyCommand,
            SetCommand, RemoveCommand, AddCommand, PrintCommand,
            HelpCommand, ClearCommand, InfoCommand, TagsCommand,
            ImageExtractCommand, ImageSetCommand, ImageClearCommand,
            EditCommand, FillCommand])
COMMANDS.sort(key=lambda c: c.NAME)

# TODO
# RenameCommand
# FillTracknumberCommand, LoadCommand

if __name__ == "__main__":
    config.init()
    sys.exit(run())
