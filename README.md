# Seed MCP v2 — DeepInfra Creative Server

> The creative brain for the fleet. Seed-2.0-Mini as the star, 15 creative tools, zero dependencies.

## Quick Start

```bash
# Set your API key
export DEEPINFRA_API_KEY=sk-your-key-here

# Run it
python3 seed-mcp-v2.py

# Verify
curl http://localhost:9438/health
curl http://localhost:9438/playbook
curl http://localhost:9438/mcp/tools
```

Works without API key — tools will return a config message.

## Why Seed-2.0-Mini?

**$0.00003/1K tokens.** That's 10x cheaper than Hermes-3-405B, 30x cheaper than Qwen3.5-397B.

It's a **divergent thinker** — terrible at math, brilliant at generating options. The secret:
- **Never ask for one answer** — always 3-5
- **Temperature 0.85** is the sweet spot
- **Use it FIRST in chains**, then hand off to a convergent model

10 calls = $0.003 for breadth that costs $0.03+ with expensive models.

## The 15 Tools

### Seed-2.0-Mini Bread & Butter (80% of usage)

| Tool | What It Does | Temp |
|------|-------------|------|
| `brainstorm` | N diverse approaches to a problem | 0.85 |
| `diverge_converge` | Diverge (7 wild ideas) → converge (pick best 2) | 0.9 → 0.3 |
| `chain_storm` | Parallel ideation across 5 angles + synthesis | 0.85 |
| `what_if` | Alternative scenarios with cascading implications | 0.85 |
| `creative_rewrite` | Same content, multiple styles/voices | 0.85 |
| `name_storm` | Creative names with etymology | 1.0 |
| `perspective_shift` | Multi-stakeholder analysis + synthesis | 0.85 |
| `reverse_engineer` | Extract reusable principles from examples | 0.7 |

### Cross-Model Chain Tools (15% of usage)

| Tool | Model | Purpose |
|------|-------|---------|
| `evaluate` | Hermes-3-405B | Score options against criteria |
| `deep_dive` | Seed-2.0-Pro | Full concept development |
| `creative_writing` | Euryale-v2.3 | Fiction, worldbuilding, immersive prose |
| `rapid_prototype` | Mini + Hermes | 10 Mini calls → cherry-pick → refine |
| `model_compare` | Multiple | Same prompt, compare outputs |

### Utility Tools (5% of usage)

| Tool | Purpose |
|------|---------|
| `cost_calculator` | Estimate workflow costs |
| `model_guide` | Which model for which task |

## Endpoints

- `GET /playbook` — Seed-2.0-Mini wisdom (the IP)
- `GET /playbook/{model}` — Model-specific playbook
- `GET /mcp/tools` — All 15 tool definitions
- `GET /mcp/models` — Model registry
- `GET /health` — Server status
- `POST /mcp` — MCP protocol (tools/list, tools/call)
- `POST /v1/chat/completions` — OpenAI-compatible proxy

## Model Roster

### Tier 1 — The Star
- **ByteDance/Seed-2.0-mini** — $0.00003/1K — The Divergent Thinker

### Tier 2 — Specialists
- **bytedance/Seed-2.0-pro** — $0.00015/1K — Premium ideation
- **NousResearch/Hermes-3-Llama-3.1-405B** — $0.0003/1K — The Architect
- **NousResearch/Hermes-3-Llama-3.1-70B** — $0.00006/1K — The Storyteller
- **Sao10k/L3.3-70B-Euryale-v2.3** — $0.00006/1K — The Worldbuilder

### Tier 3 — Niche
- **Gryphe/MythoMax-L2-13b** — $0.00001/1K — The Fast Riffer
- **allenai/Olmo-3.1-32B-Instruct** — $0.00004/1K — The Scientist
- **microsoft/phi-4** — $0.00005/1K — The Edge Runner

## Architecture

Pure Python stdlib. Zero pip installs. Runs on a Jetson Orin Nano 8GB.

```
seed-mcp-v2/
├── seed-mcp-v2.py    # The server (~900 lines)
├── models.json        # Model registry
├── playbook.json      # Seed-2.0-Mini wisdom
├── data/              # Runtime data (git-synced)
│   ├── call_log.jsonl # Last 500 calls
│   └── theories.json  # Working theories
├── README.md
├── ORACLE1-GUIDE.md   # Fleet integration guide
└── .gitignore
```

## Cost Examples

| Workflow | Calls | Cost |
|----------|-------|------|
| Quick brainstorm | 1x Mini | $0.0001 |
| Full diverge_converge | 2x Mini | $0.0002 |
| chain_storm (5 angles) | 6x Mini | $0.0006 |
| rapid_prototype | 10x Mini + 2x Hermes | $0.001 |
| Full model_compare | 3x mixed | $0.0004 |

**You can run 100 brainstorm sessions for under $0.01.**
