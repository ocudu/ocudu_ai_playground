# Agent notes

## Layout

- `skills/`: Claude Code skills. Tests: `python3 -m unittest discover -s tests -p "test_*.py"`.
- `tools/parsers/`: decoders of OCUDU artifacts. Standard library only. See its README.
  Tests: `python3 -m unittest discover -s tools/parsers/tests -t tools/parsers`.
- `tools/viz/`: browser visualizer built on `tools/parsers`. See its README (Usage, Development) and DESIGN.md.
  Tests: `python3 -m unittest discover -s tools/viz/tests -t tools/viz`.
