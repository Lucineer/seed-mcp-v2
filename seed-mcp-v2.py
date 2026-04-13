#!/usr/bin/env python3
"""
Seed MCP v2 — DeepInfra Creative MCP Server
=============================================
Unlocks ALL of DeepInfra's creative models with Seed-2.0-Mini as the star.
Pure Python stdlib. Zero dependencies. Port 9438.

Usage:
    DEEPINFRA_API_KEY=sk-xxx python3 seed-mcp-v2.py
    python3 seed-mcp-v2.py  # works without key (tools return config message)
"""

import json
import os
import time
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("SEED_MCP_PORT", 9438))
BASE_URL = "https://api.deepinfra.com/v1/openai"
API_KEY = os.environ.get("DEEPINFRA_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ─── Load static data ────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent

def _load(name, default):
    # Check data/ first, then repo root (for static files like playbook.json)
    for d in [DATA_DIR, REPO_DIR]:
        p = d / name
        if p.exists():
            return json.loads(p.read_text())
    return default

MODELS = _load("models.json", {}).get("models", [])
PLAYBOOK = _load("playbook.json", {})

MODEL_MAP = {m["id"]: m for m in MODELS}
MODEL_SHORT = {}
for m in MODELS:
    short = m["id"].split("/")[-1]
    MODEL_SHORT[short] = m["id"]
    MODEL_SHORT[m["name"]] = m["id"]

def resolve_model(name):
    """Resolve model name (short or full) to full DeepInfra model ID."""
    if not name:
        return "ByteDance/Seed-2.0-mini"
    if name in MODEL_MAP:
        return name
    if name in MODEL_SHORT:
        return MODEL_SHORT[name]
    return name  # pass through as-is

# ─── Call logging ─────────────────────────────────────────────────────────────
LOG_LOCK = threading.Lock()
MAX_LOG = 500

def log_call(model, tool, tokens_in, tokens_out, cost):
    entry = {
        "ts": time.time(),
        "model": model,
        "tool": tool,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost
    }
    with LOG_LOCK:
        path = DATA_DIR / "call_log.jsonl"
        lines = []
        if path.exists():
            lines = path.read_text().strip().split("\n")
        lines.append(json.dumps(entry))
        if len(lines) > MAX_LOG:
            lines = lines[-MAX_LOG:]
        path.write_text("\n".join(lines) + "\n")

# ─── DeepInfra API call ──────────────────────────────────────────────────────
def call_deepinfra(model, messages, temperature=0.85, max_tokens=2048):
    """Call DeepInfra OpenAI-compatible API. Returns dict or error string."""
    if not API_KEY:
        return {"error": "DEEPINFRA_API_KEY not configured. Set it in environment or .env file."}
    model = resolve_model(model)
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode()
    req = Request(f"{BASE_URL}/chat/completions", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            meta = MODEL_MAP.get(model, {})
            cost = (tokens_in * meta.get("cost_per_1k_tokens", 0.00003) / 1000
                    + tokens_out * meta.get("cost_per_1k_tokens", 0.00003) / 1000)
            log_call(model, "", tokens_in, tokens_out, cost)
            return data
    except HTTPError as e:
        return {"error": f"DeepInfra HTTP {e.code}: {e.read().decode()[:500]}"}
    except URLError as e:
        return {"error": f"DeepInfra connection error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}

def extract_text(result):
    """Extract assistant text from API result."""
    if "error" in result:
        return result["error"]
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return json.dumps(result)

# ─── System Prompts ──────────────────────────────────────────────────────────
SYSTEM_PROMPTS = {
    "brainstorm": (
        "You are a world-class creative strategist. Your superpower is generating DIVERSE options "
        "— not safe, similar variations, but genuinely different approaches that explore different "
        "axes of the problem space.\n\n"
        "Rules:\n"
        "- Each option must differ from the others in a MEANINGFUL way (different assumptions, "
        "different tradeoffs, different scales)\n"
        "- Include at least one \"wild card\" option that challenges conventional thinking\n"
        "- For each option: give it a memorable name, a 2-sentence description, one concrete "
        "strength, one concrete risk\n"
        "- Never default to \"do what everyone else does\" — that's not brainstorming\n\n"
        "Think in terms of: What would a startup do? What would a researcher do? "
        "What would a hacker do? What would a child ask? What would nature do?\n\n"
        "Return your answer as a JSON array of objects with keys: name, description, strength, risk."
    ),
    "diverge_converge_diverge": (
        "You are a wild creative thinker. Generate {count} genuinely different ideas for the "
        "following problem. Push boundaries. Include ideas that are unconventional, provocative, "
        "or seemingly absurd but might have hidden merit.\n\n"
        "For each idea: name, 2-sentence description, why it's interesting.\n\n"
        "Return as JSON array."
    ),
    "diverge_converge_converge": (
        "You are a rigorous evaluator. Given these ideas and criteria, pick the best 2.\n"
        "Score each idea 1-10 against each criterion. Be honest about weaknesses.\n\n"
        "Return JSON: {{\"top_2\": [{{\"name\":..., \"score\":..., \"reasoning\":...}}]}}"
    ),
    "chain_storm": (
        "You are a {angle} thinker. Approach this problem from a purely {angle} perspective.\n"
        "Generate one compelling idea that a {angle} expert would propose.\n\n"
        "Return JSON: {{\"angle\": \"{angle}\", \"idea_name\": \"...\", \"description\": \"...\", "
        "\"why_this_works\": \"...\"}}"
    ),
    "chain_storm_synthesis": (
        "You are a creative synthesizer. Given ideas from multiple perspectives, find the magic "
        "at the intersections. What themes emerge? What's the unexpected connection?\n\n"
        "Return JSON: {{\"themes\": [...], \"top_synthesis\": {{\"name\":..., \"description\":..., "
        "\"combines_angles\": [...]}}}}"
    ),
    "what_if": (
        "You are a speculative thinker. For each variable change, explore {depth} possible "
        "outcomes — each more surprising than the last. Consider cascading effects.\n\n"
        "Return JSON array of objects with: variable, scenario_name, description, "
        "implications (array of strings), likelihood (low/medium/high)."
    ),
    "creative_rewrite": (
        "You are a master of voice and tone. Rewrite the given content in {style} style.\n"
        "Capture the essence but transform the delivery completely.\n\n"
        "Return the rewritten content as plain text (not JSON)."
    ),
    "name_storm": (
        "You are a brilliant naming consultant — think Silicon Valley meets creative agency.\n"
        "Generate {count} names for: {thing} ({what_it_does}).\n\n"
        "Rules:\n"
        "- Mix approaches: portmanteaus, metaphors, Latin/Greek roots, wordplay, tech-sounding\n"
        "- At least 2 names should be playful or unexpected\n"
        "- At least 2 should feel premium/professional\n"
        "- For each: name, etymology/explanation, vibe (one word)\n\n"
        "Return JSON array of objects."
    ),
    "perspective_shift": (
        "You are analyzing from the perspective of: {stakeholder}\n\n"
        "Given this problem, answer:\n"
        "1. What does {stakeholder} care about most?\n"
        "2. What would {stakeholder} propose?\n"
        "3. What would {stakeholder} object to?\n"
        "4. What unique insight does {stakeholder} have?\n\n"
        "Return as JSON object with keys: cares_about, proposal, objections, unique_insight."
    ),
    "perspective_synthesis": (
        "You are a mediator and systems thinker. Given multiple stakeholder perspectives:\n"
        "1. Where do they align?\n"
        "2. Where do they conflict?\n"
        "3. What's the creative compromise?\n\n"
        "Return JSON: {{\"alignment\": [...], \"conflicts\": [...], \"synthesis\": \"...\"}}"
    ),
    "reverse_engineer": (
        "You are an expert at reverse-engineering success. Analyze this example and extract "
        "{what_to_extract}.\n\n"
        "For each principle:\n"
        "- Name it clearly\n"
        "- Explain why it works\n"
        "- Note how to apply it elsewhere\n"
        "- Rate transferability (high/medium/low)\n\n"
        "Return JSON array of principles."
    ),
    "evaluate": (
        "You are a rigorous evaluator. Score each option against each criterion on a 1-10 scale.\n"
        "Be specific about strengths and weaknesses. Don't be afraid to give low scores.\n\n"
        "Return JSON: {{\"rankings\": [{{\"option\": \"...\", \"scores\": {{}}, \"total\": N, "
        "\"reasoning\": \"...\"}}], \"recommendation\": \"...\"}}"
    ),
    "deep_dive": (
        "You are a strategic thinker doing a deep dive. Develop this idea across all requested "
        "aspects. Be specific, not vague. Include concrete numbers, names, steps where possible.\n\n"
        "Return JSON with keys matching each requested aspect."
    ),
    "creative_writing": (
        "You are a master creative writer in the {style} style. Write a {length} piece based on "
        "the prompt. Be vivid, immersive, and emotionally resonant.\n\n"
        "Return the creative content as plain text."
    ),
    "rapid_prototype_refine": (
        "You are a top-tier strategist. Take this raw idea and refine it into a polished, "
        "actionable proposal. Sharpen the thinking, add concrete details, address weaknesses.\n\n"
        "Return JSON: {{\"refined_name\": \"...\", \"description\": \"...\", \"key_steps\": [...], "
        "\"expected_outcome\": \"...\", \"why_it_beats_others\": \"...\"}}"
    ),
}

# ─── MCP Tool Definitions ────────────────────────────────────────────────────
MCP_TOOLS = [
    {
        "name": "brainstorm",
        "description": "Generate N diverse approaches to a problem. Uses Seed-2.0-mini at temp 0.85. Always asks for multiple options — never one.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "The problem or challenge to brainstorm"},
                "count": {"type": "integer", "description": "Number of approaches (default: 5)", "default": 5},
                "domain": {"type": "string", "description": "Optional domain context"}
            },
            "required": ["problem"]
        }
    },
    {
        "name": "diverge_converge",
        "description": "Two-stage thinking: diverge (many wild options) then converge (pick best 2). Seed-2.0-mini at temp 0.9 → 0.3.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Problem to solve"},
                "diverge_count": {"type": "integer", "description": "Options to generate (default: 7)", "default": 7},
                "criteria": {"type": "string", "description": "Evaluation criteria for convergence stage"}
            },
            "required": ["problem"]
        }
    },
    {
        "name": "chain_storm",
        "description": "Rapid parallel ideation across multiple angles. One Seed-2.0-mini call per angle, then synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Problem to ideate on"},
                "angles": {"type": "array", "items": {"type": "string"},
                    "description": "Angles (default: technical,creative,practical,radical,user-centric)",
                    "default": ["technical", "creative", "practical", "radical", "user-centric"]}
            },
            "required": ["problem"]
        }
    },
    {
        "name": "what_if",
        "description": "Generate alternative scenarios by changing variables. Seed-2.0-mini explores cascading implications.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "situation": {"type": "string", "description": "Current situation"},
                "variables": {"type": "array", "items": {"type": "string"}, "description": "Variables to change"},
                "depth": {"type": "integer", "description": "Outcomes per variable (default: 3)", "default": 3}
            },
            "required": ["situation", "variables"]
        }
    },
    {
        "name": "creative_rewrite",
        "description": "Rewrite content in different styles/voices. One Seed-2.0-mini call per style.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to rewrite"},
                "styles": {"type": "array", "items": {"type": "string"},
                    "description": "Styles (default: professional,casual,academic,storytelling)",
                    "default": ["professional", "casual", "academic", "storytelling"]}
            },
            "required": ["content"]
        }
    },
    {
        "name": "name_storm",
        "description": "Generate creative names with etymology. Seed-2.0-mini at temp 1.0 for maximum creativity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thing": {"type": "string", "description": "What to name"},
                "what_it_does": {"type": "string", "description": "What it does"},
                "count": {"type": "integer", "description": "Number of names (default: 10)", "default": 10},
                "style": {"type": "string", "description": "Optional style guidance"}
            },
            "required": ["thing", "what_it_does"]
        }
    },
    {
        "name": "perspective_shift",
        "description": "Analyze a problem from multiple stakeholder viewpoints. Each gets a dedicated Seed-2.0-mini call, then synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Problem to analyze"},
                "stakeholders": {"type": "array", "items": {"type": "string"}, "description": "Stakeholder perspectives"}
            },
            "required": ["problem", "stakeholders"]
        }
    },
    {
        "name": "reverse_engineer",
        "description": "Deconstruct why something works and extract reusable principles. Seed-2.0-mini at temp 0.7.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "example": {"type": "string", "description": "Example to analyze"},
                "what_to_extract": {"type": "string", "description": "What to extract (default: general principles)",
                    "default": "general principles"}
            },
            "required": ["example"]
        }
    },
    {
        "name": "evaluate",
        "description": "Evaluate ideas/options against criteria. Uses Hermes-3-405B for structured scoring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "options": {"type": "array", "items": {"type": "string"}, "description": "Options to evaluate"},
                "criteria": {"type": "array", "items": {"type": "string"}, "description": "Evaluation criteria"}
            },
            "required": ["options", "criteria"]
        }
    },
    {
        "name": "deep_dive",
        "description": "Take a seed idea and develop it fully. Uses Seed-2.0-pro for premium development.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "idea": {"type": "string", "description": "Seed idea to develop"},
                "aspects": {"type": "array", "items": {"type": "string"},
                    "description": "Aspects to explore (default: technical,market,risks,next_steps)",
                    "default": ["technical", "market", "risks", "next_steps"]}
            },
            "required": ["idea"]
        }
    },
    {
        "name": "creative_writing",
        "description": "Long-form creative content using Euryale-v2.3. Fiction, worldbuilding, immersive prose.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Writing prompt"},
                "style": {"type": "string", "description": "Writing style"},
                "length": {"type": "string", "description": "Length: short, medium, or long", "enum": ["short", "medium", "long"]}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "rapid_prototype",
        "description": "Breadth-first exploration: multiple Seed-2.0-mini calls at varying temps, then Hermes-3-405B cherry-picks and refines.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Problem to solve"},
                "iterations": {"type": "integer", "description": "Number of ideation passes (default: 10)", "default": 10},
                "refine_with": {"type": "string", "description": "Model for refinement (default: Hermes-3-405B)",
                    "default": "Hermes-3-405B"}
            },
            "required": ["problem"]
        }
    },
    {
        "name": "model_compare",
        "description": "Run the same prompt across multiple models and compare outputs side-by-side.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt to send to each model"},
                "models": {"type": "array", "items": {"type": "string"},
                    "description": "Models to compare (default: Seed-2.0-mini, Hermes-3-70B, MythoMax-L2-13b)",
                    "default": ["Seed-2.0-mini", "Hermes-3-70B", "MythoMax-L2-13b"]}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "cost_calculator",
        "description": "Estimate cost for a creative workflow across models.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "models_used": {"type": "array", "items": {"type": "string"}, "description": "Models used"},
                "estimated_tokens": {"type": "integer", "description": "Estimated total tokens"}
            },
            "required": ["models_used", "estimated_tokens"]
        }
    },
    {
        "name": "model_guide",
        "description": "Get model recommendations for a creative task based on requirements.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {"type": "string", "description": "Type of creative task"},
                "budget_conscious": {"type": "boolean", "description": "Prioritize cost efficiency"},
                "quality_requirement": {"type": "string", "description": "draft, good, or excellent",
                    "enum": ["draft", "good", "excellent"]}
            },
            "required": ["task_type"]
        }
    },
]

