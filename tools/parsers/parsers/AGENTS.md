# Parsers

- OCUDU log line formats: `skills/analyze-ran-log/references/ocudu/reference/log-format.md`.
- Scheduler event traces (schedtrace) are FlatBuffers, with schemas in OCUDU's `lib/scheduler/trace/fbs`.
  `parsers.schedtrace` decodes them.
