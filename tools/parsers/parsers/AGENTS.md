# Parsers

- OCUDU log line formats: `skills/analyze-ran-log/references/ocudu/reference/log-format.md`.
- Log entry headers and timestamps: parse them with `parsers.log.preamble`, the one source for the entry start,
  header and slot patterns and the epoch conversions.
- Scheduler event traces (schedtrace) are FlatBuffers, with schemas in OCUDU's `lib/scheduler/trace/fbs`.
  `parsers.schedtrace` decodes them.