# ─── Tool Implementations ────────────────────────────────────────────────────

def tool_brainstorm(args):
    problem = args["problem"]
    count = args.get("count", 5)
    domain = args.get("domain", "")
    prompt = f"Generate {count} diverse approaches to: {problem}"
    if domain:
        prompt += f"\nDomain context: {domain}"
    result = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": SYSTEM_PROMPTS["brainstorm"]},
         {"role": "user", "content": prompt}], temperature=0.85)
    return {"approaches": extract_text(result)}

def tool_diverge_converge(args):
    problem = args["problem"]
    count = args.get("diverge_count", 7)
    criteria = args.get("criteria", "impact, feasibility, novelty")
    # Stage 1: diverge
    sys_prompt = SYSTEM_PROMPTS["diverge_converge_diverge"].format(count=count)
    result = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": f"Problem: {problem}"}], temperature=0.9)
    ideas = extract_text(result)
    # Stage 2: converge
    sys_prompt2 = SYSTEM_PROMPTS["diverge_converge_converge"]
    result2 = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": sys_prompt2},
         {"role": "user", "content": f"Ideas:\n{ideas}\n\nCriteria: {criteria}"}], temperature=0.3)
    return {"stage1_ideas": ideas, "top_2": extract_text(result2)}

def tool_chain_storm(args):
    problem = args["problem"]
    angles = args.get("angles", ["technical", "creative", "practical", "radical", "user-centric"])
    results = []
    for angle in angles:
        sys_prompt = SYSTEM_PROMPTS["chain_storm"].format(angle=angle)
        result = call_deepinfra("ByteDance/Seed-2.0-mini",
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": f"Problem: {problem}"}], temperature=0.85)
        results.append({"angle": angle, "idea": extract_text(result)})
    # Synthesis
    all_ideas = "\n".join(f"[{r['angle']}]: {r['idea']}" for r in results)
    synth = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": SYSTEM_PROMPTS["chain_storm_synthesis"]},
         {"role": "user", "content": f"Problem: {problem}\n\nIdeas:\n{all_ideas}"}], temperature=0.85)
    return {"per_angle": results, "synthesis": extract_text(synth)}

