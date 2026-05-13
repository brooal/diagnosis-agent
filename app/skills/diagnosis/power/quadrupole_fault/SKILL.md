---
name: quadrupole_power_diagnosis
version: 1.0.0
category: diagnosis
domain: power
stage: cause_analysis
description: Analyze quadrupole power faults around a beam fault time.
entrypoint: skill:QuadrupolePowerDiagnosisSkill
symptoms:
  - beam_trip
requires:
  {"phenomena": ["beam_trip"]}
produces:
  - evidence
  - candidate_causes
tags:
  - power
  - quadrupole
  - diagnosis
parameters:
  {
    "type": "object",
    "properties": {
      "fault_time": {"type": "string"},
      "power_pattern": {"type": "string"},
      "pv_pattern": {"type": "string"},
      "window_seconds": {"type": "integer"}
    },
    "required": []
  }
---

# Quadrupole Power Diagnosis

Use the quadrupole power diagnosis tool around a beam fault time to extract candidate devices.
