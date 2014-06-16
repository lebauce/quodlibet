# Copyright 2011,2013,2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import multiprocessing

from gi.repository import Gst, GObject


class FingerPrintResult(object):

    def __init__(self, song, chromaprint, length):
        self.song = song
        self.chromaprint = chromaprint
        # in seconds
        self.length = length


class FingerPrintPipeline(object):

    def __init__(self):
        super(FingerPrintPipeline, self).__init__()
        self._song = None
        self._setup_pipe()

    def _finish(self, result, error):
        song = self._song
        callback = self._callback
        self.stop()
        callback(self, song, result, error)

    def _setup_pipe(self):
        # pipeline
        self._pipe = pipe = Gst.Pipeline()

        # decode part
        self._filesrc = filesrc = Gst.ElementFactory.make("filesrc", None)
        pipe.add(filesrc)

        decode = Gst.ElementFactory.make("decodebin", None)
        pipe.add(decode)
        Gst.Element.link(filesrc, decode)

        # convert to right format
        convert = Gst.ElementFactory.make("audioconvert", None)
        resample = Gst.ElementFactory.make("audioresample", None)
        pipe.add(convert)
        pipe.add(resample)
        Gst.Element.link(convert, resample)

        # ffdec_mp3 got disabled in gstreamer
        # (for a reason they don't remember), reenable it..
        # http://cgit.freedesktop.org/gstreamer/gst-ffmpeg/commit/
        # ?id=2de5aaf22d6762450857d644e815d858bc0cce65
        ffdec_mp3 = Gst.ElementFactory.find("ffdec_mp3")
        if ffdec_mp3:
            ffdec_mp3.set_rank(Gst.Rank.MARGINAL)

        def new_decoded_pad(convert, pad, *args):
            pad.link(convert.get_static_pad("sink"))

        # decodebin creates pad, we link it
        decode.connect_object("pad-added", new_decoded_pad, convert)

        def sort_decoders(decode, pad, caps, factories):
            # mad is the default decoder with GST_RANK_SECONDARY
            # flump3dec also is GST_RANK_SECONDARY, is slower than mad,
            # but wins because of its name, ffdec_mp3 is faster but had some
            # stability problems (which all seem resolved by now and we call
            # this >= 0.10.31 anyway). Finally there is mpg123
            # (http://gst.homeunix.net/) which is even faster but not in the
            # GStreamer core (FIXME: re-evaluate if it gets merged)
            #
            # Example (atom CPU) 248 sec song:
            #   mpg123: 3.5s / ffdec_mp3: 5.5s / mad: 7.2s / flump3dec: 13.3s

            def set_prio(x):
                i, f = x
                i = {
                    "mad": -1,
                    "ffdec_mp3": -2,
                    "mpg123audiodec": -3
                }.get(f.get_name(), i)
                return (i, f)

            return zip(*sorted(map(set_prio, enumerate(factories))))[1]

        decode.connect("autoplug-sort", sort_decoders)

        chroma = Gst.ElementFactory.make("chromaprint", None)
        fake = Gst.ElementFactory.make("fakesink", None)
        pipe.add(chroma)
        pipe.add(fake)

        Gst.Element.link(resample, chroma)
        Gst.Element.link(chroma, fake)

        # bus
        self._bus = bus = pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._bus_message)

    def start(self, song, callback):
        """Start processing a new song"""

        assert self.is_idle()

        self._song = song
        self._callback = callback

        # use mutagen one, but replace if gstreamer gives us a duration
        self._length = song("~#length")

        self._filesrc.set_property("location", song["~filename"])
        self._bus.add_signal_watch()
        self._pipe.set_state(Gst.State.PLAYING)

    def stop(self):
        """Abort processing. Can be called multiple times"""

        if not self._song:
            return
        self._bus.remove_signal_watch()
        self._pipe.set_state(Gst.State.NULL)
        self._song = None
        self._callback = None

    def is_idle(self):
        """If start() can be called"""

        return not self._song

    def _bus_message(self, bus, message):
        error = None
        if message.type == Gst.MessageType.TAG:
            tags = message.parse_tag()

            ok, value = tags.get_string("chromaprint-fingerprint")
            if ok:
                res = FingerPrintResult(self._song, value, self._length)
                self._finish(res, None)
        elif message.type == Gst.MessageType.ASYNC_DONE:
            # GStreamer probably knows song durations better than we do.
            ok, d = self._pipe.query_duration(Gst.Format.TIME)
            if ok:
                self._length = float(d) / Gst.SECOND
        elif message.type == Gst.MessageType.EOS:
            error = "EOS but no fingerprint"
        elif message.type == Gst.MessageType.ERROR:
            error = str(message.parse_error()[0])

        if error:
            self._finish(None, error)


class FingerPrintPool(GObject.GObject):

    __gsignals__ = {
        # FingerPrintResult
        "fingerprint-done": (
            GObject.SignalFlags.RUN_LAST, None, (object,)),
        # AudioFile
        "fingerprint-started": (
            GObject.SignalFlags.RUN_LAST, None, (object,)),
        # AudioFile, str
        "fingerprint-error": (
            GObject.SignalFlags.RUN_LAST, None, (object, object)),
        }

    def __init__(self, max_workers=None):
        super(FingerPrintPool, self).__init__()

        if max_workers is None:
            max_workers = int(multiprocessing.cpu_count() * 1.5)
        self._max_workers = max_workers

        self._idle = set()
        self._workers = set()
        self._queue = []

    def _get_worker(self):
        """An idle FingerPrintPipeline or None"""

        for worker in self._workers:
            if worker in self._idle:
                self._idle.discard(worker)
                break
        else:
            worker = None
            if len(self._workers) < self._max_workers:
                worker = FingerPrintPipeline()
                self._workers.add(worker)

        if worker:
            assert worker.is_idle()

        return worker

    def _start_song(self, worker, song):
        assert worker.is_idle()
        worker.start(song, self._callback)
        self.emit("fingerprint-started", song)

    def push(self, song):
        """Add a new song to the queue"""

        worker = self._get_worker()
        if worker:
            self._start_song(worker, song)
        else:
            self._queue.append(song)

    def stop(self):
        """Stop everything.

        callback will not be called after this.
        Can be called multiple times.
        """

        for worker in self._workers:
            worker.stop()
        self._workers.clear()
        self._idle.clear()

    def _callback(self, worker, song, result, error):
        self._idle.add(worker)
        if result:
            self.emit("fingerprint-done", result)
        else:
            self.emit("fingerprint-error", song, error)

        if self._queue:
            song = self._queue.pop(0)
            worker = self._get_worker()
            assert worker
            self._start_song(worker, song)
        elif len(self._idle) == len(self._workers):
            # all done, all idle, kill em
            self.stop()
