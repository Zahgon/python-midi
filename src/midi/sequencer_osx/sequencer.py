"""macOS CoreMIDI sequencer with tick-accurate playback and recording.

Mirrors the ALSA sequencer API for cross-platform compatibility.
"""
from __future__ import annotations

import threading
import time
from collections import deque

import midi
from . import coremidi as cm


class Sequencer:
    SEQUENCER_TYPE = "coremidi"

    def __init__(self, *, sequencer_name: str = "python-midi",
                 sequencer_tempo: int = 120,
                 sequencer_resolution: int = 1000) -> None:
        self.sequencer_tempo = sequencer_tempo
        self.sequencer_resolution = sequencer_resolution
        self._queue_running = False
        self._start_host_time: int = 0
        self._start_wall_time: float = 0.0
        self._client = cm.midi_client_create(sequencer_name)
        self._output_port: cm.MIDIPortRef | None = None
        self._input_port: cm.MIDIPortRef | None = None
        self._dest_endpoint: cm.MIDIEndpointRef | None = None
        self._source_endpoint: cm.MIDIEndpointRef | None = None
        self._read_queue: deque[midi.Event] = deque()
        self._read_proc: cm.MIDIReadProc | None = None

    def __del__(self) -> None:
        try:
            cm.midi_client_dispose(self._client)
        except Exception:
            pass

    def _usec_per_tick(self) -> float:
        return (60_000_000.0 / self.sequencer_tempo) / self.sequencer_resolution

    def _tick_to_host_time(self, tick: int) -> int:
        nanos = int(tick * self._usec_per_tick() * 1000)
        return self._start_host_time + cm.nanos_to_host_time(nanos)

    def _host_time_to_tick(self, host_time: int) -> int:
        elapsed_nanos = cm.host_time_to_nanos(host_time - self._start_host_time)
        usec_per_tick = self._usec_per_tick()
        return int(elapsed_nanos / (usec_per_tick * 1000))

    def start_sequencer(self) -> None:
        if not self._queue_running:
            self._start_host_time = cm.mach_absolute_time()
            self._start_wall_time = time.time()
            self._queue_running = True

    def stop_sequencer(self) -> None:
        self._queue_running = False

    def continue_sequencer(self) -> None:
        pass

    def change_tempo(self, tempo: int) -> bool:
        self.sequencer_tempo = tempo
        return True

    def queue_get_tick_time(self) -> int:
        if not self._queue_running:
            return 0
        return self._host_time_to_tick(cm.mach_absolute_time())

    def queue_get_real_time(self) -> tuple[int, int]:
        pass

    def drain(self) -> None:
        pass  # CoreMIDI handles delivery

    def drop_output(self) -> None:
        pass  # No output buffer to flush

    def output_pending(self) -> int:
        pass

    def subscribe_port(self, client: int, port: int) -> None:
        raise NotImplementedError("Subclasses must implement subscribe_port")


class SequencerHardware(Sequencer):
    """Enumerate CoreMIDI devices, sources, and destinations."""

    class Client:
        def __init__(self, device_ref: cm.MIDIDeviceRef, name: str) -> None:
            self.client = device_ref
            self.name = name
            self._ports: dict[str, SequencerHardware.Client.Port] = {}

        def __str__(self) -> str:
            retstr = '] client(%d) "%s"\n' % (self.client, self.name)
            for port in self:
                retstr += str(port)
            return retstr

        def add_port(self, port_ref: int, name: str, caps: int) -> None:
            pass

        def __iter__(self):
            return iter(self._ports.values())

        def __len__(self) -> int:
            return len(self._ports)

        def get_port(self, key: str) -> SequencerHardware.Client.Port:
            pass
        __getitem__ = get_port

        class Port:
            CAP_READ = 1
            CAP_WRITE = 2

            def __init__(self, port: int, name: str, caps: int) -> None:
                self.port = port          # primary ref (backward compat)
                self.name = name
                self.caps = caps
                self.source_ref = port if (caps & self.CAP_READ) else None
                self.dest_ref = port if (caps & self.CAP_WRITE) else None
                self.caps_read = bool(caps & self.CAP_READ)
                self.caps_write = bool(caps & self.CAP_WRITE)

            def __str__(self) -> str:
                flags = []
                if self.caps_read:
                    flags.append('r')
                if self.caps_write:
                    flags.append('w')
                flags_str = ', '.join(flags)
                refs = []
                if self.source_ref is not None:
                    refs.append('source=%d' % self.source_ref)
                if self.dest_ref is not None:
                    refs.append('dest=%d' % self.dest_ref)
                refs_str = ' (%s)' % ', '.join(refs) if refs else ''
                return ']   port [%s] "%s"%s\n' % (flags_str, self.name, refs_str)

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._clients: dict[str, SequencerHardware.Client] = {}
        self._enumerate()

    def _enumerate(self) -> None:
        pass

    def __iter__(self):
        return iter(self._clients.values())

    def __len__(self) -> int:
        return len(self._clients)

    def get_client(self, key: str) -> SequencerHardware.Client:
        pass
    __getitem__ = get_client

    def get_client_and_port(self, cname: str, pname: str) -> tuple[int, int]:
        client = self[cname]
        port = client[pname]
        return (client.client, port.port)

    def __str__(self) -> str:
        retstr = ''
        for client in self:
            retstr += str(client)
        return retstr


