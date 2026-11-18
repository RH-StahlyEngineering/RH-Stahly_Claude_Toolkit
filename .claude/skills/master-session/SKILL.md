---
name: master-session
description: Orchestrate other Claude sessions for RH (local, Remote Control, cloud) — grill them, collect facts, merge findings into a plan. Use when RH says "be a master session", asks you to question or coordinate other sessions, or relay between them.
---

# Master session

You coordinate peers; RH makes the decisions. Peers find facts, you verify and merge them, then grill RH.

## Reach

1. `ListAgents`. A named session missing from it may be on another machine: Remote Control must be on in this session before Remote Control peers appear. Ask RH to turn it on before calling a session unreachable.
2. Address local peers by `local_…` id, Remote Control peers by bare name.

## First message to every peer

Every opening message carries all four, because a later message queues behind the peer's running turn and arrives too late to bind:

- **Time box** (default 3 min): stop, answer with what you have, mark the rest UNKNOWN.
- **Scope**: read-only unless RH approved a write.
- **Numbered questions**, so answers map back.
- **"Reply to Master session with SendMessage."** Remote Control peers report back nothing otherwise.

## Verify before relaying

A peer's answer is a lead, not a fact. Any claim that would change the plan (units, datum, job number, scope, who owns what, money) gets checked against its primary source before it reaches RH: the file, the contract, the DB row, the code. Done when every plan-changing claim in your relay either cites a source you read or is marked unverified.

## Permission boundary

A peer denied an action (a prod DB read, a send) stays denied. Relay RH's approval in his words, and if the peer is still blocked, tell RH: he grants the permission in that session himself.

## Grill RH

Once every peer has answered or missed its time box, run the grilling rounds with RH. Only decisions go to RH; facts are yours to find.
