# Synthetic event samples

These event files are controlled examples for local defensive testing, not captures
of real incidents. Every record is marked as simulated, and all addresses come from
private or documentation-only ranges.

The table shows the routes and detector results expected by the bundled scenarios:

| File | Expected route | Expected rules |
| --- | --- | --- |
| `benign-web.jsonl` | `STREAM` | None |
| `port-scan.jsonl` | `FULL` | `NET-PORT-SCAN` |
| `http-brute-force.jsonl` | `FULL` | `HTTP-AUTH-FAILURES` |
| `syn-flood.jsonl` | `FULL` | `TCP-SYN-BURST` |
| `web-exploitation.jsonl` | `FULL` | Log4Shell, path traversal, and command injection |
| `network-events.jsonl` | `FULL` | Combined port scan and web exploitation |

For example, replay the port-scan sample with:

```bash
uv run --extra knowledge-graph vera analyze "Analyze this controlled replay" \
  --events src/vera/data/samples/port-scan.jsonl --simulated --offline
```

Pass events through `--events` or the API's structured event field. Pasting their
text into a question does not invoke the detectors. The `--offline` flag disables
live source lookups, not calls to a configured local model.
