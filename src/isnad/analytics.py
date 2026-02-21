"""
Trust network analytics — graph analysis, community detection, sybil resistance.

Analyze trust networks: centrality, clusters, bridges, anomalies.
No external dependencies (networkx-free).
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


@dataclass
class AgentMetrics:
    """Per-agent analytics."""
    agent_id: str
    in_degree: int = 0          # attestations received
    out_degree: int = 0         # attestations given
    betweenness: float = 0.0    # bridge score
    pagerank: float = 0.0       # influence
    clustering_coeff: float = 0.0
    community: Optional[int] = None
    is_bridge: bool = False
    sybil_score: float = 0.0    # 0=clean, 1=likely sybil
    reciprocity: float = 0.0    # fraction of mutual attestations
    avg_trust_given: float = 0.0
    avg_trust_received: float = 0.0


@dataclass
class NetworkStats:
    """Aggregate network statistics."""
    num_agents: int = 0
    num_edges: int = 0
    density: float = 0.0
    avg_degree: float = 0.0
    num_components: int = 0
    largest_component_size: int = 0
    num_communities: int = 0
    avg_clustering: float = 0.0
    diameter: int = -1  # -1 if disconnected
    reciprocity: float = 0.0


class TrustGraph:
    """
    Lightweight directed graph for trust network analysis.
    
    Nodes = agent IDs, edges = attestations with trust scores.
    No external graph library needed.
    """

    def __init__(self):
        self._out: Dict[str, Dict[str, float]] = defaultdict(dict)  # src -> {dst: score}
        self._in: Dict[str, Dict[str, float]] = defaultdict(dict)   # dst -> {src: score}
        self._agents: Set[str] = set()

    def add_agent(self, agent_id: str) -> None:
        self._agents.add(agent_id)

    def add_edge(self, src: str, dst: str, score: float = 1.0) -> None:
        """Add a trust edge (attestation) from src to dst."""
        self._agents.add(src)
        self._agents.add(dst)
        self._out[src][dst] = score
        self._in[dst][src] = score

    def remove_edge(self, src: str, dst: str) -> None:
        self._out[src].pop(dst, None)
        self._in[dst].pop(src, None)

    @property
    def agents(self) -> Set[str]:
        return set(self._agents)

    @property
    def num_agents(self) -> int:
        return len(self._agents)

    @property
    def num_edges(self) -> int:
        return sum(len(targets) for targets in self._out.values())

    def out_neighbors(self, agent: str) -> Dict[str, float]:
        return dict(self._out.get(agent, {}))

    def in_neighbors(self, agent: str) -> Dict[str, float]:
        return dict(self._in.get(agent, {}))

    def out_degree(self, agent: str) -> int:
        return len(self._out.get(agent, {}))

    def in_degree(self, agent: str) -> int:
        return len(self._in.get(agent, {}))

    def has_edge(self, src: str, dst: str) -> bool:
        return dst in self._out.get(src, {})

    def edge_weight(self, src: str, dst: str) -> Optional[float]:
        return self._out.get(src, {}).get(dst)

    def to_undirected(self) -> Dict[str, Set[str]]:
        """Convert to undirected adjacency for community detection."""
        adj: Dict[str, Set[str]] = defaultdict(set)
        for src, targets in self._out.items():
            for dst in targets:
                adj[src].add(dst)
                adj[dst].add(src)
        for a in self._agents:
            if a not in adj:
                adj[a] = set()
        return dict(adj)


class TrustAnalytics:
    """
    Analyze trust network structure.
    
    All algorithms are self-contained (no networkx dependency).
    Designed for networks up to ~10k agents.
    """

    def __init__(self, graph: TrustGraph):
        self.graph = graph

    # ─── Degree & Basic ─────────────────────────────

    def degree_distribution(self) -> Dict[str, Tuple[int, int]]:
        """Return {agent_id: (in_degree, out_degree)}."""
        return {
            a: (self.graph.in_degree(a), self.graph.out_degree(a))
            for a in self.graph.agents
        }

    def density(self) -> float:
        """Graph density: edges / possible_edges."""
        n = self.graph.num_agents
        if n < 2:
            return 0.0
        return self.graph.num_edges / (n * (n - 1))

    def reciprocity(self) -> float:
        """Fraction of edges that are reciprocated."""
        if self.graph.num_edges == 0:
            return 0.0
        mutual = 0
        for src in self.graph.agents:
            for dst in self.graph.out_neighbors(src):
                if self.graph.has_edge(dst, src):
                    mutual += 1
        return mutual / self.graph.num_edges

    # ─── Connected Components ────────────────────────

    def connected_components(self) -> List[Set[str]]:
        """Find connected components (undirected)."""
        adj = self.graph.to_undirected()
        visited: Set[str] = set()
        components: List[Set[str]] = []

        for start in self.graph.agents:
            if start in visited:
                continue
            component: Set[str] = set()
            queue = deque([start])
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                component.add(node)
                for neighbor in adj.get(node, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if component:
                components.append(component)

        return sorted(components, key=len, reverse=True)

    def strongly_connected_components(self) -> List[Set[str]]:
        """Tarjan's SCC algorithm for directed graph."""
        index_counter = [0]
        stack: List[str] = []
        lowlink: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Set[str] = set()
        sccs: List[Set[str]] = []

        def strongconnect(v: str):
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in self.graph.out_neighbors(v):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                scc: Set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.add(w)
                    if w == v:
                        break
                sccs.append(scc)

        for v in self.graph.agents:
            if v not in index:
                strongconnect(v)

        return sorted(sccs, key=len, reverse=True)

    # ─── Shortest Paths ──────────────────────────────

    def bfs_distances(self, source: str) -> Dict[str, int]:
        """BFS shortest path distances from source."""
        dist: Dict[str, int] = {source: 0}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for neighbor in self.graph.out_neighbors(node):
                if neighbor not in dist:
                    dist[neighbor] = dist[node] + 1
                    queue.append(neighbor)
        return dist

    def diameter(self) -> int:
        """Diameter of largest weakly connected component. -1 if empty."""
        components = self.connected_components()
        if not components:
            return -1
        largest = components[0]
        if len(largest) < 2:
            return 0

        # Build undirected adj for largest component
        adj = self.graph.to_undirected()
        max_dist = 0
        for start in largest:
            dist: Dict[str, int] = {start: 0}
            queue = deque([start])
            while queue:
                node = queue.popleft()
                for nb in adj.get(node, set()):
                    if nb not in dist and nb in largest:
                        dist[nb] = dist[node] + 1
                        queue.append(nb)
                        max_dist = max(max_dist, dist[nb])
        return max_dist

    # ─── Centrality ──────────────────────────────────

    def pagerank(self, damping: float = 0.85, max_iter: int = 100, tol: float = 1e-6) -> Dict[str, float]:
        """PageRank centrality (power iteration)."""
        agents = list(self.graph.agents)
        n = len(agents)
        if n == 0:
            return {}

        rank = {a: 1.0 / n for a in agents}

        for _ in range(max_iter):
            new_rank: Dict[str, float] = {}
            dangling_sum = sum(
                rank[a] for a in agents if self.graph.out_degree(a) == 0
            )

            for a in agents:
                incoming = self.graph.in_neighbors(a)
                s = sum(rank[src] / self.graph.out_degree(src) for src in incoming)
                new_rank[a] = (1 - damping) / n + damping * (s + dangling_sum / n)

            # Check convergence
            diff = sum(abs(new_rank[a] - rank[a]) for a in agents)
            rank = new_rank
            if diff < tol:
                break

        return rank

    def betweenness_centrality(self) -> Dict[str, float]:
        """
        Brandes' betweenness centrality (directed).
        O(V * E) — practical for networks < 5k nodes.
        """
        agents = list(self.graph.agents)
        cb: Dict[str, float] = {a: 0.0 for a in agents}

        for s in agents:
            # BFS
            stack: List[str] = []
            pred: Dict[str, List[str]] = {a: [] for a in agents}
            sigma: Dict[str, int] = {a: 0 for a in agents}
            sigma[s] = 1
            dist: Dict[str, int] = {a: -1 for a in agents}
            dist[s] = 0
            queue = deque([s])

            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in self.graph.out_neighbors(v):
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            delta: Dict[str, float] = {a: 0.0 for a in agents}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != s:
                    cb[w] += delta[w]

        # Normalize
        n = len(agents)
        if n > 2:
            norm = 1.0 / ((n - 1) * (n - 2))
            cb = {a: v * norm for a, v in cb.items()}

        return cb

    # ─── Clustering ──────────────────────────────────

    def clustering_coefficient(self, agent: str) -> float:
        """Local clustering coefficient (directed)."""
        neighbors = set(self.graph.out_neighbors(agent)) | set(self.graph.in_neighbors(agent))
        neighbors.discard(agent)
        k = len(neighbors)
        if k < 2:
            return 0.0

        links = 0
        for u in neighbors:
            for v in neighbors:
                if u != v and self.graph.has_edge(u, v):
                    links += 1

        return links / (k * (k - 1))

    def avg_clustering(self) -> float:
        """Average clustering coefficient."""
        agents = list(self.graph.agents)
        if not agents:
            return 0.0
        return sum(self.clustering_coefficient(a) for a in agents) / len(agents)

    # ─── Community Detection ─────────────────────────

    def label_propagation(self, max_iter: int = 50) -> Dict[str, int]:
        """
        Label propagation community detection (undirected).
        Simple, fast, no parameters.
        """
        adj = self.graph.to_undirected()
        agents = sorted(self.graph.agents)  # deterministic order

        # Init: each agent = own community
        labels: Dict[str, int] = {a: i for i, a in enumerate(agents)}

        for _ in range(max_iter):
            changed = False
            for agent in agents:
                neighbors = adj.get(agent, set())
                if not neighbors:
                    continue

                # Count neighbor labels
                label_counts: Dict[int, int] = defaultdict(int)
                for nb in neighbors:
                    label_counts[labels[nb]] += 1

                # Pick most common (deterministic tie-breaking: min label)
                max_count = max(label_counts.values())
                best_labels = [l for l, c in label_counts.items() if c == max_count]
                best = min(best_labels)

                if labels[agent] != best:
                    labels[agent] = best
                    changed = True

            if not changed:
                break

        # Renumber communities 0..N
        unique = sorted(set(labels.values()))
        remap = {old: new for new, old in enumerate(unique)}
        return {a: remap[l] for a, l in labels.items()}

    def communities(self) -> List[Set[str]]:
        """Return list of communities (sets of agents)."""
        labels = self.label_propagation()
        groups: Dict[int, Set[str]] = defaultdict(set)
        for agent, label in labels.items():
            groups[label].add(agent)
        return sorted(groups.values(), key=len, reverse=True)

    # ─── Sybil Detection ─────────────────────────────

    def sybil_scores(self, seed_agents: Optional[Set[str]] = None) -> Dict[str, float]:
        """
        Sybil likelihood scoring based on structural signals.
        
        Heuristic signals:
        1. Low clustering + high degree = suspicious
        2. Reciprocity with only a small clique = suspicious
        3. No attestations from seed agents = suspicious
        4. All attestations from same small group = suspicious
        
        Returns {agent_id: score} where 0=clean, 1=likely sybil.
        """
        scores: Dict[str, float] = {}
        agents = list(self.graph.agents)

        if not agents:
            return {}

        # Precompute
        pr = self.pagerank()
        max_pr = max(pr.values()) if pr else 1.0

        for agent in agents:
            signals: List[float] = []

            in_deg = self.graph.in_degree(agent)
            out_deg = self.graph.out_degree(agent)
            total_deg = in_deg + out_deg

            # Signal 1: Degree imbalance (many out, few in = spam attestor)
            if total_deg > 0:
                imbalance = abs(out_deg - in_deg) / total_deg
                signals.append(imbalance * 0.3)

            # Signal 2: Low clustering despite connections
            cc = self.clustering_coefficient(agent)
            if total_deg >= 4 and cc < 0.1:
                signals.append(0.3)
            elif total_deg >= 2 and cc < 0.05:
                signals.append(0.2)

            # Signal 3: Low PageRank relative to degree
            if total_deg > 2 and max_pr > 0:
                pr_ratio = pr.get(agent, 0) / max_pr
                if pr_ratio < 0.01:
                    signals.append(0.2)

            # Signal 4: Not attested by seed agents
            if seed_agents:
                attested_by_seed = any(
                    src in seed_agents 
                    for src in self.graph.in_neighbors(agent)
                )
                if not attested_by_seed:
                    signals.append(0.3)

            # Signal 5: All attestations from single source
            in_neighbors = self.graph.in_neighbors(agent)
            if len(in_neighbors) == 1 and in_deg > 3:
                signals.append(0.4)

            scores[agent] = min(1.0, sum(signals))

        return scores

    # ─── Bridge Detection ────────────────────────────

    def bridges(self) -> Set[str]:
        """
        Find bridge agents — removal disconnects components.
        Uses articulation point detection on undirected graph.
        """
        adj = self.graph.to_undirected()
        visited: Set[str] = set()
        disc: Dict[str, int] = {}
        low: Dict[str, int] = {}
        parent: Dict[str, Optional[str]] = {}
        ap: Set[str] = set()
        timer = [0]

        def dfs(u: str):
            children = 0
            visited.add(u)
            disc[u] = low[u] = timer[0]
            timer[0] += 1

            for v in adj.get(u, set()):
                if v not in visited:
                    children += 1
                    parent[v] = u
                    dfs(v)
                    low[u] = min(low[u], low[v])

                    # u is AP if:
                    # 1) u is root and has 2+ children
                    if parent[u] is None and children > 1:
                        ap.add(u)
                    # 2) u is not root and low[v] >= disc[u]
                    if parent[u] is not None and low[v] >= disc[u]:
                        ap.add(u)
                elif v != parent.get(u):
                    low[u] = min(low[u], disc[v])

        for agent in self.graph.agents:
            if agent not in visited:
                parent[agent] = None
                dfs(agent)

        return ap

    # ─── Agent Metrics ───────────────────────────────

    def agent_metrics(self, agent: str, seed_agents: Optional[Set[str]] = None) -> AgentMetrics:
        """Full analytics for a single agent."""
        pr = self.pagerank()
        bc = self.betweenness_centrality()
        sybil = self.sybil_scores(seed_agents)
        communities = self.label_propagation()
        bridge_set = self.bridges()

        in_nb = self.graph.in_neighbors(agent)
        out_nb = self.graph.out_neighbors(agent)

        # Reciprocity
        mutual = sum(1 for dst in out_nb if self.graph.has_edge(dst, agent))
        total_connections = len(set(out_nb) | set(in_nb))
        recip = mutual / total_connections if total_connections > 0 else 0.0

        return AgentMetrics(
            agent_id=agent,
            in_degree=self.graph.in_degree(agent),
            out_degree=self.graph.out_degree(agent),
            betweenness=bc.get(agent, 0.0),
            pagerank=pr.get(agent, 0.0),
            clustering_coeff=self.clustering_coefficient(agent),
            community=communities.get(agent),
            is_bridge=agent in bridge_set,
            sybil_score=sybil.get(agent, 0.0),
            reciprocity=recip,
            avg_trust_given=sum(out_nb.values()) / len(out_nb) if out_nb else 0.0,
            avg_trust_received=sum(in_nb.values()) / len(in_nb) if in_nb else 0.0,
        )

    # ─── Network Stats ───────────────────────────────

    def network_stats(self) -> NetworkStats:
        """Aggregate network statistics."""
        n = self.graph.num_agents
        e = self.graph.num_edges
        components = self.connected_components()
        comms = self.communities()

        return NetworkStats(
            num_agents=n,
            num_edges=e,
            density=self.density(),
            avg_degree=e / n if n > 0 else 0.0,
            num_components=len(components),
            largest_component_size=len(components[0]) if components else 0,
            num_communities=len(comms),
            avg_clustering=self.avg_clustering(),
            diameter=self.diameter(),
            reciprocity=self.reciprocity(),
        )

    # ─── Trust Flow Analysis ─────────────────────────

    def trust_flow(self, source: str, target: str, max_depth: int = 5) -> List[List[Tuple[str, float]]]:
        """
        Find all trust paths from source to target (up to max_depth).
        Returns list of paths, each path = [(agent, edge_score), ...].
        """
        paths: List[List[Tuple[str, float]]] = []

        def dfs(current: str, path: List[Tuple[str, float]], visited: Set[str]):
            if len(path) > max_depth:
                return
            if current == target:
                paths.append(list(path))
                return
            for nb, score in self.graph.out_neighbors(current).items():
                if nb not in visited:
                    visited.add(nb)
                    path.append((nb, score))
                    dfs(nb, path, visited)
                    path.pop()
                    visited.discard(nb)

        dfs(source, [(source, 1.0)], {source})
        return paths

    def transitive_trust(self, source: str, target: str, decay: float = 0.8) -> float:
        """
        Calculate transitive trust from source to target.
        Each hop multiplies by decay factor.
        Returns max trust across all paths.
        """
        paths = self.trust_flow(source, target)
        if not paths:
            return 0.0

        max_trust = 0.0
        for path in paths:
            trust = 1.0
            for i in range(1, len(path)):
                trust *= path[i][1] * decay
            max_trust = max(max_trust, trust)

        return max_trust

    # ─── Export ───────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Export full analytics as dict."""
        stats = self.network_stats()
        pr = self.pagerank()
        bc = self.betweenness_centrality()
        comms = self.label_propagation()
        bridge_set = self.bridges()

        agents_data = {}
        for a in self.graph.agents:
            agents_data[a] = {
                "in_degree": self.graph.in_degree(a),
                "out_degree": self.graph.out_degree(a),
                "pagerank": round(pr.get(a, 0), 6),
                "betweenness": round(bc.get(a, 0), 6),
                "clustering": round(self.clustering_coefficient(a), 4),
                "community": comms.get(a),
                "is_bridge": a in bridge_set,
            }

        return {
            "network": {
                "agents": stats.num_agents,
                "edges": stats.num_edges,
                "density": round(stats.density, 4),
                "components": stats.num_components,
                "communities": stats.num_communities,
                "diameter": stats.diameter,
                "reciprocity": round(stats.reciprocity, 4),
                "avg_clustering": round(stats.avg_clustering, 4),
            },
            "agents": agents_data,
        }
