---
name: pss_emergency_unlock_diagnosis
version: 1.0.0
category: diagnosis
domain: pss
stage: event_diagnosis
description: Diagnose PSS EmergencyUnlocked events from provided event records and context events.
entrypoint: skill:PssEmergencyUnlockDiagnosisSkill
symptoms:
  - pss_emergency_unlock
  - emergency_unlock
  - pss_interlock
requires:
  {"event": ["pv", "value", "time"]}
produces:
  - evidence
  - candidate_causes
  - primary_cause
tags:
  - pss
  - emergency_unlock
  - interlock
parameters:
  {
    "type": "object",
    "properties": {
      "event": {"type": "object"},
      "context_events": {"type": "array"},
      "start": {"type": "string"},
      "end": {"type": "string"},
      "prefix": {"type": "string"},
      "seconds_before": {"type": "integer"},
      "seconds_after": {"type": "integer"},
      "use_demo_data": {"type": "boolean"}
    },
    "required": []
  }
---

# PSS Emergency Unlock Diagnosis

Diagnose PSS EmergencyUnlocked events using provided event records. This first version does not query a database.
