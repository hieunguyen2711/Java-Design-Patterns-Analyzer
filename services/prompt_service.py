from typing import Dict, List


class PromptService:
    """Build prompts for chunked and merged LLM interactions."""

    SYSTEM_PROMPT: str = (
        "You are a senior Java software architect and design pattern expert. "
        "Identify only patterns truly present in the provided code. "
        "List exact class names, interfaces, and file paths. Do not hallucinate.\n"
        "GoF Design Patterns:\n"
        "- Creational: Singleton, Factory Method, Abstract Factory, Builder, Prototype\n"
        "- Structural: Adapter, Bridge, Composite, Decorator, Facade, Flyweight, Proxy\n"
        "- Behavioral: Chain of Responsibility, Command, Iterator, Mediator, Memento, "
        "Observer, State, Strategy, Template Method, Visitor, Interpreter\n"
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

    def build_merge_prompt(self, partial_analyses: List[str]) -> str:
        """Construct a prompt to merge partial analyses into a final report."""
        lines: List[str] = [self.SYSTEM_PROMPT]
        lines.append("Merge the following partial analyses into a single cohesive report.")

        for idx, analysis in enumerate(partial_analyses, start=1):
            lines.append(f"### PARTIAL ANALYSIS {idx}")
            lines.append(analysis)
            lines.append("-----")

        lines.append(
            "Combine, deduplicate, and resolve conflicts. "
            "Return a clear final design pattern analysis with evidence and file paths."
        )
        return "\n".join(lines)
