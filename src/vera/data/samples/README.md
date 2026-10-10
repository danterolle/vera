# Synthetic event samples

All addresses use private or documentation-only ranges. Every record is explicitly marked as
simulated and is intended only for local defensive testing.

| File | Expected route | Expected rules |
| --- | --- | --- |
| `benign-web.jsonl` | `STREAM` | None |
| `port-scan.jsonl` | `FULL` | `NET-PORT-SCAN` |
| `http-brute-force.jsonl` | `FULL` | `HTTP-AUTH-FAILURES` |
| `syn-flood.jsonl` | `FULL` | `TCP-SYN-BURST` |
| `web-exploitation.jsonl` | `FULL` | Log4Shell, path traversal, and command injection |
| `network-events.jsonl` | `FULL` | Combined port scan and web exploitation |

Example:

```bash
uv run vera analyze "Analyze this controlled replay" \
  --events src/vera/data/samples/port-scan.jsonl --simulated --offline
```
