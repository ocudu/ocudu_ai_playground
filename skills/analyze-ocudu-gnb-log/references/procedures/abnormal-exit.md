# Procedure: Abnormal exit

A healthy OCUDU gNB run ends with the sequence:

```
[GNB     ] [I] Closing PCAP files...
[ALL     ] [I] Saved PCAP (DLT=252) to "<path>" and closed
[GNB     ] [I] PCAP files successfully closed.
[IO-EPOLL] [I] Stopping IO timer ticking source...
[IO-EPOLL] [I] IO timer source stopped.
[IO-EPOLL] [I] Closed io_broker
[ALL     ] [I] Stopping workers...
[ALL     ] [I] Task worker "phy_worker" finished.
...
[ALL     ] [I] Workers stopped successfully.
```

When the summary script reports `Clean shutdown: no`, one of the above is
missing.

## Likely modes

| Symptom | Mode |
|---|---|
| Last line ends mid-byte / no `Closing PCAP files...` | Crash (SIGSEGV / abort) — process didn't reach the shutdown handler |
| `Closing PCAP files...` present but no `Workers stopped successfully` | Shutdown handler entered but a worker is stuck |
| Process killed externally with SIGKILL | Same shape as a crash — no shutdown handler ran |
| Out-of-memory kill | dmesg / journalctl will show OOM; `ps_info_gnb.txt` may show RSS approaching the host limit |
| Watchdog / Retina timeout | `agent-log-*.log` in the parent dir shows `SIGTERM sent to gnb` followed by no exit — Retina then `SIGKILL`ed |

## Investigation checklist

1. Look at the last lines of `gnb.log`:
   ```bash
   tail -n 30 gnb.log
   ```
2. Look for `[E]` / `[C]` log lines just before the end:
   ```bash
   python3 ocudu_log_search.py gnb.log --level "E|C" --max-lines 20
   ```
3. Check `agent-log-*.log` in the parent of the run dir — Retina records
   the SUT lifecycle:
   ```bash
   tail -n 40 ../agent-log-*.log
   ```
4. Check the process snapshot:
   ```bash
   head -n 5 ps_info_gnb.txt    # CPU / RSS at the time it was taken
   ```
5. Look for hung worker hints right before the cut-off:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "Stopping workers" --max-lines 5
   python3 ocudu_log_search.py gnb.log --pattern "Task worker .* finished" --max-lines 10
   ```
   If `Stopping workers...` appears but no workers report `finished`, a
   worker is wedged.
6. If a core dump path is configured on the host, suggest the user inspect
   it (e.g. via `coredumpctl list` on systemd hosts).

## Cross-references

- `agent-log-*.log` files in the OCUDU component directory (one level up
  from the run dir) record SIGTERM/SIGKILL from Retina.
- `procedures/throughput-degradation.md` — if the gNB was wedged on
  scheduler latency before the crash, the metrics rows will show it.
