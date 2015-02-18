.. _RenamingFiles:

Renaming files
==============

Basic Syntax
------------

Quod Libet allows you to rename files based on their tags. In some cases
you may wish to alter the filename depending on whether some tags are
present or missing, in addition to their values. A common pattern might be::

    <tracknumber>. <title~version>


You can use a ``|`` to only insert text when a tag is present::

    <tracknumber|<tracknumber>. ><title~version>


You can also specify literal text to use if the tag is missing by adding
another `|`::

    <album|<album>|No Album> - <title>

A reasonable use of albumartist would be::

    <albumartist|<albumartist>|<artist|<artist>|No artist>>


..which uses the first of the following: Albumartist, Artist or "No artist".

You can of course also move files across your filesystem to another
directory by mixing path elements and ``<tag>`` syntax::

    /home/*username*/Music/<artist>/<album>/...


Simple Renames
--------------

Like tagging by filename, renaming by tags uses tag names enclosed by
``<...>`` to substitute values. To rename songs as their artist followed
by their title, use ``<artist> - <title>`` (The file extension, .ogg, .mpc,
and so on, is automatically added). Other common patterns include

 * ``<tracknumber>. <title>``
 * ``<tracknumber>. <artist> - <title>``
 * ``~/music/<artist> - <album>/<tracknumber>. <title>``
 * ``~/music/<artist>/<album>/<tracknumber>. <title>``

You can also use tied tags to rename, e.g. ``<artist~title>``.


Creating Directories
--------------------

Note that if you use ``/`` (a directory separator) in your filename, you
''must'' start the pattern with a ``/`` (or a ``~/``, which expands to your
home directory). To see why, consider what would happen if you tried to
rename the same file twice with ``<artist>/<title>``. The first time it
would go under ``Artist/Title.ogg``, the second time,
``Artist/Artist/Title.ogg``. When you specify the full path, this can't
happen.

If you don't use a `/` in the pattern, the file gets put in the same directory.


Conditional Renaming
--------------------

Consider the ``<tracknumber>. <title>`` pattern.

When the file is missing a track number, you get a filename that starts
with ., which isn't good. So Quod Libet lets you use ''conditional
renaming'' to avoid that.

To use conditional text, after the tag name (but inside the ``<...>``) put
a ``|`` (a pipe). Then after the pipe, place all the text you want,
including other tag names inside ``<...>``. That text will only be added when
that tag isn't empty.

To avoid the original problem, only display the track number, period, and
space when the track number tag exists:

``<tracknumber|<tracknumber>. ><title>``.

Quod Libet also lets you change the text if a tag ''doesn't'' exist: Use a
second pipe. ``<tracknumber|<tracknumber>|00>. <title>`` will use the
track number at the start of the filename if it exists, or *00* if it
doesn't.


Go crazy with conditions / More examples
----------------------------------------

So you basically want to remember that it goes ``<condition|<conditional
tag>|<else tag>>`` You can however even put conditions inside each other.
Here's an example that I just created, and so far it seems to work:

I first had::

    /mnt/musik/<genre|<genre>/><artist|<artist>|Unknown>/<album|<album>/><tracknumber|<tracknumber> - ><title>

Let's dissect this:

 * ``/mnt/musik``: My basic music partition
 * ``<genre|<genre>/>``: If there is a tag "genre", put the song into that
   folder (creating the folder if necessary). If there is no tag genre,
   skip this level in the folder hierarchy (note that the trailing slash
   of ``<genre>/`` is inside the < > that delineate the conditional "block".
 * ``<artist>|<artist>|Unknown>/``: If there's a tag artist, put everything
   into that folder, else put into a folder called "Unknown". Not that the
   trailing slash is outside the < > that delineate the conditional block,
   since we always want that folder level.
 * ``<album|<album>/>``: Album folder as needed, else skip
 * ``<tracknumber|<tracknumber - >``: Prepend tracknumber if it exists
 * ``<title>``: Duh.

However, for songs that don't have a genre tag, I wanted to use a tag I use
called "language" and sort into that folder instead. But I have some songs
that have a genre tag and also a language tag, and those songs should only
go into the genre folder; the language folder should be ignored.

Turns out QL can do this just fine, by expanding the ``<genre>`` conditional
block in the expression above to ``<genre|<genre>/|<language|<language>/>>``.

Basically, the pipe after the second ``<genre>/`` introduces what should be
done if the first condition isn't met (i.e. no genre tag), but here instead
of putting straightforward text or another label we then introduce a second
conditional block, ``<language|<language/>>``, which puts in a language tag
folder, if the song has a tag "language".

The full expression now looks like this::

    /mnt/musik/<genre|<genre>/|<language|<language>/>><artist|<artist>|Unknown>/<album|<album>/><tracknumber|<tracknumber> - ><title>
