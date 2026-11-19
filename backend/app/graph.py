"""Route deterministic tools through a LangGraph supervisor and emit evidence events."""

from collections.abc import AsyncIterator
from typing import TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from .data import DataRepository
from .llm import write_answer
from .models import Answer, ChatRequest, Route, Trace
from .rag import choose_route, search_docs
from .tools import analyze


class State(TypedDict, total=False):
    request: ChatRequest
    route: Route
    evidence: list[dict]
    trace: list[Trace]
    text: str
    limitations: list[str]


def build_graph(repo: DataRepository, docs: list[dict], dsn: str | None = None):
    def supervisor(state: State) -> State:
        route = choose_route(state["request"].question)
        return {
            "route": route,
            "trace": [
                Trace(
                    agent="Supervisor",
                    tool="route_question",
                    detail=f"Selected {route} specialist; asset scope remains user-selected.",
                )
            ],
            "limitations": [],
            "evidence": [],
        }

    def asset_agent(state: State) -> State:
        request = state["request"]
        asset = repo.find_asset(request.asset_id)
        children = repo.get_children(asset.id)
        sensors = repo.get_timeseries_for_asset(asset.id)
        evidence: dict = {
            "id": f"asset:{asset.id}",
            "asset": asset.model_dump(),
            "children": [child.model_dump() for child in children],
            "sensors": [{"id": s.id, "name": s.name, "unit": s.unit} for s in sensors],
        }
        return {
            "evidence": [evidence],
            "trace": state["trace"]
            + [
                Trace(agent="Asset Graph", tool=tool, detail=detail, evidence=[evidence["id"]])
                for tool, detail in [
                    ("find_asset", asset.name),
                    ("get_children", f"{len(children)} direct children"),
                    ("get_timeseries_for_asset", f"{len(sensors)} linked sensors"),
                ]
            ],
        }

    def selected_series(request: ChatRequest):
        available = repo.get_timeseries_for_asset(request.asset_id)
        if request.timeseries_id:
            available = [s for s in available if s.id == request.timeseries_id]
        else:
            hints = ["pressure", "temperature", "vibration", "flow"]
            kinds = [word for word in hints if word in request.question.casefold()]
            if kinds:
                available = [
                    s for s in available if any(word in s.name.casefold() for word in kinds)
                ]
        return available[:12]

    def time_agent(state: State) -> State:
        request = state["request"]
        evidence, trace, limits = [], list(state["trace"]), []
        if request.start_ms is None and request.end_ms is None:
            limits.append(
                "Statistics cover the loaded snapshot, not a live or inferred calendar window. Use start_ms/end_ms to select exact dates."
            )
        for item in selected_series(request):
            series = repo.get_series(item.id, request.start_ms, request.end_ms)
            if not series.points:
                limits.append(f"No {item.name} datapoints in the requested time window.")
                continue
            if item.points and (
                request.start_ms is not None
                and request.start_ms < item.points[0].timestamp
                or request.end_ms is not None
                and request.end_ms > item.points[-1].timestamp + 3600000
            ):
                limits.append(f"{item.name} only partially covers the requested window.")
            result = analyze(series)
            result["id"] = f"timeseries:{item.id}"
            evidence.append(result)
            for tool in ("get_datapoints", "compute_stats", "detect_anomalies"):
                trace.append(
                    Trace(
                        agent="Time Series Analyst",
                        tool=tool,
                        detail=f"{series.name}: {len(series.points)} recorded samples",
                        evidence=[result["id"]],
                    )
                )
        if not evidence:
            limits.append("No selected sensor has data in the requested scope.")
        return {"evidence": evidence, "trace": trace, "limitations": limits}

    def doc_agent(state: State) -> State:
        matches = search_docs(state["request"].question, docs, dsn)
        evidence = [
            {
                "id": f"procedure:{item['id']}",
                "title": item["title"],
                "text": item["text"],
                "source": "synthetic sample procedure",
            }
            for item in matches
        ]
        return {
            "evidence": evidence,
            "trace": state["trace"]
            + [
                Trace(
                    agent="Docs RAG",
                    tool="search_docs",
                    detail=f"{len(matches)} synthetic procedure matches",
                    evidence=[item["id"] for item in evidence],
                )
            ],
            "limitations": [
                "Procedures are synthetic educational samples. Consult approved site documentation."
            ],
        }

    def report_agent(state: State) -> State:
        assets = asset_agent(state)
        times = time_agent(state)
        return {
            "evidence": assets["evidence"] + times["evidence"],
            "trace": assets["trace"] + times["trace"][1:],
            "limitations": times["limitations"],
        }

    async def reporter(state: State) -> State:
        request = state["request"]
        evidence = state["evidence"]
        lines = []
        if repo.corpus.source == "synthetic":
            lines.append("Synthetic demonstration data.")
        for item in evidence:
            cite = f"[{item['id']}]"
            if "asset" in item:
                lines.append(
                    f"{item['asset']['name']} has {len(item['sensors'])} linked sensors. {cite}"
                )
                lines.extend(f"• {sensor['name']} ({sensor['unit']})" for sensor in item["sensors"])
            elif "mean" in item:
                lines.append(
                    f"{item['name']}: mean {item['mean']:.2f} {item['unit']}, "
                    f"range {item['minimum']:.2f}–{item['maximum']:.2f} {item['unit']}; "
                    f"{len(item['anomalies'])} statistical deviations. {cite}"
                )
            else:
                lines.append(
                    f"Synthetic sample: {item['title']}. {item['text'].splitlines()[-1]} {cite}"
                )
        if not evidence:
            lines.append("The selected scope has insufficient evidence to answer this question.")
        if request.mode == "executive":
            lines.insert(
                0,
                "Snapshot summary for review. Statistical deviations require context before action.",
            )
        limitations = list(state["limitations"])
        try:
            drafted = await write_answer(
                {"question": request.question, "evidence": evidence}, request.mode
            )
            if drafted:
                lines = (
                    ["Synthetic demonstration data."] if repo.corpus.source == "synthetic" else []
                ) + [drafted]
                limitations.append("Provider-written wording needs human grounding review.")
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            limitations.append(
                "The language provider failed; the answer uses the recorded tool evidence."
            )
        return {
            "text": "\n".join(lines),
            "limitations": limitations,
            "trace": state["trace"]
            + [
                Trace(
                    agent="Report",
                    tool="format_answer",
                    detail=f"{request.mode} answer with {len(evidence)} evidence records",
                    evidence=[item["id"] for item in evidence],
                )
            ],
        }

    graph = StateGraph(State)
    graph.add_node("supervisor", supervisor)
    for name, action in (
        ("assets", asset_agent),
        ("timeseries", time_agent),
        ("docs", doc_agent),
        ("report", report_agent),
        ("reporter", reporter),
    ):
        graph.add_node(name, action)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["route"],
        {name: name for name in ("assets", "timeseries", "docs", "report")},
    )
    for name in ("assets", "timeseries", "docs", "report"):
        graph.add_edge(name, "reporter")
    graph.add_edge("reporter", END)
    return graph.compile()


async def events(graph, request: ChatRequest, source: str) -> AsyncIterator[dict]:
    state: State = {"request": request}
    seen = 0
    async for update in graph.astream(state, stream_mode="updates"):
        for values in update.values():
            state.update(values)
            for trace in state.get("trace", [])[seen:]:
                yield {"event": "step", "data": trace.model_dump()}
            seen = len(state.get("trace", []))
    answer = Answer(
        text=state["text"],
        citations=[item["id"] for item in state["evidence"]],
        source=source,
        route=state["route"],
        trace=state["trace"],
        limitations=state["limitations"],
    )
    yield {"event": "answer", "data": answer.model_dump()}