def _build_midi_bytes(event: midi.Event) -> bytes | None:
    """Convert a midi Event to raw MIDI bytes for CoreMIDI."""
    if isinstance(event, midi.EndOfTrackEvent):
        return None
    if isinstance(event, midi.NoteOnEvent):
        return bytes([0x90 | event.channel, event.pitch, event.velocity])
    if isinstance(event, midi.NoteOffEvent):
        return bytes([0x80 | event.channel, event.pitch, event.velocity])
    if isinstance(event, midi.ControlChangeEvent):
        return bytes([0xB0 | event.channel, event.control, event.value])
    if isinstance(event, midi.ProgramChangeEvent):
        return bytes([0xC0 | event.channel, event.value])
    if isinstance(event, midi.ChannelAfterTouchEvent):
        return bytes([0xD0 | event.channel, event.value])
    if isinstance(event, midi.PitchWheelEvent):
        value = event.pitch + 0x2000
        return bytes([0xE0 | event.channel, value & 0x7F, (value >> 7) & 0x7F])
    if isinstance(event, midi.AfterTouchEvent):
        return bytes([0xA0 | event.channel, event.pitch, event.value])
    if isinstance(event, midi.SysexEvent):
        return bytes([0xF0]) + bytes(event.data) + bytes([0xF7])
    if isinstance(event, midi.ClockEvent):    return bytes([0xF8])
    if isinstance(event, midi.StartEvent):    return bytes([0xFA])
    if isinstance(event, midi.ContinueEvent): return bytes([0xFB])
    if isinstance(event, midi.StopEvent):     return bytes([0xFC])
    if isinstance(event, midi.SongPositionPointerEvent):
        value = event.position
        return bytes([0xF2, value & 0x7F, (value >> 7) & 0x7F])
    return None


def _msg_length(status: int) -> int:
    """Return the total message length (including status byte) for a channel message."""
    pass


def _parse_channel_msg(data: bytes, i: int, status: int) -> midi.Event | None:
    """Parse a single channel message starting at offset i."""
    pass


def _parse_midi_bytes(data: bytes, timestamp: int) -> midi.Event | None:
    """Parse raw MIDI bytes into a midi Event (single message, legacy API)."""
    pass


def _parse_all_midi_bytes(data: bytes, timestamp: int) -> list[midi.Event]:
    """Parse all MIDI messages from a CoreMIDI packet data buffer."""
    pass


def find_source_by_name(name: str) -> cm.MIDIEndpointRef | None:
    """Find a CoreMIDI source endpoint by its display name."""
    pass


class _WriteMixin:
    """Mixin for MIDI output via CoreMIDI."""
    _virtual_source = None
    _dest_endpoint = None
    OUTPUT_BUFFER_SIZE: int = 65536

    def create_virtual_source(self, name: str) -> None:
        """Create a virtual MIDI source visible to other CoreMIDI clients."""
        self._virtual_source = cm.midi_source_create(self._client, name)

    def subscribe_port_by_index(self, index: int) -> None:
        """Subscribe to a destination by its index in the system destination list."""
        pass

    def event_write(self, event: midi.Event, direct: bool = False,
                    relative: bool = False, tick: bool = False) -> int | None:
        if isinstance(event, midi.EndOfTrackEvent):
            return None
        if self._virtual_source is None and self._dest_endpoint is None:
            raise RuntimeError("No destination subscribed")

        if isinstance(event, midi.SetTempoEvent):
            self.change_tempo(int(event.bpm))
            return self.OUTPUT_BUFFER_SIZE

        midi_bytes = _build_midi_bytes(event)
        if midi_bytes is None:
            return None

        if direct:
            timestamp = 0
        elif tick:
            timestamp = self._tick_to_host_time(event.tick)
        else:
            ms = getattr(event, 'msdelay', 0)
            nanos = int(ms * 1_000_000)
            timestamp = self._start_host_time + cm.nanos_to_host_time(nanos)

        pktlist = cm.MIDIPacketList()
        pkt = cm.packet_list_init(pktlist)
        pkt = cm.packet_list_add(pktlist, pkt, timestamp, midi_bytes)
        if self._virtual_source is not None:
            cm.midi_received(self._virtual_source, pktlist)
        else:
            cm.midi_send(self._output_port, self._dest_endpoint, pktlist)
        return self.OUTPUT_BUFFER_SIZE


class _ReadMixin:
    """Mixin for MIDI input via CoreMIDI."""

    def _setup_read(self) -> None:
        pass

    def _on_read(self, pktlist_ptr, read_proc_ref_con, src_conn_ref_con) -> None:
        """Callback invoked by CoreMIDI on a separate thread."""
        pass

    def subscribe_port_by_index(self, index: int) -> None:
        """Subscribe to a source by its index in the system source list."""
        pass

    def event_read(self) -> midi.Event | None:
        with self._lock:
            if self._read_queue:
                return self._read_queue.popleft()
        return None


class SequencerWrite(_WriteMixin, Sequencer):
    """Schedule MIDI output with tick-accurate timestamps via CoreMIDI."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._output_port = cm.midi_output_port_create(self._client, "output")

    def subscribe_port(self, client: int, port: int) -> None:
        """Subscribe to a destination endpoint for writing."""
        self._dest_endpoint = cm.MIDIEndpointRef(int(port))


class SequencerRead(_ReadMixin, Sequencer):
    """Subscribe to MIDI input and read events."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._setup_read()

    def subscribe_port(self, client: int, port: int) -> None:
        """Subscribe to a source endpoint for reading."""
        source = cm.MIDIEndpointRef(int(port))
        cm.midi_port_connect_source(self._input_port, source)
        self._source_endpoint = source


class SequencerDuplex(_ReadMixin, _WriteMixin, Sequencer):
    """Both read and write MIDI events."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._output_port = cm.midi_output_port_create(self._client, "output")
        self._setup_read()

    def subscribe_read_port(self, client: int, port: int) -> None:
        pass

    def subscribe_write_port(self, client: int, port: int) -> None:
        self._dest_endpoint = cm.MIDIEndpointRef(int(port))

    def subscribe_port(self, client: int, port: int) -> None:
        self.subscribe_write_port(client, port)
