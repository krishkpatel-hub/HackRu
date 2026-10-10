"""Device-free development runner: python -m companion.main."""

import sys
from uuid import uuid4

from companion.transport.server import BridgeServer
from shared.protocol import SHAPES


def main():
    server = BridgeServer(log=lambda message: print(message, flush=True))
    try:
        server.start()
    except OSError as exc:
        print(f"Cannot listen on 127.0.0.1:8765: {exc}", file=sys.stderr)
        return 1
    print("Connect in Blender, wait for READY, then type: spawn cube|sphere|cylinder|prism; status; quit", flush=True)
    try:
        for line in sys.stdin:
            words = line.strip().split()
            if not words:
                continue
            if words == ["quit"]:
                break
            if words == ["status"]:
                print(f"session={server.session_id} status={server.last_status} error={server.last_error}", flush=True)
            elif len(words) == 2 and words[0] == "spawn" and words[1] in SHAPES:
                identifier = str(uuid4())
                event = {"type": "command", "payload": {"id": identifier, "action": "spawn", "shape": words[1]}}
                accepted = server.emit(event)
                print(f"{'QUEUED' if accepted else 'DISCARDED'} {identifier}: {words[1]}" + (f" ({server.last_error})" if not accepted else ""), flush=True)
            else:
                print("Development syntax: spawn cube|sphere|cylinder|prism, status, quit", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
