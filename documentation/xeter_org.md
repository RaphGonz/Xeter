# Xeter — Company Organization
B2B SaaS · Solo founder · Paperclip-based autonomous structure  
Version 0.1 — Draft

---

## Structure overview

You operate as the board. All agents report to the COO. The COO reports to you.  
You intervene only for: pricing decisions, build decisions, critical escalations, and the weekly digest.

---

## Roles

---

### You (Board)

**Reports to:** nobody  
**Receives from:** COO (weekly digest), Customer Success (call list), Finance (anomaly alerts), Product (top 3 weekly)

Responsibilities:
- Approve or reject pricing changes proposed by Finance
- Decide what to build from Product's weekly top 3
- Handle all sales conversations and demos
- Call customers flagged by Customer Success
- Override or terminate any agent at any time

Tools: none — you are the human in the loop.

---

### COO

**Reports to:** You  
**Receives from:** all agents  
**Signals to:** You

Responsibilities:
- Orchestrates all agents, routes tickets to the right agent
- Produces a weekly digest summarizing activity across all domains: growth experiment results, CS ticket volume, top backlog items, financial health, prospect pipeline
- Escalates anything that no agent can resolve autonomously
- Maintains `program.md` files for each agent (operational documentation)

Heartbeat: weekly digest every Monday morning. Event-driven escalation at any time.

Tools: internal Paperclip orchestration, Gmail (digest delivery)

---

### Growth

**Reports to:** COO  
**Signals to:** Finance (purchase event + variant context), Product (conversion gap)

Responsibilities:
- Tracks the one primary metric: downloads + purchases per week via Posthog
- Runs A/B experiments on the landing page — one change at a time (copy, pricing display, CTA, layout)
- Deploys variants, splits traffic 50/50, measures for 7 days, picks winner
- Logs all experiments with hypothesis, variant, result, and decision
- Monitors SEO signals and suggests content adjustments
- On experiment conclusion: fires purchase event with variant context to Finance, fires conversion gap (clicked but did not buy) to Product

Heartbeat: daily check of the primary metric. Weekly experiment cycle.

Tools: Posthog (analytics, A/B flags), Loops or Brevo (email campaigns), web search (SEO monitoring, competitor tracking)

---

### SDR (Sales Development Representative)

**Reports to:** COO  
**Signals to:** You (prospect dossiers)

Responsibilities:
- Identifies companies that fit Xeter's ICP: startups or scale-ups building AI agents, Python-heavy stacks, actively hiring ML engineers, publishing content about agent reliability
- Builds a one-page dossier per prospect: company name, size, what they build, why they fit Xeter, who to contact (engineering lead or CTO), contact info, suggested tailored opening line
- Maintains a prospect list with status: not contacted / contacted / replied / demo booked / closed / not interested
- Never contacts anyone directly — hands all dossiers to you
- Produces 5–10 new prospects per week

Heartbeat: weekly, delivers prospect list every Monday alongside the COO digest.

Tools: web search, LinkedIn (public data), Apollo or Clay (prospecting data), Hunter.io (contact finding)

---

### CS (Customer Support — inbound)

**Reports to:** COO  
**Signals to:** Product (structured bug issues), Customer Success (ticket history per customer)

Responsibilities:
- Handles all inbound support emails
- Runs a clarification dialogue with the user before filing anything: asks targeted questions to collect reproduction steps, environment details, expected vs actual behavior
- Escalates to you only if severity is critical or if the dialogue stalls after N attempts
- On resolution: files a structured issue to Product with failure type (mapped to A–H taxonomy), frequency tag, and reproduction steps
- Logs all interactions per customer and shares digest with Customer Success weekly

Heartbeat: event-driven, fires on every inbound email.

Tools: Gmail (inbound), web search (known issues lookup)

---

### Customer Success (outbound relationships)

**Reports to:** COO  
**Signals to:** You (weekly call list)  
**Receives from:** Finance (payment signals), CS (ticket history)

