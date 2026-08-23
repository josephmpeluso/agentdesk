# Vertical 2 — Connected device fleet triage

## Why a second vertical exists

One working pipeline is a demo. The claim worth making is that the
*orchestration core* is the reusable asset — that the gates, contracts, retry
budget, and eval harness survive a change of domain, and only the field names
move.

This vertical tests that claim against a domain with real stakes: connectivity
troubleshooting for a fleet of connected medical device accessories across
cellular, Bluetooth, and dashboard platforms. Same three roles. Same five
gates. Different consequences for getting it wrong, which is exactly why it is
the better test.

## The role mapping

| Outreach | Fleet triage | Unchanged |
|---|---|---|
| researcher | **diagnostician** | read-only, one source per claim, halts on thin evidence |
| drafter | **resolution author** | no tool access, works only from the diagnostic packet |
| qa-reviewer | **safety reviewer** | different model, no editing, blocks below 8 |

## Contract changes

`research_brief` → `diagnostic_packet`

```
company            → device_id
resolved_domain    → firmware_version + connectivity_path (cellular|ble|gateway)
what_they_sell     → observed_symptom
recent_news        → last_known_good      (when did it last check in, and from where)
marketing_task     → probable_cause       (with the evidence class that supports it)
claims[].source_url → claims[].evidence_ref
                      a log line ID, a KB article ID, or a telemetry query —
                      not a URL, but the same rule: it must resolve, and
                      a remembered log line is a fabrication
gaps[]             → unknowns[]           (what telemetry was unavailable)
```

`draft_package` → `resolution_package`

```
email              → customer_message     (plain language, no jargon, no blame)
account_brief      → internal_ticket_note (technical, for the next engineer)
claim_refs         → evidence_refs        (identical mechanism, identical purpose)
draftable: false   → resolvable: false    (escalate to field service)
```

`qa_verdict` keeps its shape entirely. The flag taxonomy gains one entry and
loses none:

```
+ clinical_impact   blocking — the resolution touches device availability
                    in a way that needs a named human to sign off
```

## What the swap test becomes

In outreach, the swap test catches templates. Here it catches something worse:
**a resolution that would be sent for any device with this symptom, regardless
of what the telemetry actually showed.**

Redact the device ID, firmware version, and connectivity path. If the customer
message still reads as a complete answer, the diagnostician's findings weren't
used — the resolution author pattern-matched the symptom to a generic
remediation. In outreach that wastes an email. Here it sends a customer a
power-cycle instruction for a device with a failing modem, and the device is
offline for another week.

Same test. Same three lines of reviewer instruction. Much larger blast radius.

## What changes in the gates

**Gate 2b (provenance) gets stricter.** A URL either resolves or doesn't. An
`evidence_ref` must resolve *and* fall inside the incident window — a log line
from three weeks ago is real and irrelevant, and irrelevant-but-real is the
harder failure. The check becomes: does this reference exist, and is its
timestamp within the fault window?

**Gate 3 gains a jargon check.** The customer message is scanned for internal
terminology — RSSI, PDP context, MTU, GATT, provisioning state. These are
correct and unusable. Deterministic, cheap, exactly the kind of thing that
should never be a judgment call.

**Gate 5 gains a hard ceiling.** Any resolution flagged `clinical_impact`
cannot be released by score. It routes to a named human regardless of a 10/10
verdict. Some decisions do not get delegated at any confidence level, and the
architecture should make that structural rather than procedural — a rule in a
runbook is a rule someone skips at 2am.

**The retry budget shortens to 1.** In outreach, a second revision costs
pennies and a slightly stale send. Here it costs time on an offline device.
One revision, then a human, and the flags tell them where the model got stuck.

## What stays exactly the same

- All five gates, in the same order, with the same semantics
- The orchestrator loop in `orchestrator/run.py` — the pipeline function is
  domain-agnostic; only the schema paths and check functions are injected
- The eval harness: the same mutation-based golden set, the same recall and
  false-block reporting, the same code-vs-model split
- The `halted` outcome as a first-class success. "I could not determine the
  cause from available telemetry" is the correct output more often here than
  in outreach, and a triage system that always produces a confident answer is
  worse than no triage system.

## Why this is the more honest demo

The outreach pipeline has a forgiving failure mode: a bad email gets ignored.
Triage does not. Building the same architecture twice, where the second one
has real consequences, is the difference between "I can prompt three agents"
and "I can decide where a model is allowed to be wrong."

That second sentence is the actual job.

## Status

Contract mapping and gate modifications are specified above. The
implementation reuses `orchestrator/run.py` with injected schemas and check
functions; it is not built in this repo. Documented rather than shipped —
listing it as complete would be the exact kind of unsupported claim this
system exists to block.
