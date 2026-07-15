"""Request graph: nodes are discovered URLs, edges record how one URL led to
another during a crawl. Lets later phases (assessment plugins, reporting)
show how an endpoint was reached, not just that it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autofuzz.web.crawler import CrawlResult


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str


@dataclass
class RequestGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_result(self, result: CrawlResult) -> None:
        self.nodes.add(result.url)
        for link in result.discovered_links:
            self.nodes.add(link)
            self.edges.append(GraphEdge(source=result.url, target=link))

    def discovered_via(self, url: str) -> list[str]:
        """Return the URLs whose links led to ``url`` during the crawl."""
        return [edge.source for edge in self.edges if edge.target == url]

    @classmethod
    def from_crawl_results(cls, results: list[CrawlResult]) -> RequestGraph:
        graph = cls()
        for result in results:
            graph.add_result(result)
        return graph
