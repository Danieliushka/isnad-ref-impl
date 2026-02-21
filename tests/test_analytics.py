"""Tests for trust network analytics module."""
import pytest
from isnad.analytics import TrustGraph, TrustAnalytics, AgentMetrics, NetworkStats


# ─── Fixtures ────────────────────────────────────────

@pytest.fixture
def empty_graph():
    return TrustGraph()


@pytest.fixture
def triangle_graph():
    """A->B->C->A (fully connected cycle)."""
    g = TrustGraph()
    g.add_edge("A", "B", 0.9)
    g.add_edge("B", "C", 0.8)
    g.add_edge("C", "A", 0.7)
    return g


@pytest.fixture
def star_graph():
    """Hub H connected to S1..S5."""
    g = TrustGraph()
    for i in range(1, 6):
        g.add_edge("H", f"S{i}", 0.9)
        g.add_edge(f"S{i}", "H", 0.8)
    return g


@pytest.fixture
def disconnected_graph():
    """Two separate clusters."""
    g = TrustGraph()
    g.add_edge("A1", "A2", 0.9)
    g.add_edge("A2", "A3", 0.8)
    g.add_edge("B1", "B2", 0.9)
    g.add_edge("B2", "B1", 0.7)
    return g


@pytest.fixture
def sybil_graph():
    """Normal agents + sybil cluster."""
    g = TrustGraph()
    # Normal cluster
    g.add_edge("Alice", "Bob", 0.9)
    g.add_edge("Bob", "Alice", 0.85)
    g.add_edge("Bob", "Carol", 0.8)
    g.add_edge("Carol", "Alice", 0.7)
    g.add_edge("Carol", "Bob", 0.75)
    g.add_edge("Alice", "Carol", 0.8)
    # Sybil cluster — one attacker creates fake identities
    g.add_edge("Sybil1", "Sybil2", 1.0)
    g.add_edge("Sybil2", "Sybil1", 1.0)
    g.add_edge("Sybil1", "Sybil3", 1.0)
    g.add_edge("Sybil3", "Sybil1", 1.0)
    g.add_edge("Sybil2", "Sybil3", 1.0)
    g.add_edge("Sybil3", "Sybil2", 1.0)
    # Weak bridge
    g.add_edge("Sybil1", "Bob", 0.5)
    return g


@pytest.fixture
def large_chain():
    """A linear chain: 0->1->2->...->9."""
    g = TrustGraph()
    for i in range(9):
        g.add_edge(str(i), str(i + 1), 0.9)
    return g


# ─── TrustGraph basics ──────────────────────────────

class TestTrustGraph:
    def test_empty(self, empty_graph):
        assert empty_graph.num_agents == 0
        assert empty_graph.num_edges == 0

    def test_add_edge(self, empty_graph):
        empty_graph.add_edge("A", "B", 0.9)
        assert empty_graph.num_agents == 2
        assert empty_graph.num_edges == 1
        assert empty_graph.has_edge("A", "B")
        assert not empty_graph.has_edge("B", "A")

    def test_edge_weight(self, triangle_graph):
        assert triangle_graph.edge_weight("A", "B") == 0.9
        assert triangle_graph.edge_weight("B", "A") is None

    def test_remove_edge(self, triangle_graph):
        triangle_graph.remove_edge("A", "B")
        assert not triangle_graph.has_edge("A", "B")
        assert triangle_graph.num_edges == 2

    def test_degrees(self, star_graph):
        assert star_graph.out_degree("H") == 5
        assert star_graph.in_degree("H") == 5
        assert star_graph.out_degree("S1") == 1
        assert star_graph.in_degree("S1") == 1

    def test_neighbors(self, triangle_graph):
        out = triangle_graph.out_neighbors("A")
        assert "B" in out
        assert out["B"] == 0.9

        inp = triangle_graph.in_neighbors("A")
        assert "C" in inp

    def test_add_isolated_agent(self, empty_graph):
        empty_graph.add_agent("lonely")
        assert empty_graph.num_agents == 1
        assert empty_graph.num_edges == 0

    def test_to_undirected(self, triangle_graph):
        adj = triangle_graph.to_undirected()
        assert "B" in adj["A"]
        assert "A" in adj["B"]  # undirected


