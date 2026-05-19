---
name: decay_cause_analysis
version: 1.0.0
category: diagnosis
domain: beam
stage: cause_analysis
description: Explain topoff decay or constant-current interruption causes from beam state diagnosis evidence.
entrypoint: skill:DecayCauseAnalysisSkill
symptoms:
  - topoff_decay
  - beam_decay
  - mode_interrupt
requires:
  {"evidence": ["beam_state_diagnosis"]}
produces:
  - primary_cause
  - recommended_actions
tags:
  - beam
  - decay
  - topoff
  - cause
parameters:
  {
    "type": "object",
    "properties": {
      "event_id": {"type": "string"}
    },
    "required": []
  }
---

# Decay Cause Analysis

Explain decay and constant-current interruption events using root-cause candidates produced by beam state diagnosis.
