# DEMO

A script for explaining AgentDesk out loud, in an interview, without repeating
words you'd have to define if someone asked a follow-up. Each section is a
point to make, then a version of how to actually say it.

---

## 1. "Why is this three agents and not one model asked three times?"

This is the question that decides whether the interviewer thinks you built a
system or wrote a long prompt. Answer it before they ask.

**The point:** it's three separate API calls, to three different models, each
with a different set of tools turned on, and each one can fail independently
without taking the others down.

**How to say it:**

> "It's not one conversation where I ask the model to play three roles. It's
> three separate calls to the API. The researcher runs on Haiku, the drafter
> runs on Sonnet, and the reviewer runs on Opus — a different model family
> from the drafter, on purpose, which I'll come back to. Each one gets a
> different set of tools: the researcher can search the web, the drafter and
> reviewer can't touch the internet at all. And each stage can fail on its
> own — if the researcher can't find enough, the pipeline stops right there
> and nothing gets drafted. That's the difference between an agent team and
> one model wearing three hats: the hats can't fail independently, and they
> can't have different permissions."

If they push — "but couldn't one model do all three roles well enough?" — the
honest answer is yes, probably, for an easy company. The whole system exists
for the cases where "probably" isn't good enough, which is most of them once
you're not hand-picking the demo input.

---

## 2. The five gates, and the one that's a model

**The point:** there are five checkpoints between a company name and
something reaching a human, and only one of them involves a model making a
judgment call. The other four are just code.

**How to say it:**

> "There are five checkpoints. One — the prompt each agent runs under, which
> is really the contract for what it's allowed to do. Two — every agent's
> reply has to match a JSON schema exactly, or it's thrown out, no retry.
> Three — before anything reaches the reviewer, code checks word count,
> banned phrases, and whether every fact in the email actually traces back to
> something the researcher found. Four is the only one that's a model: the
> reviewer reads the draft adversarially and scores it. Five — and this is
> the part people don't expect — even the reviewer's own score doesn't
> directly decide anything. The code recomputes pass or fail from the score
> and the flags. If the model says 'pass' but the math says no, the code
> wins. A gate the model can talk its way past isn't a gate."

If they ask why only one gate is a model: because judgment doesn't scale and
code does. Anything that *can* be checked mechanically should be, so the one
expensive, adversarial model call is spent on the one thing that actually
needs judgment — not on re-verifying a word count.

---

## 3. Claim references — why "cite your sources" is mechanical here

**The point:** every factual sentence in the email carries a little tag like
`[c2]`, and that tag points at a specific fact the researcher actually found
and sourced. This turns "did the drafter make something up?" from a feeling
into a yes/no check.

**How to say it:**

> "Every sentence that states a fact about the company gets a tag — `[c2]`,
> `[c3]`, whatever — and that tag has to point at a claim the researcher
> actually sourced, with a URL it actually fetched. So checking for
> fabrication isn't 'read the email and see if it feels made up.' It's:
> pull out every tag, check it exists in the source list, check the drafter
> declared it was using that source. If a sentence makes a claim with no tag,
> or a tag that points at nothing, that's caught before a human ever sees the
> draft."

The sharper point, if there's time: this doesn't just catch missing sources —
the QA reviewer separately checks whether the tagged sentence still says what
the source actually said. A citation can be technically present and still be
a lie — restating "roughly three case studies a quarter" as "twelve case
studies a year." That's the harder failure mode, and it's why gate 4 exists
at all instead of stopping at gate 3.

---

## 4. The swap test

**The point:** the cheapest way to check if an email is actually about *this*
company, not a template with the name swapped in, is to swap the name and see
if it still reads fine.

**How to say it:**

> "Take the finished email, and mechanically replace every company-specific
> detail with a placeholder — `[COMPANY]`, `[PRODUCT]`. Then read what's
> left. If it still reads like a coherent email you could send to any
> company, you've written a template, and that's an automatic block. If it
> collapses into nonsense once the specifics are gone, that means the
> specifics were actually load-bearing — which is what you want."

This is the one check nothing but a model can do, which is exactly why it's
the reviewer's job and not code's. And the reviewer shows its work — it
writes out the redacted version so a human can look at it and agree or
disagree in about four seconds, instead of trusting the score blind.

---

## 5. Why halting counts as success

**The point:** if the researcher can't back up its findings, the system
refuses to write anything — and that refusal is a *design goal*, not a bug
that needs fixing.

**How to say it:**

> "If the research comes back thin — no real news, two companies with the
> same name and no way to tell which — the pipeline stops before it ever
> drafts anything. That's not a failure state, that's the system doing its
> job. A system that always produces an email is a system that will
> eventually invent facts about a company it couldn't actually research. I'd
> rather it say 'I don't know enough' than guess confidently."

Same logic applies to the retry budget running out: after two revisions, if
the reviewer still won't clear it, the system doesn't lower the bar to eight
on the third try — it hands it to a human with the flags attached. That's not
the system failing to finish. That's the system refusing to negotiate with
itself.

---

## 6. Walking through the escalation run — the 90-second version

This is the best thing this project has to show, and it's real: a live run
against Sonos, actual API calls, no fixtures.

**Open `web/index.html`. It loads on this run by default.**

> "This one didn't release, and that's the point. Watch the sequence: the
> researcher found six sourced claims about Sonos — real URLs, real recent
> news. The drafter wrote an email. First attempt got caught by a plain word
> count check before it even reached the reviewer — the drafter said it wrote
> 124 words, it actually wrote 129, so no review call was even spent on it.
>
> Second attempt passed the mechanical checks and went to the reviewer —
> Opus, a different model than the one that wrote it. The reviewer flagged
> something called claim drift: a sentence that cited a real fact but
> restated it as something stronger than the source actually said. Blocked.
>
> The system sent it back for one more try. Same flag came back. At that
> point the retry budget — two revisions — was used up. Instead of relaxing
> the bar to let something through, it escalated to a human queue. Nobody
> scripted that outcome. That's what the reviewer actually caught, on a real
> model, on a real company, twice in a row."

If they ask what happens next in real use: a human picks it up from the queue
with the flags already attached, and either fixes it by hand or decides the
company isn't worth pursuing. The system did its job either way — it didn't
ship something it couldn't stand behind.

**If you have another 30 seconds**, click one of the two `REJECTED` runs with
full researcher detail. Point at the flagged field directly: "this field is
437 characters, the schema caps it at 400 — that's the exact reason this run
stopped here, before anything was even drafted." It's a small, concrete
example of gate 2 working exactly as designed, on a real model output, and it
costs about a cent of Haiku to reproduce.

---

## If they ask what's *not* proven

Say it plainly — it's a better answer than pretending otherwise:

> "The live testing found real bugs and fixed them, and produced one clean
> escalation and two clean rejections with full detail. What it didn't get to
> is a live release — every released email in this repo came from a
> fixture, not a real model call — and the model side of the quality eval,
> which needs real reviewer calls I didn't have budget left for. Both are
> exactly where I'd pick this back up."
