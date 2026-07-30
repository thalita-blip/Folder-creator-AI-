"""
Sends the raw RFA text to Google's Gemini API and gets back a structured
JSON object matching the fixed SOP section list + tracker-specific extras,
using the DBIA SOP as a one-shot worked example.

Uses Gemini (not Anthropic) so this can run on Google AI Studio's free tier
with no billing required.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
ONE_SHOT_EXAMPLE_PATH = ROOT / "templates_reference" / "dbia_sop_example.md"

MODEL = "gemini-2.5-flash"


class EvaluationCriterion(BaseModel):
    criterion: str
    points: Optional[float] = None
    notes: str


class ApplicantEligibilityQuestions(BaseModel):
    business: List[str]
    previous_funding: List[str]
    compliance: List[str]


class DocumentsToRequest(BaseModel):
    business: List[str]
    financial: List[str]
    project: List[str]
    supporting: List[str]


class SopSections(BaseModel):
    grant_purpose: str
    grant_overview: str
    reimbursement_rules: str
    eligible_projects: str
    eligible_costs: str
    ineligible_costs: str
    most_important_rules: List[str]
    applicant_eligibility_questions: ApplicantEligibilityQuestions
    project_eligibility_questions: List[str]
    evaluation_criteria: List[EvaluationCriterion]
    strengthening_questions: List[str]
    project_readiness_checklist: List[str]
    documents_to_request: DocumentsToRequest
    financing_questions: List[str]
    client_commitment_questions: List[str]
    red_flags: List[str]


class TrackerExtras(BaseModel):
    reimbursement_summary: str
    competitive_scoring_bullets: List[str]
    grant_specific_rows: List[str]


class SopSynthesis(BaseModel):
    sop_sections: SopSections
    tracker_extras: TrackerExtras


SYSTEM_PROMPT = """You are helping Lasso CS, a grant-writing consultancy, turn a raw RFA/NOFO \
document into their standard internal SOP structure.

You will be shown one fully worked example (for the DBIA Dairy Business Builder grant) \
that demonstrates the exact structure, section order, level of detail, and tone to use. \
This is a REWRITE AND SYNTHESIS task, not a section-by-section copy: the new RFA will not \
share the same headings or organization as the source NOFO, so you must read the whole \
document, understand its substance, and reorganize it into the fixed structure below. \
Where the RFA doesn't address a section (e.g. no reimbursement process because it's an \
upfront-payment grant), say so briefly rather than inventing content.

competitive_scoring_bullets should reflect the RFA's actual published scoring/evaluation \
breakdown (e.g. "Alignment and Intent — 25 pts") if one exists, otherwise a reasonable \
synthesized set of criteria in the same style as the example.

Be concise. Match the example's information density, not its exact word count — a couple \
of tight sentences per prose section, short bullet phrases (not full paragraphs) everywhere \
else. Never pad a section to sound thorough."""


def _build_user_message(rfa_text: str, one_shot_example: str) -> str:
    return (
        "Here is a fully worked example of the target structure, for a different grant "
        "(DBIA Dairy Business Builder):\n\n"
        f"{one_shot_example}\n\n"
        "---\n\n"
        "Now reorganize the following RFA into that same structure. This RFA covers a "
        "different grant program — do not carry over any DBIA-specific facts (states, "
        "dairy terminology, award amounts, etc.), only the structural pattern.\n\n"
        f"{rfa_text}"
    )


def synthesize(rfa_text: str, api_key: str | None = None) -> dict:
    """Call the Gemini API and return the parsed synthesis JSON."""
    client = genai.Client(api_key=api_key)
    one_shot_example = ONE_SHOT_EXAMPLE_PATH.read_text(encoding="utf-8")

    response = client.models.generate_content(
        model=MODEL,
        contents=_build_user_message(rfa_text, one_shot_example),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=SopSynthesis,
            max_output_tokens=6000,
        ),
    )

    if response.parsed is None:
        raise RuntimeError(f"Gemini did not return a parsed SopSynthesis object. Raw text: {response.text[:500]}")

    return response.parsed.model_dump()


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", required=True, help="Path to raw RFA text (.tmp/grant_raw.txt)")
    parser.add_argument("--out", default=str(ROOT / ".tmp" / "grant_synthesis.json"))
    args = parser.parse_args()

    rfa_text = Path(args.text_file).read_text(encoding="utf-8")
    result = synthesize(rfa_text, api_key=os.getenv("GEMINI_API_KEY"))

    out_path = Path(args.out)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved synthesis to {out_path}")


if __name__ == "__main__":
    main()