def tool_what_if(args):
    situation = args["situation"]
    variables = args["variables"]
    depth = args.get("depth", 3)
    sys_prompt = SYSTEM_PROMPTS["what_if"].format(depth=depth)
    prompt = f"Situation: {situation}\nVariables to explore: {', '.join(variables)}"
    result = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": prompt}], temperature=0.85)
    return {"scenarios": extract_text(result)}

def tool_creative_rewrite(args):
    content = args["content"]
    styles = args.get("styles", ["professional", "casual", "academic", "storytelling"])
    rewrites = {}
    for style in styles:
        sys_prompt = SYSTEM_PROMPTS["creative_rewrite"].format(style=style)
        result = call_deepinfra("ByteDance/Seed-2.0-mini",
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": content}], temperature=0.85)
        rewrites[style] = extract_text(result)
    return {"rewrites": rewrites}

def tool_name_storm(args):
    thing = args["thing"]
    what_it_does = args["what_it_does"]
    count = args.get("count", 10)
    style = args.get("style", "")
    sys_prompt = SYSTEM_PROMPTS["name_storm"].format(thing=thing, what_it_does=what_it_does, count=count)
    prompt = f"Name this: {thing} — {what_it_does}"
    if style:
        prompt += f"\nStyle preference: {style}"
    result = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": prompt}], temperature=1.0)
    return {"names": extract_text(result)}

def tool_perspective_shift(args):
    problem = args["problem"]
    stakeholders = args["stakeholders"]
    perspectives = {}
    for s in stakeholders:
        sys_prompt = SYSTEM_PROMPTS["perspective_shift"].format(stakeholder=s)
        result = call_deepinfra("ByteDance/Seed-2.0-mini",
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": f"Problem: {problem}"}], temperature=0.85)
        perspectives[s] = extract_text(result)
    # Synthesis
    all_persp = "\n".join(f"[{k}]: {v}" for k, v in perspectives.items())
    synth = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": SYSTEM_PROMPTS["perspective_synthesis"]},
         {"role": "user", "content": f"Problem: {problem}\n\nPerspectives:\n{all_persp}"}], temperature=0.85)
    return {"perspectives": perspectives, "synthesis": extract_text(synth)}

