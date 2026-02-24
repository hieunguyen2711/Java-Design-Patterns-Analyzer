from typing import Dict, List

from config import settings

class PromptService:
    """Build prompts for chunked and merged LLM interactions."""

    SYSTEM_PROMPT: str = (
        "You are a senior Java software architect and design pattern expert. "
        "Identify only one pattern truly present in the provided code. "
        "List exact class names, interfaces, and file paths. Do not hallucinate.\n"
        "Be concise, precise, and cite evidence from code snippets and paths."
    )

    def build_chunk_prompt(
        self, java_files: Dict[str, str], chunk_index: int, total_chunks: int
    ) -> str:
        """Construct a prompt for a specific chunk of Java files."""
        lines: List[str] = [self.SYSTEM_PROMPT]

        if total_chunks > 1:
            lines.append(
                f"This is chunk {chunk_index + 1} of {total_chunks}. "
                "Identify patterns observable so far."
            )
        else:
            lines.append("Analyze the full project and provide the complete report.")

        for path, content in java_files.items():
            lines.append(f"### FILE: {path}")
            lines.append(content)
            lines.append("-----")

        lines.append("Provide structured findings with pattern names and evidence.")
        return "\n".join(lines)

    def build_generate_prompt(self, pattern: str, description: str) -> str:
        """Construct a prompt to generate Java code following a specific design pattern."""
        lines: List[str] = [
            "You are a senior Java software engineer and design pattern expert.",
            "Generate clean, well-structured Java code that implements the design pattern requested by the user.",
            "Include all necessary classes and interfaces, with comments explaining each role in the pattern.",
            "Do not include explanations outside the code — use inline Javadoc comments only.",
            "",
            f"Design Pattern: {pattern}",
            f"User Description: {description}",
            "",
            "Provide the full Java implementation below:",
        ]
        return "\n".join(lines)

        """Construct a prompt to merge partial analyses into a final report."""
        lines: List[str] = [self.SYSTEM_PROMPT]
        lines.append("Merge the following partial analyses into a single cohesive report.")

        budget = settings.MAX_MERGE_CHARS
        per_analysis = max(500, budget // max(len(partial_analyses), 1))

        for idx, analysis in enumerate(partial_analyses, start=1):
            truncated = analysis[:per_analysis]
            if len(analysis) > per_analysis:
                truncated += "\n[TRUNCATED]"
            lines.append(f"### PARTIAL ANALYSIS {idx}")
            lines.append(truncated)
            lines.append("-----")

        lines.append(
            "Combine, deduplicate, and resolve conflicts. "
            "Return a clear final design pattern analysis with evidence and file paths."
        )
        return "\n".join(lines)
