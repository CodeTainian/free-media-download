"use client";

import { useEffect, useRef } from "react";
import { apiUrl } from "../lib/api/client";

type SequencedPayload = { sequence: number };

type TaskStreamOptions<TSnapshot, TPayload extends SequencedPayload> = {
  streamKey: string | null;
  eventsUrl: string | null;
  eventNames: readonly string[];
  parse: (value: string) => TPayload | null;
  getSnapshot: () => Promise<TSnapshot>;
  onUpdate: (snapshot: TSnapshot) => void;
  snapshotFromPayload: (payload: TPayload) => TSnapshot | null;
  onEvent?: (payload: TPayload) => void;
  isTerminal: (snapshot: TSnapshot) => boolean;
  onExhausted?: () => void;
};

const reconnectDelays = [1000, 2000, 4000, 8000, 10000];

export function useTaskStream<TSnapshot, TPayload extends SequencedPayload>({
  streamKey,
  eventsUrl,
  eventNames,
  parse,
  getSnapshot,
  onUpdate,
  snapshotFromPayload,
  isTerminal,
  onExhausted,
  onEvent,
}: TaskStreamOptions<TSnapshot, TPayload>) {
  const callbacks = useRef({
    parse,
    getSnapshot,
    onUpdate,
    snapshotFromPayload,
    isTerminal,
    onExhausted,
    onEvent,
  });

  useEffect(() => {
    callbacks.current = {
      parse,
      getSnapshot,
      onUpdate,
      snapshotFromPayload,
      isTerminal,
      onExhausted,
      onEvent,
    };
  });

  useEffect(() => {
    if (!streamKey || !eventsUrl) return;

    let disposed = false;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    let lastSequence = 0;
    let recovering = false;

    const closeSource = () => {
      source?.close();
      source = null;
    };

    const connect = () => {
      if (disposed) return;
      recovering = false;
      source = new EventSource(apiUrl(eventsUrl));

      const handle = (event: Event) => {
        const message = event as MessageEvent<string>;
        const payload = callbacks.current.parse(message.data);
        if (!payload || payload.sequence <= lastSequence) return;
        lastSequence = payload.sequence;
        reconnectAttempt = 0;
        callbacks.current.onEvent?.(payload);
        const snapshot = callbacks.current.snapshotFromPayload(payload);
        if (snapshot) {
          callbacks.current.onUpdate(snapshot);
          if (callbacks.current.isTerminal(snapshot)) closeSource();
        }
      };

      eventNames.forEach((eventName) => source?.addEventListener(eventName, handle));
      source.onerror = async () => {
        if (disposed || recovering) return;
        recovering = true;
        closeSource();
        try {
          const snapshot = await callbacks.current.getSnapshot();
          if (disposed) return;
          callbacks.current.onUpdate(snapshot);
          if (callbacks.current.isTerminal(snapshot)) return;
        } catch {
          // A reconnect can still recover by replaying the server's buffered events.
        }
        if (disposed) return;
        if (reconnectAttempt >= reconnectDelays.length) {
          callbacks.current.onExhausted?.();
          return;
        }
        const delay = reconnectDelays[reconnectAttempt];
        reconnectAttempt += 1;
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      closeSource();
      if (timer) clearTimeout(timer);
    };
  }, [eventsUrl, eventNames, streamKey]);
}
