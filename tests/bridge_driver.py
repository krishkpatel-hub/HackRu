"""External companion used by Blender integration checks; no Blender imports.

Normal events use BridgeServer.emit. Fault injection is test-only and executed
by the same transport writer, never a second Blender server or writer thread.
"""

import json
from pathlib import Path
import queue
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from companion.transport.server import BridgeServer
from shared.protocol import encode


class TestServer(BridgeServer):
    def __init__(self):
        super().__init__(log=lambda message: print(message, flush=True))
        self.faults = queue.Queue()

    def _tick(self):
        super()._tick()
        if self._session is None or self._session.session_id is None:
            return
        try:
            event = self.faults.get_nowait()
        except queue.Empty:
            return
        data = b"{malformed-json}\n"
        for field, value in (("v", 99), ("session_id", str(uuid4())), ("shape", "monkey")):
            message = self._session.wrap(event)
            if field == "shape":
                message["payload"] = dict(message["payload"], shape=value)
            else:
                message[field] = value
            data += json.dumps(message).encode() + b"\n"
        data += encode(self._session.wrap(event))
        # Fault bytes deliberately bypass the validator, only in this test peer.
        self._channel.outgoing.append(data)
        self._channel.pending_bytes += len(data)


def main():
    server = TestServer()
    server.start()
    try:
        for line in sys.stdin:
            item = json.loads(line)
            if item == {"test": "quit"}:
                break
            if item.get("test") == "faults":
                server.faults.put(item["event"])
            else:
                print(f"EMIT {server.emit(item)}", flush=True)
    finally:
        server.close()


if __name__ == "__main__":
    main()
