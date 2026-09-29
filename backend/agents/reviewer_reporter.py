"""Agent 5 of 5: evidence review and the final report narrative."""
from backend.agent_common import make_agent


def build_agent(llm, tools):
    return make_agent(
        "Evidence reviewer and report writer",
        "Combine supported specialist findings into a clear, cited environmental briefing.",
        "You verify previous notes against the original evidence and quality checks. "
        "You identify disagreements and remove unsupported conclusions instead of "
        "treating agreement between agents as validation. Separate observed or "
        "modelled findings, unknowns and recommendations. Discuss policy implications "
        "as suggestions, not proven causal effects or official decisions.",
        llm, tools,
    )
