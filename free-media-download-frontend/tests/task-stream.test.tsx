import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTaskStream } from "../app/hooks/use-task-stream";

type Snapshot = { status: "running" | "completed"; value: number };
type Payload = { sequence: number; snapshot: Snapshot };

const eventNames = ["progress", "completed"];

class MockEventSource {
  static instances: MockEventSource[] = [];
  onerror: ((event: Event) => void | Promise<void>) | null = null;
  listeners = new Map<string, ((event: Event) => void)[]>();
  closed = false;

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: EventListenerOrEventListenerObject) {
    const callback =
      typeof listener === "function"
        ? listener
        : (event: Event) => listener.handleEvent(event);
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), callback]);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, payload: Payload) {
    const event = new MessageEvent("message", { data: JSON.stringify(payload) });
    this.listeners.get(name)?.forEach((listener) => listener(event));
  }

  async fail() {
    await this.onerror?.(new Event("error"));
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useTaskStream", () => {
  it("loads a snapshot after disconnect and reconnects with replay deduplication", async () => {
    const updates: Snapshot[] = [];
    const getSnapshot = vi.fn(async () => ({ status: "running", value: 7 }) as Snapshot);

    const { unmount } = renderHook(() =>
      useTaskStream<Snapshot, Payload>({
        streamKey: "job-1",
        eventsUrl: "/api/v1/jobs/job-1/events",
        eventNames,
        parse: (value) => JSON.parse(value) as Payload,
        getSnapshot,
        onUpdate: (snapshot) => updates.push(snapshot),
        snapshotFromPayload: (payload) => payload.snapshot,
        isTerminal: (snapshot) => snapshot.status === "completed",
      }),
    );

    expect(MockEventSource.instances).toHaveLength(1);
    await act(async () => {
      await MockEventSource.instances[0].fail();
    });
    expect(getSnapshot).toHaveBeenCalledTimes(1);
    expect(updates.at(-1)).toEqual({ status: "running", value: 7 });

    act(() => vi.advanceTimersByTime(1000));
    expect(MockEventSource.instances).toHaveLength(2);

    act(() => {
      MockEventSource.instances[1].emit("completed", {
        sequence: 3,
        snapshot: { status: "completed", value: 100 },
      });
      MockEventSource.instances[1].emit("completed", {
        sequence: 3,
        snapshot: { status: "completed", value: 999 },
      });
    });
    expect(updates.at(-1)).toEqual({ status: "completed", value: 100 });
    expect(MockEventSource.instances[1].closed).toBe(true);

    unmount();
    expect(MockEventSource.instances[1].closed).toBe(true);
  });
});
