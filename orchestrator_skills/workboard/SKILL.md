---
name: workboard
description: Use this skill when a task includes a shared workboard for multi-worker coordination.
---

## WORKBOARD (WORKER COORDINATION) — REQUIRED
When calling execute_subtasks, you MUST always include a `workboard` parameter.
The workboard is a markdown string shared with workers. Workers can read and edit it via
`read_workboard` and `edit_workboard(tag, content)` by filling tagged sections assigned to them.

Always create a workboard that:
1. Lists every subtask with its index and a status checkbox (e.g. `- [ ] 1 (t1): ...`)
2. Assigns a subtask ID to each worker (`t1`, `t2`, ...)
3. Includes empty tagged slots for each worker (e.g. `<t1_result></t1_result>`)
4. Provides any shared context workers might need
5. Includes a "Results" section (optional summary area for the manager)

Example workboard format:
```
# Task Board
## Subtasks
- [ ] 1 (t1): Search for X and summarize findings
- [ ] 2 (t2): Search for Y and summarize findings
## Shared Context
<any relevant context the workers should know>
## Worker Slots
### t1
<t1_status></t1_status>
<t1_result></t1_result>
### t2
<t2_status></t2_status>
<t2_result></t2_result>
## Results
(manager may summarize here)
```