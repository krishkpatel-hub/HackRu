# Physical acceptance log

Cursor-fixed baseline: merge `2e18ae8cfd93bfd8a7fe321caed0f9473ccb09d2`, incorporating H implementation `b6d3d56` and report `d3ced04`. Package remains 0.5.0, minimum Blender 5.2. Use Blender 5.2.2 for this rehearsal. 71 Python tests + 78 subtests passed after integration. ZIP contains the eight runtime modules plus exact shared validator; no Blender runtime code changed in this baseline.

H's report concerns add-on 0.5.0 at 8eda4fe on Blender 5.2.2, followed by the hands cursor fix: five post-fix drags started/released without interruption. It does not establish two Undo steps or the remaining tools. One transform-check segfault on Blender **5.1.1**, below the declared minimum, followed two Undo commands; two reruns passed. No crash fix is claimed.

Local user-confirmed devices: camera 0; microphone 0, MacBook Air Microphone. Reconfirm after device changes. Baseline launch (key entered privately in this Terminal):

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device 0 --push-to-talk
```

Before a physical run record the actual companion SHA, installed add-on source/version, Blender version and launch command. Install the rebuilt ZIP and restart Blender if cached/outdated. Verify runtime source/version against package before accepting results. Keep demo.blend/demo.blend1 and existing scenes untouched. Wait for Blender READY and Scribe ready; /talk → one phrase → /end → committed result.

All rows below are **NOT RUN locally** unless an actual observation is entered. Automated or teammate reports are separate evidence.

| Check | Expected | Actual / status |
| --- | --- | --- |
| Installed runtime identity | Blender 5.2.2, package/version match | NOT RUN |
| Hover / pinch MOVE release | Hover no geometry mutation; no aim jump | NOT RUN |
| Two MOVE edits, two Undo | Each Undo restores one prior position | NOT RUN |
| ROTATE X/Y/Z | World axes, fixed object origin | NOT RUN |
| SCALE up/down | Positive uniform factor, fixed origin | NOT RUN |
| Cube / prism EXTRUDE | Correct face outline, closed mesh, repeat cap | NOT RUN |
| Single-hand mode completion | Returns to MOVE | NOT RUN |
| Escape and typed cancel | Exact baseline restored; release to rearm | NOT RUN |
| Short / sustained loss | Freeze immediately; cancel once at 0.5 s; release gate | NOT RUN |
| Disconnect/reconnect | Restore preview; no queued replay, fresh session | NOT RUN |
| Open another file | Previous connection/timer/preview cleaned up | NOT RUN |
| PTT / muted speech / typed fallback | One committed action; muted speech no action; typed works | NOT RUN |
| Shutdown / reopen | No workers; camera light off; camera reopens | NOT RUN |
| Two-hand identity and selectors | Correct roles; stable modes; no gesture transfer | NOT RUN |
| Numeric commands / sidebar | Relative bounded edits; one Undo each; sliders do not edit | NOT RUN |
| Fixed-distance face pinch | Exact armed amount; cancel restores; one Undo | NOT RUN |

## Enhancement rehearsal context (pending)

Planned package: 0.6.0 on Blender 5.2.2; final companion SHA is reported with delivery. No physical row above has a tested revision yet: all remain NOT RUN locally. Use the [enhancement handoff](enhancement_handoff.md) for runtime byte-match verification and exact single-/two-hand launch commands. Add actual commit/version/command and observations to each row when performed; do not infer a PASS from these automated runs.

The first requested user action is to report Help → About Blender and Preferences → Air Modeler versions. While awaiting that observation, engineering and isolated native checks continued. Do not install a new ZIP into the running user's scene without following the restart/update procedure.
