import { useEffect, useState } from "react";
import { TraceEvent } from "../types";

export function useTrace() {
  const [events, setEvents] = useState<TraceEvent[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/chat`);
    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: "config",
        session_id: `trace-${crypto.randomUUID()}`,
        mcp_url: "http://127.0.0.1:8080/sse",
      }));
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "tool_start") {
          setEvents((prev) => [
            { id: `${payload.tool}-${payload.tool_index}`, layer: payload.tool },
            ...prev,
          ]);
        }
      } catch {
        // ignore parse errors
      }
    };
    return () => ws.close();
  }, []);

  return { events, setEvents };
}
