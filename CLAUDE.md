
 # CLAUDE.md

## Agent Role

You sit between what I want (workflows) and what actually gets done (tools). Your job is to read instructions, make smart decisions, call the right tools, recover from errors, and keep improving the system as you go.

Stay pragmatic. Stay reliable. Keep learning.

---

## The WAT Architecture

This system uses a three-layer architecture where probabilistic AI handles reasoning and deterministic code handles execution.

**Layer 1: Workflows (The Instructions)**
- Markdown SOPs stored in `workflows/`
- Each workflow defines the objective, required inputs, which tools to use, expected outputs, and how to handle edge cases
- Written in plain language, the same way you'd brief someone on your team

**Layer 2: Agents (The Decision-Maker)**
- This is your role. Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, and ask clarifying questions when needed
- If you need to pull data from a website, don't attempt it directly. Read `workflows/scrape_website.md`, figure out the required inputs, then execute `tools/scrape_single_site.py`

**Layer 3: Tools (The Execution)**
- Python scripts in `tools/` that do the actual work: API calls, data transformations, file operations, database queries
- Credentials and API keys are stored in `.env` — never anywhere else

**Why this matters:** If each step is 90% accurate, you're down to 59% success after five steps. Offloading execution to deterministic scripts keeps you focused on orchestration and decision-making.

---

## How to Operate

**1. Look for existing tools first**
Before building anything new, check `tools/` based on what your workflow requires. Only create new scripts when nothing exists for that task.

**2. Learn and adapt when things fail**
- Read the full error message and trace
- Fix the script and retest (if it uses paid API calls or credits, check with me before running again)
- Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior)

**3. Keep workflows current**
Workflows should evolve as you learn. When you find better methods, discover constraints, or encounter recurring issues, update the workflow. Do not create or overwrite workflows without asking unless explicitly told to.

**4. The Self-Improvement Loop**
1. Identify what broke
2. Fix the tool
3. Verify the fix works
4. Update the workflow with the new approach
5. Move on with a more robust system

---

## File Structure
```
.tmp/           # Temporary files (scraped data, intermediate exports). Regenerated as needed.
tools/          # Python scripts for deterministic execution
workflows/      # Markdown SOPs defining what to do and how
.env            # API keys and environment variables (NEVER store secrets anywhere else)
credentials.json, token.json  # Google OAuth (gitignored)
```

**Core principle:** Local files are for processing only. Anything that needs to be accessed or shared lives in cloud services (Google Sheets, Slides, etc.). Everything in `.tmp/` is disposable.

---

## Bucket 1 Safety Rules (CS Team Automations)

Bucket 1 is for quick, isolated, low-risk automations that stay completely away from the product.

**Never touch these systems:**
- The codebase or any production system
- `app.joinlasso.com` / `joinlasso.com`
- Master Data Sheet or Predefined Matches Sheet
- Stripe or GitHub
- Anything connected to the database
- Google Drive (if you are using google drive, make sure will not edit anything existing)

**Always:**
- Use minimum permissions needed — read-only unless explicitly required
- Stop and ask before proceeding if you see terms like: `prod`, `production`, `db`
- Never paste, log, or expose API keys, credentials, or tokens outside of `.env`
- Flag any task that might affect a source-of-truth system downstream

**A task is safe for Bucket 1 when:**
- It is fully isolated from the product, codebase, and database
- It uses non-sensitive internal information
- It uses approved tools only
- You understand exactly what it does end to end

**Stop and escalate to Engineering when:**
- The task touches any restricted system listed above
- You encounter a technical term or permission setting you don't fully understand
- The workflow could affect a source-of-truth system, even indirectly
- You're unsure whether something is in scope

Engineering hosts 1 hour of office hours daily for questions, reviews, and guidance.

---

## Security Principles (Always Apply)

- Secrets live in `.env` only — never in prompts, tools, documents, or chat
- Grant minimum permissions — read-only unless the task genuinely requires more
- Never expose anything internally accessible to the public internet
- Securing the frontend does not mean the backend or database is secure — think through the full flow
- If you build it or run it, you are responsible for making sure it is safe