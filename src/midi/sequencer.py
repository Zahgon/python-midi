from __future__ import annotations

from collections.abc import MutableSequence

from .events import SetTempoEvent, AbstractEvent


class TempoMap(MutableSequence[SetTempoEvent]):
    def __init__(self, stream: object) -> None:
        self.stream = stream
        self._items: list[SetTempoEvent] = []

    def __getitem__(self, index):
        return self._items[index]

    def __setitem__(self, index, value) -> None:
        self._items[index] = value

    def __delitem__(self, index) -> None:
        del self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def insert(self, index: int, value: SetTempoEvent) -> None:
        self._items.insert(index, value)

    def sort(self, *, key=None, reverse: bool = False) -> None:
        self._items.sort(key=key, reverse=reverse)

    def add_and_update(self, event: SetTempoEvent) -> None:
        pass

    def add(self, event: SetTempoEvent) -> None:
        # get tempo in microseconds per beat
        pass

    def update(self) -> None:
        pass

    def get_tempo(self, offset: int = 0) -> SetTempoEvent:
        pass


class EventStreamIterator:
    def __init__(self, stream: object, window: float) -> None:
        self.stream = stream
        self.trackpool = stream.trackpool
        self.window_length = window
        self.window_edge: float = 0
        self.leftover: AbstractEvent | None = None
        self.events = self.stream.iterevents()
        # First, need to look ahead to see when the
        # tempo markers end
        self.ttpts: list[int] = []
        for tempo in stream.tempomap[1:]:
            self.ttpts.append(tempo.tick)
        # Finally, add the end of track tick.
        self.ttpts.append(stream.endoftrack.tick)
        self._ttpts_iter = iter(self.ttpts)
        # Setup next tempo timepoint
        self.ttp: int = next(self._ttpts_iter)
        self._tempomap_iter = iter(self.stream.tempomap)
        self.tempo = next(self._tempomap_iter)
        self.endoftrack = False

    def __iter__(self) -> EventStreamIterator:
        return self

    def __next_edge(self) -> None:
        pass

    def __next__(self) -> list[AbstractEvent]:
        ret: list[AbstractEvent] = []
        self.__next_edge()
        if self.leftover:
            if self.leftover.tick > self.window_edge:
                return ret
            ret.append(self.leftover)
            self.leftover = None
        for event in self.events:
            if event.tick > self.window_edge:
                self.leftover = event
                return ret
            ret.append(event)
        return ret
