"""Agent 1 of 5: establish the study scope and the team's review priorities."""
from backend.agent_common import make_agent


def build_agent(llm, tools):
    return make_agent(
        "Study coordinator",
        "Set a feasible evidence-led review plan for the saved environmental run.",
        "You check place labels against coordinates and the boundary, separate the "
        "historical period from forecast windows, and identify missing modules. "
        "You organize the existing specialists; you never create additional agents.",
        llm, tools,
    )
