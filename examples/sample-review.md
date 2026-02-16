📋 Weekly Performance Review — Week 7

You completed 23 of 28 tasks and still managed to spend 41% of the budget on heartbeats. This is technically productivity, but with an expensive habit.

Full report attached.

📝 Performance Improvement Plan — Week 8

Based on this week's review, here are specific changes to improve next week:

1. [COST] Switch heartbeat model to a cheaper tier
   → Config change: `agents.defaults.heartbeat.model = "anthropic/claude-haiku-4-5"`

2. [EFFICIENCY] Restrict autonomous activity to waking hours
   → Config change: `agents.defaults.heartbeat.activeHours = {"start":"08:00","end":"24:00"}`

3. [RELIABILITY] Add validation before package/config edits in self-initiated runs
   → Action: require explicit risk checks before write/edit on critical files

Apply these changes? (I can update your config directly)