Responsibilities:
- Owns the relationship layer for all existing customers
- Manages onboarding sequence for new customers: automated email drip at day 1, day 7, day 30 — checks they are getting value, offers help
- Computes a weekly health score per customer based on:
  - Payment history (40%) — on time, late, overdue, failed; weighted by recency
  - Product usage frequency (30%) — spans sent per week vs. first-month baseline; flags >30% week-over-week drop
  - Support ticket volume (20%) — directional: high tickets + high usage = friction but engaged; zero tickets + zero usage = silent churn risk
  - Email response rate (10%) — tiebreaker
- Produces a weekly call list for you: customer name, health score, trend (improving / stable / declining), one-sentence reason for being on the list, last interaction note
- Maintains a contact log per customer: timestamped notes you or the COO write after each call
- Does not touch billing — receives payment signals from Finance as one input only

Heartbeat: weekly health score computation and call list. Event-driven when health score drops below threshold.

Tools: Posthog or Xeter telemetry (usage data), Gmail (onboarding drip), contact log (internal Paperclip notes)

---

### Product

**Reports to:** COO  
**Signals to:** You (weekly top 3)  
**Receives from:** CS (structured bug issues), Growth (conversion gap), Customer Success (indirect via COO)

Responsibilities:
- Maintains the backlog — collects and deduplicates items from all sources
- Scores each backlog item weekly using three input streams:
  - Internal: bug frequency from CS, failure type coverage gaps from the A–H taxonomy, conversion gap signals from Growth
  - External: web search for Xeter brand mentions, Reddit and HN complaints, competitor feature announcements — maps findings to the A–H taxonomy
  - Strategic: which failure types are undetected by Xeter that customers most complain about
- Produces a weekly one-page report: top 3 items ranked, score breakdown per item, raw evidence (internal + external), what was ignored and why
- Does not execute — research and prioritization only; you decide what gets built

Heartbeat: weekly report every Friday. Web search runs mid-week to allow synthesis time.

Tools: web search (brand monitoring, competitor intelligence, community scanning), backlog tracker (GitHub Issues or Linear)

---

### Finance

**Reports to:** COO  
**Signals to:** You (anomaly alerts, pricing proposals), Customer Success (payment signals), Growth (revenue impact of experiments)

Responsibilities:
- Tracks all financial metrics weekly: MRR, ARR, churn rate, payment status per customer, invoice aging
- Sends automated payment reminder emails on behalf of the company: day 3, day 7, day 14 after due date — escalates to you if still unpaid after day 14
- Maintains grandfathering logic: when a price change is approved by you, keeps a list of existing customers on old pricing with their contract type (monthly or yearly), schedules migration email at the right moment (1 month later for monthly, 1 year later for yearly), drafts the email for your approval before sending
- Runs periodic pricing analysis (monthly): web search for competitor pricing, computes revenue impact of a price increase, proposes a new price with justification — you approve or reject
- Tracks runway: cash in bank divided by monthly burn, flags when runway drops below 6 months
- Fires a purchase event to Growth (with plan and cohort context) on every new subscription
- Alerts you immediately on anomalies: MRR drop >10%, failed invoice, unexpected churn spike

Heartbeat: weekly financial report. Event-driven for payment failures and anomaly alerts. Monthly for pricing proposals.

Tools: Stripe (billing, payment status), Pennylane or equivalent (accounting), web search (competitor pricing research), Gmail (invoice reminders)

---

## Cross-agent signal map

| From | To | Signal | Trigger |
|---|---|---|---|
| Growth | Finance | Purchase event + variant context | On experiment winner confirmed |
| Growth | Product | Conversion gap (clicked, did not buy) | Weekly |
| CS | Product | Structured bug issue (A–H taxonomy) | On ticket resolution |
| CS | Customer Success | Ticket history digest per customer | Weekly |
| Finance | Customer Success | Payment signal (late, failed, overdue) | Event-driven |
| Finance | Growth | Revenue impact of experiment variant | On experiment conclusion |
| Product | You | Top 3 backlog items + evidence | Weekly Friday |
| Customer Success | You | Call list + health scores | Weekly |
| Finance | You | Anomaly alert | Event-driven |
| COO | You | Full weekly digest | Monday morning |

---

## What you never delegate

- Pricing decisions
- Build decisions (what gets developed next)
- All sales conversations and demos
- Customer phone calls
- Hiring or terminating agents
