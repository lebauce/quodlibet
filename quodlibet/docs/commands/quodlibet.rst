===========
 quodlibet
===========

--------------------------------
audio library manager and player
--------------------------------

:Manual section: 1

SYNOPSIS
========

| **quodlibet** [ **--print-playing** | *control* ]
| **exfalso** [ *directory* ]

DESCRIPTION
===========

Quod Libet is a music management program. It provides several different
ways to view your audio library, as well as support for Internet radio and
audio feeds. It has extremely flexible metadata tag editing and searching
capabilities.

This manual page is only a short reference for Quod Libet. Complete
documentation is available at http://code.google.com/p/quodlibet/wiki/Guide.

OPTIONS
=======

--enqueue filename|query
    Enqueue a filename or query results

--filter tag=value
    Filter on a tag value

--focus
    Focus the running player

--hide-window
    Hide main window

--next
    Jump to next song

--list-browsers
    List available browsers

--open-browser=BrowserName
    Open a new browser

--order=inorder|shuffle|weighted|onesong|toggle
    Set or toggle the playback order

--pause
    Pause playback

--play
    Start playback

--play-file=filename
    Play a file

--play-pause
    Toggle play/pause mode

--previous
    Jump to previous song or restart if near the beginning

--force-previous
    Jump to previous song

--print-playlist
    Print the current playlist

--print-queue
    Print the contents of the queue

--print-playing
    Print out information about the currently playing song. You may
    provide in a string like the kind described in the RENAMING FILES
    section below.

--query=search-string
    Search your audio library

--quit
    Exit Quod Libet

--random=tag
    Filter on a random value

--repeat=off|on|t
    Turn repeat off, on, or toggle

--seek=[+|-][HH:]MM:SS
    Seek within the playing song

--set-browser=BrowserName
    Set the current browser

--set-rating=0.0..1.0
    Rate the playing song

--show-window
    Hide main window

--start-playing
    Begin playing immediately

--status
    Print playing status

--toggle-window
    Toggle main window visibility

--unfilter
    Remove active browser filters

--unqueue=filename|query
    Unqueue a file or query

--volume=(+\|-\|)0..100
    Set the volume

ALBUM COVERS
============

Album covers should be put in the same directory as the songs they apply
to, and have "folder", "front", or "cover" in their filenames. If you want
to store multiple albums in the same directory but keep distinct cover
images, the name of the appropriate image file must contain the labelid tag
value, e.g. COCX-32760 cover.jpg.

TIED TAGS
=========

Many places in Quod Libet allow you to use "tied tags". Tied tags are two
tag names joined together with a "~" like "title~version" or "album~part".
Tied tags result in "nice" displays even when one of the tags is missing;
for example, "title~version" will result in Title - Version when a version
tag is present, but only Title when one isn't. You can tie any number of
tags together.

SEARCH SYNTAX
=============

All of Quod  Libet's search boxes support advanced searches of the
following forms:

\

| tag = value
| tag = !value
| tag = "value"
| tag = /value/
| tag = &(value1, value2)
| tag = \|(value1, value2)
| !tag = value
| \|(tag1 = value1, tag2 = value2)
| &(tag1 = value1, tag2 = value2)
| #(numerictag < value)
| #(numerictag = value)
| #(numerictag > value)

\

The 'c' postfix on strings or regular expressions makes the  search
case-sensitive. Numeric values may be given as integers, floating-point
numbers, MM:SS format, or simple English, e.g. "3 days", "2 hours".

See http://code.google.com/p/quodlibet/wiki/Guide_Searching.

All internal tags begin with a ~ character. Non-numeric internal tags are
~base‐ name, ~dirname, ~filename, ~format, ~length, ~people, and ~rating.
Numeric internal tags are ~#added, ~#bitrate, ~#disc, ~#lastplayed,
~#laststarted, ~#length, ~#mtime, ~#playcount, ~#skipcount, and ~#track.

See http://code.google.com/p/quodlibet/wiki/Guide_InternalTags.

RENAMING FILES
==============

Quod Libet allows you to rename files based on their tags. In some cases
you may wish to alter the filename depending on whether some tags are
present or missing, in addition to their values. A common pattern might be

``<tracknumber>. <title~version>``

You can use a '|' to only text when a tag is present:

``<tracknumber|<tracknumber>. ><title~version>``

You can also specify literal text to use if the tag is missing by adding another '|':

``<album|<album>|No Album> - <title>``

See http://code.google.com/p/quodlibet/wiki/Guide_Renaming.


AUDIO BACKENDS
==============

Quod Libet uses GStreamer for audio playback. It tries to read your GConf
GStreamer configuration, but if that fails it falls back to osssink. You can
change the pipeline option in ~/.quodlibet/config to use a different sink, or
pass options to the sink. For example, you might use esdsink or alsasink
device=hw:1.

See http://code.google.com/p/quodlibet/wiki/Guide_AudioBackends.


FILES
=====

~/.quodlibet/songs
   A pickled Python dict of cached metadata. Deleting this file will remove all
   songs from your library.

~/.quodlibet/config
   Quod Libet's configuration file. This file is overwritten when Quod Libet
   exits.

~/.quodlibet/current
   A "key=value" file containing information about the currently playing song.

~/.quodlibet/control
   A FIFO connected to the most-recently-started instance of the program.
   --next, --previous, etc., use this to control the player.

~/.quodlibet/plugins/
   Put plugins (from http://code.google.com/p/quodlibet/wiki/Guide_Plugins)
   here.

~/.quodlibet/browsers/
   Put custom library browsers here.

See http://code.google.com/p/quodlibet/wiki/Guide_Extending.

BUGS
====

See http://code.google.com/p/quodlibet/issues/list for a list of all
currently open bugs and feature requests.

AUTHORS
=======

Joe Wreschnig and Michael Urman are the primary authors of Quod Libet.

SEE ALSO
========

| http://code.google.com/p/quodlibet/wiki/Guide,
| http://code.google.com/p/quodlibet/wiki/FAQ,
| ``regex``\(7), ``gst-launch``\(1)
