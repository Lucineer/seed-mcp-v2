# ORACLE1 Integration Guide — Seed MCP v2

> How to use Seed-2.0-Mini effectively from the fleet's cloud brain.

## Connection

```
MCP Server: http://localhost:9438/mcp
OpenAI-compatible: http://localhost:9438/v1/chat/completions
```

If running on a different node, adjust the host accordingly.

## When to Use Seed-2.0-Mini

**ALWAYS use it for:**
- Any task that says "brainstorm", "ideate", "generate options"
- Naming things (agents, projects, features)
- "What if" exploration
- Getting multiple stakeholder perspectives
- First stage of any creative chain

**NEVER use it for:**
- Math, coding, factual QA
- Picking the best option (use Hermes-3-405B)
- Final polish (use Seed-2.0-Pro or Qwen3.5)

## The Chain Pattern

This is the key insight. Seed-2.0-Mini is a **breadth generator**, not a decision-maker.

```
Stage 1: Seed-2.0-Mini (temp 0.85-1.0) → Generate 5-10 options
Stage 2: Hermes-3-405B (temp 0.5)       → Pick the best 2-3
Stage 3: Seed-2.0-Pro (temp 0.85)       → Polish the winner
```

### Example: Building a new feature

```json
// Step 1: Breadth
{"method": "tools/call", "params": {"name": "brainstorm",
  "arguments": {"problem": "How should we handle offline mode for fleet agents?",
                "count": 7, "domain": "distributed systems"}}}

// Step 2: Evaluate (pick best)
{"method": "tools/call", "params": {"name": "evaluate",
  "arguments": {"options": ["<from step 1>"],
                "criteria": ["reliability", "implementation complexity", "user experience"]}}}

// Step 3: Deep dive on winner
{"method": "tools/call", "params": {"name": "deep_dive",
  "arguments": {"idea": "<winner from step 2>",
                "aspects": ["technical", "risks", "next_steps"]}}}
```

### Example: One-shot creative burst

```json
{"method": "tools/call", "params": {"name": "rapid_prototype",
  "arguments": {"problem": "Design an onboarding flow for new fleet agents",
                "iterations": 5}}}
```

This runs 5 Seed-2.0-Mini calls + 2 Hermes calls for ~$0.001.

## Temperature Cheat Sheet

| Temp | Use For |
|------|---------|
| 0.3 | Convergence — picking from a list (unusual for this model) |
| 0.5 | Focused — reverse engineering, analysis |
| 0.7 | Balanced — when you need some structure |
| 0.85 | **Default** — all ideation tasks |
| 0.9 | High divergence — wild ideas, diverge stage |
| 1.0 | Maximum — naming, breaking all constraints |

## Cost Management

The `cost_calculator` tool lets you estimate before running:

```json
{"method": "tools/call", "params": {"name": "cost_calculator",
  "arguments": {"models_used": ["Seed-2.0-mini", "Hermes-3-405B"],
                "estimated_tokens": 5000}}}
```

## The Playbook

`GET /playbook` contains all Seed-2.0-Mini wisdom. Read it. It's the IP.

Key rules:
1. **NEVER ask for one answer** — always 3-5
2. **Temp 0.85 is the sweet spot**
3. **Use it first, not last**
4. **It diverges, Hermes converges**

## Quick Tool Reference

Need inspiration? → `brainstorm`
Need the BEST option? → `diverge_converge`
Need multiple perspectives? → `chain_storm` or `perspective_shift`
Need to test assumptions? → `what_if`
Need to reframe something? → `creative_rewrite`
Need a name? → `name_storm`
Need to understand why something works? → `reverse_engineer`
Need to pick from options? → `evaluate`
Need to flesh out an idea? → `deep_dive`
Need fiction/worldbuilding? → `creative_writing`
Need the nuclear option? → `rapid_prototype`
Need to compare models? → `model_compare`
