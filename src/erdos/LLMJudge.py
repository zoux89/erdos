"""LLM Judge for analyzing proofs using Claude"""

import json
from dataclasses import dataclass
from typing import Optional

from anthropic import AsyncAnthropic


@dataclass
class JudgeFeedback:
    analysis: str
    suggestions: str
    revised_proof_hint: Optional[str] = None
    should_retry: bool = True
    confidence: float = 0.5


JUDGE_SYSTEM_PROMPT = """You are an expert mathematical proof assistant helping to debug Lean 4 proofs.

Analyze errors and provide:
1. Root cause analysis
2. Specific fixes or alternative strategies
3. A revised proof hint

Format:
## Analysis
[What went wrong]

## Suggestions
[Actionable suggestions]

## Revised Proof Hint
[New proof sketch, or "NO REVISION NEEDED"]

## Should Retry
[YES or NO]"""


class LLMJudge:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def analyze_failure(
        self,
        problem: str,
        proof_hint: Optional[str],
        generated_proof: Optional[str],
        error_output: str,
        attempt_number: int,
    ) -> JudgeFeedback:
        prompt = f"""## Problem
{problem}

## Proof Hint
{proof_hint or "None"}

## Generated Lean Proof
```lean
{generated_proof or "None"}
```

## Error Output
```
{error_output}
```

Attempt #{attempt_number}. Analyze and provide feedback."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text)

    def _parse_response(self, content: str) -> JudgeFeedback:
        sections = {"analysis": "", "suggestions": "", "revised_proof_hint": None, "should_retry": True}
        current_section = None
        current_content = []

        for line in content.splitlines():
            lower = line.lower().strip()

            if lower.startswith("## analysis"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "analysis"
                current_content = []
            elif lower.startswith("## suggestion"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "suggestions"
                current_content = []
            elif lower.startswith("## revised proof"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "revised_proof_hint"
                current_content = []
            elif lower.startswith("## should retry"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "should_retry"
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section and current_content:
            sections[current_section] = "\n".join(current_content).strip()

        should_retry = True
        if isinstance(sections["should_retry"], str):
            should_retry = "yes" in sections["should_retry"].lower()

        revised_hint = sections.get("revised_proof_hint")
        if revised_hint and "no revision" in revised_hint.lower():
            revised_hint = None

        return JudgeFeedback(
            analysis=sections.get("analysis", content),
            suggestions=sections.get("suggestions", ""),
            revised_proof_hint=revised_hint,
            should_retry=should_retry,
            confidence=0.7 if revised_hint else 0.5,
        )

    async def translate_lean_to_english(self, lean_proof: str, problem_statement: Optional[str] = None) -> str:
        context = f"Original Problem:\n{problem_statement}\n\n" if problem_statement else ""

        prompt = f"""{context}Lean 4 Proof:
```lean
{lean_proof}
```

Translate to readable English with LaTeX ($..$ inline, $$..$$ display).
Structure: Theorem Statement, Proof Strategy, Step-by-Step, Key Lemmas."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system="Translate Lean 4 proofs to readable mathematical English with LaTeX.",
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    async def verify_proof_logic(self, lean_proof: str, problem_statement: str) -> dict:
        """Check if proof is legitimate or BS (degenerate cases, vacuous, etc)."""

        prompt = f"""Problem:
{problem_statement}

Lean Proof:
```lean
{lean_proof}
```

Detect BS proofs that type-check but don't prove anything real:

1. DEGENERATE CASES - using trivial objects (point as triangle, empty set, n=0)
2. VACUOUS PROOFS - exploiting weak definitions
3. CLASSICAL.EM ABUSE - using "P ∨ ¬P" instead of proving P
4. FORMALIZATION ONLY - just definitions, no theorem with proof
5. SORRY/ADMIT - incomplete proofs
6. WRONG THEOREM - proving something different

Reply JSON:
{{"valid": bool, "confidence": 0-1, "summary": "what it does", "issues": [...], "feedback": "what to fix", "is_real_proof": bool}}

BE HARSH."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system="Ruthless proof critic. Catch BS proofs that type-check but prove nothing.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())

        if "is_real_proof" not in result:
            result["is_real_proof"] = result.get("valid", False)
        if "feedback" not in result:
            result["feedback"] = ""

        return result