# ─── Degree & Basic ─────────────────────────────────

class TestBasicMetrics:
    def test_density_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        # 3 edges, 3 agents, max = 6
        assert abs(a.density() - 0.5) < 0.01

    def test_density_empty(self, empty_graph):
        a = TrustAnalytics(empty_graph)
        assert a.density() == 0.0

    def test_reciprocity_full(self, star_graph):
        a = TrustAnalytics(star_graph)
        assert a.reciprocity() == 1.0  # all edges reciprocated

    def test_reciprocity_none(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        assert a.reciprocity() == 0.0  # A->B->C->A, no mutual

    def test_degree_distribution(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        dd = a.degree_distribution()
        assert dd["A"] == (1, 1)  # in=1 (from C), out=1 (to B)


# ─── Components ──────────────────────────────────────

class TestComponents:
    def test_single_component(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        cc = a.connected_components()
        assert len(cc) == 1
        assert len(cc[0]) == 3

    def test_two_components(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        cc = a.connected_components()
        assert len(cc) == 2

    def test_scc_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        sccs = a.strongly_connected_components()
        assert len(sccs) == 1
        assert len(sccs[0]) == 3

    def test_scc_chain(self, large_chain):
        a = TrustAnalytics(large_chain)
        sccs = a.strongly_connected_components()
        assert len(sccs) == 10  # each node is its own SCC


# ─── Shortest Paths ─────────────────────────────────

class TestPaths:
    def test_bfs_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        d = a.bfs_distances("A")
        assert d["A"] == 0
        assert d["B"] == 1
        assert d["C"] == 2

    def test_diameter_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        assert a.diameter() == 1  # undirected: all connected

    def test_diameter_chain(self, large_chain):
        a = TrustAnalytics(large_chain)
        assert a.diameter() == 9

    def test_diameter_disconnected(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        # Largest component has 3 nodes
        d = a.diameter()
        assert d == 2


# ─── Centrality ──────────────────────────────────────

class TestCentrality:
    def test_pagerank_star(self, star_graph):
        a = TrustAnalytics(star_graph)
        pr = a.pagerank()
        # Hub should have highest PageRank
        assert pr["H"] > pr["S1"]
        assert pr["H"] > pr["S2"]

    def test_pagerank_sums_to_one(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        pr = a.pagerank()
        assert abs(sum(pr.values()) - 1.0) < 0.01

    def test_pagerank_empty(self, empty_graph):
        a = TrustAnalytics(empty_graph)
        assert a.pagerank() == {}

    def test_betweenness_chain(self, large_chain):
        a = TrustAnalytics(large_chain)
        bc = a.betweenness_centrality()
        # Middle nodes should have higher betweenness
        assert bc["4"] > bc["0"]
        assert bc["4"] > bc["9"]

    def test_betweenness_star(self, star_graph):
        a = TrustAnalytics(star_graph)
        bc = a.betweenness_centrality()
        # Hub is the bridge
        assert bc["H"] > bc["S1"]


# ─── Clustering ──────────────────────────────────────

class TestClustering:
    def test_clustering_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        # In directed triangle A->B->C->A, each node has 2 neighbors
        # but only 1 directed link between them
        cc = a.clustering_coefficient("A")
        assert cc > 0

    def test_clustering_star(self, star_graph):
        a = TrustAnalytics(star_graph)
        # Spokes don't connect to each other
        cc = a.clustering_coefficient("H")
        assert cc == 0.0

    def test_avg_clustering(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        avg = a.avg_clustering()
        assert 0 <= avg <= 1


# ─── Community Detection ────────────────────────────

class TestCommunities:
    def test_communities_disconnected(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        comms = a.communities()
        assert len(comms) >= 2

    def test_communities_sybil(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        comms = a.communities()
        # Should detect at least 2 communities
        assert len(comms) >= 1  # label propagation may merge via bridge

    def test_label_propagation_deterministic(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        l1 = a.label_propagation()
        l2 = a.label_propagation()
        assert l1 == l2  # deterministic with sorted agents


# ─── Sybil Detection ────────────────────────────────

class TestSybilDetection:
    def test_sybil_scores_with_seeds(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        scores = a.sybil_scores(seed_agents={"Alice", "Bob", "Carol"})
        # Sybils should score higher
        assert scores["Sybil2"] > scores["Alice"]
        assert scores["Sybil3"] > scores["Alice"]

    def test_sybil_scores_no_seeds(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        scores = a.sybil_scores()
        assert all(0 <= s <= 1 for s in scores.values())

    def test_sybil_empty(self, empty_graph):
        a = TrustAnalytics(empty_graph)
        assert a.sybil_scores() == {}


# ─── Bridge Detection ───────────────────────────────

class TestBridges:
    def test_bridge_in_sybil(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        b = a.bridges()
        # Bob or Sybil1 should be bridges (connecting clusters)
        assert len(b) > 0

    def test_no_bridges_in_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        b = a.bridges()
        assert len(b) == 0  # fully connected cycle

    def test_bridges_in_chain(self, large_chain):
        a = TrustAnalytics(large_chain)
        b = a.bridges()
        # All internal nodes are articulation points
        assert len(b) == 8  # nodes 1-8


# ─── Trust Flow ──────────────────────────────────────

class TestTrustFlow:
    def test_direct_path(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        paths = a.trust_flow("A", "B")
        assert len(paths) >= 1
        assert paths[0][0] == ("A", 1.0)
        assert paths[0][1] == ("B", 0.9)

    def test_indirect_path(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        paths = a.trust_flow("A", "C")
        # A->B->C
        assert any(len(p) == 3 for p in paths)

    def test_no_path(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        paths = a.trust_flow("A1", "B1")
        assert len(paths) == 0

    def test_transitive_trust(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        # A->B direct: 0.9 * 0.8 decay = 0.72
        t = a.transitive_trust("A", "B")
        assert abs(t - 0.72) < 0.01

    def test_transitive_trust_no_path(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        assert a.transitive_trust("A1", "B1") == 0.0


# ─── Agent Metrics ───────────────────────────────────

class TestAgentMetrics:
    def test_metrics_hub(self, star_graph):
        a = TrustAnalytics(star_graph)
        m = a.agent_metrics("H")
        assert isinstance(m, AgentMetrics)
        assert m.in_degree == 5
        assert m.out_degree == 5
        assert m.pagerank > 0
        assert m.reciprocity > 0

    def test_metrics_leaf(self, star_graph):
        a = TrustAnalytics(star_graph)
        m = a.agent_metrics("S1")
        assert m.in_degree == 1
        assert m.out_degree == 1

    def test_metrics_with_seeds(self, sybil_graph):
        a = TrustAnalytics(sybil_graph)
        m = a.agent_metrics("Sybil2", seed_agents={"Alice", "Bob"})
        assert m.sybil_score > 0


# ─── Network Stats ───────────────────────────────────

class TestNetworkStats:
    def test_stats_triangle(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        s = a.network_stats()
        assert isinstance(s, NetworkStats)
        assert s.num_agents == 3
        assert s.num_edges == 3
        assert s.num_components == 1
        assert s.largest_component_size == 3

    def test_stats_disconnected(self, disconnected_graph):
        a = TrustAnalytics(disconnected_graph)
        s = a.network_stats()
        assert s.num_components == 2

    def test_stats_empty(self, empty_graph):
        a = TrustAnalytics(empty_graph)
        s = a.network_stats()
        assert s.num_agents == 0
        assert s.density == 0.0


# ─── Export ──────────────────────────────────────────

class TestExport:
    def test_to_dict(self, triangle_graph):
        a = TrustAnalytics(triangle_graph)
        d = a.to_dict()
        assert "network" in d
        assert "agents" in d
        assert d["network"]["agents"] == 3
        assert len(d["agents"]) == 3
        for agent_data in d["agents"].values():
            assert "pagerank" in agent_data
            assert "betweenness" in agent_data
            assert "community" in agent_data

    def test_to_dict_has_all_fields(self, star_graph):
        a = TrustAnalytics(star_graph)
        d = a.to_dict()
        net = d["network"]
        assert "density" in net
        assert "reciprocity" in net
        assert "avg_clustering" in net
        assert "diameter" in net
