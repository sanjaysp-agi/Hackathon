# Demo Script — Intelligent Workflow Manager (~90 seconds)

The seeded dataset reproduces the problem statement's own example, so the
dashboard literally shows the numbers from the brief. Have the backend
(`:8000`) and frontend (`:5173`) running.

## The one-liner to open with

> "Traditional QBE/LSBI reporting tells a PV manager *what happened*. This tells
> them *what's happening, why, what's likely next, and what to do* — and because
> every number is computed deterministically, every AI recommendation is
> explainable and auditable."

## Beat 1 — the control tower (what's happening) · ~20s
Open `http://localhost:5173`. Point to the landing dashboard:
- **Workflow Health gauge** — one score, Green/Amber/Red, with the component
  breakdown (so the score is explainable, not a black box).
- The four headline tiles read exactly like the brief:
  **"12 cases at HIGH risk of missing their reporting deadline"**, SLA breaches,
  **top bottleneck = Medical Review**, **3 cases stuck**.

## Beat 2 — why + workload · ~15s
- **Bottlenecks panel:** Medical Review is worst — 21 cases queued, 1.3× the
  historical wait. (AC #4)
- **Workload panel:** **Priya Nair at 125%** (red, over the 100% marker) while
  **Omar Haddad has slack at 50%**. (AC #5) — the imbalance is visible at a glance.

## Beat 3 — ask the agent (why, grounded) · ~20s
In the chat panel, click the suggested prompt **"Why is Medical Review a
bottleneck?"**
- Watch the `get_bottlenecks()` tool line appear, then the grounded answer with
  the real figures (severity, queue depth, wait vs norm). (AC #9, #6)
- Make the point: *the agent can only cite numbers the engine returned — it
  cannot hallucinate a metric.*

## Beat 4 — next best action + drill-down · ~20s
- On the dashboard's **Recommended Actions**, find the **reassign** card:
  *"Priya Nair is at 125% capacity; Omar Haddad has slack (50%)."* (AC #7)
- Click **Accept** → toast confirms it's **logged**.
- Click a HIGH-risk row in **Critical Cases** → drill into the case:
  activity timeline, reassignment history, and the **"why this case is at risk"**
  explainability panel. (AC #8, #6)

## Beat 5 — governance · ~15s
Top-nav **Audit** → show the trail: every AI chat turn (with the tools it
called) and the human decision you just made, timestamped and immutable.
> "AI recommends, a human decides, and everything is on the record — which is
> what a regulated PV decision requires." (AC #10)

## Backup / talking points
- **"Is the AI making up numbers?"** No — show a tool line in the chat; the agent
  calls typed engine tools and the system prompt forbids stating any value a tool
  didn't return.
- **"How does this handle our real data?"** The engine runs on a normalized LSMV
  model; point `ingest.py` at the real extract (same columns) and rebuild — no
  engine changes. The 9 passing unit tests pin the behavior.
- **"Predictive?"** Regulatory risk flags cases *before* they're overdue
  (remaining work vs time left); SLA risk uses historical p80 turnaround. (AC #2, #3)
