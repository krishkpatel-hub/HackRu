"""Run from the repository root: python -m companion.voice --typed."""

import argparse
import json
import threading

from .service import VoiceError, run_voice, stderr_feedback


def print_json(event: dict) -> None:
    print(json.dumps(event, separators=(",", ":")), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Air Modeler voice commands")
    parser.add_argument("--typed", action="store_true", help="Read commands from stdin (default)")
    parser.parse_args()
    stop = threading.Event()
    try:
        run_voice(print_json, stop, {"source": "typed"})
    except KeyboardInterrupt:
        pass
    except VoiceError as error:
        stderr_feedback(str(error))
        return 1
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
