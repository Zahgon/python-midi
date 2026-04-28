"""MIDI Clock â€” source and sink, platform-agnostic.

Uses only sequencer.event_write(event, tick=True) for output.
Works identically on CoreMIDI (macOS) and ALSA (Linux).
"""
from __future__ import annotations

import time

import midi


class ClockSource:
    """Clock source: schedules clock pulses via OS sequencer timestamps.

    Call schedule_ahead() from your run loop to keep the buffer full.
    The OS delivers each pulse at the exact kernel-scheduled time.
    """

    PPQ = 24  # pulses per quarter note (MIDI standard)

    def __init__(self, bpm: float = 120.0, sequencer: object = None) -> None:
        if sequencer is None:
            raise ValueError("sequencer is required")
        self._seq = sequencer
        self._bpm = bpm
        self._running = False
        self._pulse: int = 0          # total pulses scheduled since start
        self._scheduled: int = 0      # pulses already sent to sequencer
        self._start_tick: int = 0     # sequencer tick at start
        self._numerator: int = 4
        self._denominator: int = 4

    @property
    def bpm(self) -> float:
        pass

    @bpm.setter
    def bpm(self, value: float) -> None:
        pass

    @property
    def running(self) -> bool:
        pass

    @property
    def pulse(self) -> int:
        pass

    @property
    def beat(self) -> float:
        pass

    @property
    def bar(self) -> float:
        pass

    def set_time_signature(self, numerator: int = 4, denominator: int = 4) -> None:
        pass

    def _ticks_per_pulse(self) -> float:
        """Sequencer ticks per MIDI clock pulse."""
        pass

    def tick_for_pulse(self, pulse: int) -> int:
        """Return the sequencer tick value for a given pulse number."""
        pass

    def start(self) -> None:
        """Send Start event and begin scheduling clock pulses."""
        self._seq.change_tempo(int(self._bpm))
        self._start_tick = self._seq.queue_get_tick_time()
        self._pulse = 0
        self._scheduled = 0
        self._running = True
        ev = midi.StartEvent()
        ev.tick = self._start_tick
        self._seq.event_write(ev, tick=True)

    def stop(self) -> None:
        """Send Stop event."""
        ev = midi.StopEvent()
        ev.tick = self._seq.queue_get_tick_time()
        self._seq.event_write(ev, tick=True)
        self._running = False

    def cont(self) -> None:
        """Send Continue event and resume scheduling."""
        pass

    def schedule_ahead(self, pulses: int = 48) -> None:
        """Pre-schedule clock pulses into the future via event_write(tick=True).

        Only schedules pulses beyond what's already been scheduled.
        Call this periodically from your run loop.
        """
        pass


class ClockSink:
    """Clock sink: processes incoming clock events.

    Uses wall-clock time between ClockEvents for BPM estimation
    (exponential moving average). Feed events from event_read() into process().
    """

    PPQ = 24

    def __init__(self, sequencer_resolution: int) -> None:
        self._resolution = sequencer_resolution
        self._running = False
        self._pulse: int = 0
        self._last_tick: int | None = None
        self._last_time: float | None = None
        self._smoothed_interval: float | None = None  # seconds between pulses
        self._smoothed_tick_interval: float | None = None  # ticks between pulses
        self._alpha: float = 0.1  # EMA smoothing factor
        self._numerator: int = 4
        self._denominator: int = 4

    @property
    def running(self) -> bool:
        pass

    @property
    def pulse(self) -> int:
        pass

    @property
    def beat(self) -> float:
        pass

    @property
    def bar(self) -> float:
        pass

    def set_time_signature(self, numerator: int = 4, denominator: int = 4) -> None:
        pass

    @property
    def bpm(self) -> float:
        """Estimated BPM from wall-clock inter-pulse intervals."""
        pass

    def tick_for_next_pulse(self, offset: int = 0) -> int:
        """Predict tick for the next clock pulse (or +offset pulses ahead)."""
        pass

    def process(self, event: midi.AbstractEvent) -> None:
        """Feed events from event_read(). Recognizes Clock/Start/Stop/Continue/SPP."""
        pass