def tool_reverse_engineer(args):
    example = args["example"]
    what = args.get("what_to_extract", "general principles")
    sys_prompt = SYSTEM_PROMPTS["reverse_engineer"].format(what_to_extract=what)
    result = call_deepinfra("ByteDance/Seed-2.0-mini",
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": f"Analyze this:\n\n{example}"}], temperature=0.7)
    return {"principles": extract_text(result)}

def tool_evaluate(args):
    options = args["options"]
    criteria = args["criteria"]
    prompt = f"Options:\n" + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
    prompt += f"\n\nCriteria: {', '.join(criteria)}"
    result = call_deepinfra("NousResearch/Hermes-3-Llama-3.1-405B",
        [{"role": "system", "content": SYSTEM_PROMPTS["evaluate"]},
         {"role": "user", "content": prompt}], temperature=0.5)
    return {"evaluation": extract_text(result)}

def tool_deep_dive(args):
    idea = args["idea"]
    aspects = args.get("aspects", ["technical", "market", "risks", "next_steps"])
    prompt = f"Idea: {idea}\n\nDevelop this across: {', '.join(aspects)}"
    result = call_deepinfra("bytedance/Seed-2.0-pro",
        [{"role": "system", "content": SYSTEM_PROMPTS["deep_dive"]},
         {"role": "user", "content": prompt}], temperature=0.85)
    return {"development": extract_text(result)}

def tool_creative_writing(args):
    prompt = args["prompt"]
    style = args.get("style", "immersive literary")
    length = args.get("length", "medium")
    length_map = {"short": "200-400 words", "medium": "500-1000 words", "long": "1500-3000 words"}
    sys_prompt = SYSTEM_PROMPTS["creative_writing"].format(style=style, length=length_map.get(length, "500-1000 words"))
    max_tokens = {"short": 1024, "medium": 2048, "long": 4096}.get(length, 2048)
    result = call_deepinfra("Sao10k/L3.3-70B-Euryale-v2.3",
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": prompt}], temperature=0.9, max_tokens=max_tokens)
    return {"content": extract_text(result)}

def tool_rapid_prototype(args):
    problem = args["problem"]
    iterations = min(args.get("iterations", 10), 10)
    refine_model = args.get("refine_with", "Hermes-3-405B")
    refine_full = resolve_model(refine_model)
    # Stage 1: breadth
    ideas = []
    for i in range(iterations):
        temp = round(0.7 + (0.3 * i / max(iterations - 1, 1)), 2)
        result = call_deepinfra("ByteDance/Seed-2.0-mini",
            [{"role": "system", "content": SYSTEM_PROMPTS["brainstorm"]},
             {"role": "user", "content": f"Approach #{i+1} for: {problem}\nMake this one unique."}],
            temperature=temp, max_tokens=512)
        ideas.append(extract_text(result))
    # Stage 2: evaluate
    all_ideas = "\n\n---\n\n".join(ideas)
    eval_prompt = f"Problem: {problem}\n\nIdeas:\n{all_ideas}\n\nPick the top 3 and explain why."
    eval_result = call_deepinfra(refine_full,
        [{"role": "system", "content": "You are an expert evaluator. Pick the 3 best ideas from the list. Be specific about why each is good."},
         {"role": "user", "content": eval_prompt}], temperature=0.5)
    top_ideas = extract_text(eval_result)
    # Stage 3: refine
    refine_result = call_deepinfra(refine_full,
        [{"role": "system", "content": SYSTEM_PROMPTS["rapid_prototype_refine"]},
         {"role": "user", "content": f"Problem: {problem}\n\nBest ideas:\n{top_ideas}\n\nRefine the #1 idea into an actionable proposal."}],
        temperature=0.5)
    return {
        "iterations": iterations,
        "raw_ideas_count": len(ideas),
        "top_picks": top_ideas,
        "refined": extract_text(refine_result),
        "cost_note": f"{iterations} Seed-2.0-mini calls + 2 {refine_model} calls. Total cost: ~${iterations * 0.00003 + 2 * 0.0003:.6f}"
    }

def tool_model_compare(args):
    prompt = args["prompt"]
    models = args.get("models", ["Seed-2.0-mini", "Hermes-3-70B", "MythoMax-L2-13b"])
    comparisons = {}
    for m in models:
        full_model = resolve_model(m)
        result = call_deepinfra(full_model,
            [{"role": "user", "content": prompt}], temperature=0.85, max_tokens=512)
        comparisons[m] = {
            "model": full_model,
            "output": extract_text(result),
            "cost_per_1k": MODEL_MAP.get(full_model, {}).get("cost_per_1k_tokens", "unknown")
        }
    return {"comparisons": comparisons}

def tool_cost_calculator(args):
    models_used = args["models_used"]
    tokens = args.get("estimated_tokens", 0)
    breakdown = []
    total = 0
    for m in models_used:
        full = resolve_model(m)
        meta = MODEL_MAP.get(full, {})
        cpm = meta.get("cost_per_1k_tokens", 0.00003)
        cost = (tokens * cpm) / 1000
        total += cost
        breakdown.append({"model": m, "full_id": full, "cost_per_1k_tokens": cpm, "estimated_cost": round(cost, 8)})
    return {"breakdown": breakdown, "total_estimated_cost": round(total, 8)}

def tool_model_guide(args):
    task = args["task_type"].lower()
    budget = args.get("budget_conscious", False)
    quality = args.get("quality_requirement", "good")
    recommendations = []
    for m in MODELS:
        if any(task in bf for bf in m.get("best_for", [])):
            score = m.get("tier", 3)
            if budget and m["tier"] == 3:
                score -= 1
            if quality == "excellent" and m["tier"] == 1:
                score += 1
            recommendations.append((score, m))
    recommendations.sort(key=lambda x: x[0])
    recs = [{"model": m["id"], "name": m["name"], "tier": m["tier"],
             "cost_per_1k": m.get("cost_per_1k_tokens"), "reason": ", ".join(m.get("best_for", [])[:3])}
            for _, m in recommendations[:5]]
    if not recs:
        recs = [{"model": "ByteDance/Seed-2.0-mini", "name": "Seed-2.0-Mini", "reason": "Good default for most creative tasks"}]
    return {"task": task, "quality": quality, "budget_conscious": budget, "recommendations": recs}

TOOL_HANDLERS = {
    "brainstorm": tool_brainstorm,
    "diverge_converge": tool_diverge_converge,
    "chain_storm": tool_chain_storm,
    "what_if": tool_what_if,
    "creative_rewrite": tool_creative_rewrite,
    "name_storm": tool_name_storm,
    "perspective_shift": tool_perspective_shift,
    "reverse_engineer": tool_reverse_engineer,
    "evaluate": tool_evaluate,
    "deep_dive": tool_deep_dive,
    "creative_writing": tool_creative_writing,
    "rapid_prototype": tool_rapid_prototype,
    "model_compare": tool_model_compare,
    "cost_calculator": tool_cost_calculator,
    "model_guide": tool_model_guide,
}

# ─── MCP Protocol Helpers ────────────────────────────────────────────────────

def mcp_response(result_id, content):
    return {
        "jsonrpc": "2.0",
        "id": result_id,
        "result": {"content": [{"type": "text", "text": json.dumps(content, indent=2)}]}
    }

def mcp_error(result_id, code, message):
    return {"jsonrpc": "2.0", "id": result_id, "error": {"code": code, "message": message}}

def mcp_tools_list(result_id):
    return mcp_response(result_id, MCP_TOOLS)

def mcp_tool_call(result_id, name, arguments):
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return mcp_error(result_id, -32601, f"Unknown tool: {name}")
    try:
        result = handler(arguments)
        return mcp_response(result_id, result)
    except Exception as e:
        return mcp_error(result_id, -32603, f"Tool error: {e}")

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class SeedMCPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default logging

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_GET(self):
        path = self.path.rstrip("/")
        if path == "/playbook":
            self._json_response(PLAYBOOK)
        elif path.startswith("/playbook/"):
            model_key = path.split("/playbook/", 1)[1]
            if model_key in PLAYBOOK:
                self._json_response({model_key: PLAYBOOK[model_key]})
            else:
                self._json_response({"error": f"No playbook for {model_key}. Available: {list(PLAYBOOK.keys())}"}, 404)
        elif path == "/mcp/tools":
            self._json_response(MCP_TOOLS)
        elif path == "/mcp/models":
            self._json_response(MODELS)
        elif path == "/health":
            self._json_response({"status": "ok", "api_configured": bool(API_KEY), "port": PORT})
        else:
            self._json_response({
                "name": "Seed MCP v2",
                "version": "2.0.0",
                "endpoints": ["/mcp/tools", "/mcp/models", "/playbook", "/v1/chat/completions", "/health"],
                "api_configured": bool(API_KEY)
            })

    def do_POST(self):
        path = self.path.rstrip("/")
        body = self._read_body()

        if path == "/mcp":
            req_id = body.get("id")
            method = body.get("method", "")
            if method == "tools/list":
                self._json_response(mcp_tools_list(req_id))
            elif method == "tools/call":
                params = body.get("params", {})
                self._json_response(mcp_tool_call(req_id, params.get("name", ""), params.get("arguments", {})))
            else:
                self._json_response(mcp_error(req_id, -32601, f"Unknown method: {method}"))

        elif path == "/v1/chat/completions":
            model = body.get("model", "ByteDance/Seed-2.0-mini")
            messages = body.get("messages", [])
            temperature = body.get("temperature", 0.85)
            max_tokens = body.get("max_tokens", 2048)
            if not messages:
                self._json_response({"error": "messages required"}, 400)
                return
            result = call_deepinfra(model, messages, temperature, max_tokens)
            self._json_response(result)
        else:
            self._json_response({"error": "Not found"}, 404)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), SeedMCPHandler)
    print(f"🌱 Seed MCP v2 running on port {PORT}")
    print(f"   API key: {'configured' if API_KEY else 'NOT SET — tools will return config message'}")
    print(f"   Endpoints: GET /playbook, /mcp/tools, /mcp/models, /health")
    print(f"              POST /mcp (MCP protocol), /v1/chat/completions")
    print(f"   {len(MCP_TOOLS)} tools, {len(MODELS)} models ready")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
