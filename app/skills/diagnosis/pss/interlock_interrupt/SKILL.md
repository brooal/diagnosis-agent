---
name: pss_interlock_interrupt_diagnosis
version: 1.0.0
category: diagnosis
domain: pss
stage: event_diagnosis
description: Diagnose why PSS leaves interlocked state and enters unlocked state.
entrypoint: skill:PssInterlockInterruptDiagnosisSkill
symptoms:
  - pss_interlock_interrupt
  - interlocked_to_unlocked
  - pss_interlock
requires:
  {"time_window": ["start", "end"]}
produces:
  - evidence
  - candidate_causes
  - primary_cause
tags:
  - pss
  - interlock_interrupt
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
      "use_remote_db": {"type": "boolean"},
      "use_current_fake_data": {"type": "boolean"},
      "fake_seed": {"type": "string"},
      "fake_scenario_id": {"type": "string"}
    },
    "required": []
  }
---

# PSS Interlock Interrupt Diagnosis

Diagnose PSS interlocked -> unlocked events. By default this skill uses fake
archive rows with the same `channel` and `sample_raw` fields as the real PV
database. Set `use_remote_db=true` to query archived PV data. The skill treats
`sysStatus_Eunlocked:bi` as an auxiliary state only; it is not used as the root
cause unless an explicit emergency unlock command PV is present.

For local/demo current-state questions, set `use_current_fake_data=true`. The
tool will use the current Shanghai time, randomly select one of the fake PSS
scenarios, and build a current interlocked -> unlocked transition around that
time. Use `fake_scenario_id` or `fake_seed` only for reproducible tests.
