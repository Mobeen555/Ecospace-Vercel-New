"""Agent 4 of 5: ecology and citizen-science/field evidence."""
from backend.agent_common import make_agent


def build_agent(llm, tools):
    return make_agent(
        "Ecology and field analyst",
        "Assess biodiversity records and included field samples with their sampling limitations.",
        "You distinguish no returned GBIF records from ecological absence. Uploaded "
        "measurements are unverified and only included samples support this study. "
        "Keep chlorophyll, Secchi depth and phosphorus units explicit. Interpret "
        "Carlson indices only when the user requested lake indices; do not apply "
        "them automatically to rivers. Suggest practical field validation.",
        llm, tools,
    )
