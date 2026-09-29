"""CrewAI tools bound to one run and one specialist's allowed modules."""
import backend.crew_config  # privacy settings must precede CrewAI imports
from crewai.tools import tool
from backend.evidence import json_text


def make_tools(store, domain, activity):
    def record(name):
        activity.append({"agent": domain, "event": "tool", "tool": name})

    @tool("read_evidence")
    def read_evidence(module: str = "all") -> str:
        """Read source IDs, facts, limitations and exact table/column names for an available module."""
        record("read_evidence")
        payload = store.evidence(domain, module)
        text = json_text(payload)
        if len(text) > 10000:
            payload = store.evidence(domain, module, compact=True)
            payload["coverage_note"] = "Compact evidence; request one specific module for more detail. Some notes/table inventories omitted."
            text = json_text(payload)
        return text

    @tool("table_statistics")
    def table_statistics(module: str, table: str, column: str, operation: str = "mean") -> str:
        """Compute mean, median, min, max, count or a supported sum from an existing numeric table column."""
        record("table_statistics")
        return json_text(store.statistics(domain, module, table, column, operation))

    @tool("quality_checks")
    def quality_checks() -> str:
        """Read computed coverage, missing-evidence and spatial-scope checks for this specialist."""
        record("quality_checks")
        return json_text(store.check_scope(domain))

    return [read_evidence, table_statistics, quality_checks]
