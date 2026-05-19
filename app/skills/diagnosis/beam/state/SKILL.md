---
name: beam_state_diagnosis
version: 1.0.0
category: diagnosis
domain: beam
stage: phenomenon_detection
description: Diagnose beam state within a time window and identify topoff decay, mode interruption, and beam trip phenomena.
entrypoint: skill:BeamStateDiagnosisSkill
symptoms:
  - beam_trip
  - beam_decay
requires:
  {"time_window": ["start", "end"]}
produces:
  - phenomena
  - evidence
  - candidate_causes
tags:
  - beam
  - state
  - diagnosis
parameters:
  {
    "type": "object",
    "properties": {
      "start": {"type": "string"},
      "end": {"type": "string"},
      "beam_channel": {"type": "string"},
      "beam_current_pv": {"type": "string"}
    },
    "required": ["start", "end"]
  }
---

# Beam State Diagnosis

Use topoff decay and beam diagnosis tools to determine whether the beam window contains topoff decay, mode interruption, or trip-like phenomena.
