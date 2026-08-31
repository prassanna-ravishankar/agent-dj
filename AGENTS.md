# Agent DJ operating contract

This repository controls a live music system. The highest-priority runtime invariant is:

> Music must not stop.

Before a musical decision, inspect `dj state --json` and future coverage. Extend unsafe coverage
before creative changes. Never put Python, an LLM, network I/O, file reads, or dependency
installation in the real-time audio callback.

During a live session, use only certified CLI operations. Do not edit runtime code, install
packages, rebuild binaries, restart the audio runtime, or delete active audio assets. A missing
agent or analyser must not stop audio. Prefer continuing a safe deck over an unnecessary change.

All meaningful commands must support machine-readable output and append operational events.
Record concise decisions, never private reasoning traces.

