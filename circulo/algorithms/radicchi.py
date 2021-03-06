import sys
import igraph as ig
import itertools
import argparse

def radicchi(G, measure='weak'):
    """ Wrapper for execution of the Radicchi community-detection algorithm. Returns 
    covers of the graph, with metadata representing provenance - in essence, a "dendrogram"
    that represents splits into communities. """
    g = G.copy()
    g.vs['id'] = list(range(g.vcount()))

    if measure=='weak':
        result = radicchi_internal(G, g, 0, measure=measure, clustering=4)
    elif measure=='strong':
        result = radicchi_internal(G, g, 0, measure=measure, clustering=3)
    else:
        raise Exception('Other measures of community not yet supported')

    clustering = [0] * G.vcount()
    for i,l in enumerate(result):
        for v in l:
            clustering[v] = i

    return ig.VertexClustering(G, clustering)

def radicchi_internal(G, g, level, measure='strong', clustering=3):
    """
    Uses the Radicchi et al. algorithm to find the communities in a graph. Returns a list of the splits in the graph.
    """
    # Caching some global graph information and updating it manually. Because igraph
    # tends to recalculate this stuff on the whole graph every time, 
    # storing it and manipulating only the parts that change will make things faster.

    degree = g.degree()
    neighbors = [set(g.neighbors(v)) for v in g.vs]
    edges = {e.tuple for e in g.es}
    n_components = len(g.components())

    if clustering == 3:
        edge_clustering_coefficient = edge_clustering_coefficient_3 
    else:
        edge_clustering_coefficient = edge_clustering_coefficient_4

    communities = []
    while True:
        if len(edges) == 0:
            break

        min_edges = []; min_ecc = None
        for e in edges:
            ecc = edge_clustering_coefficient(e[0], e[1], degree, neighbors)
            if not min_ecc or ecc < min_ecc:
                min_edges = [e]
                min_ecc = ecc
            elif ecc == min_ecc:
                min_edges.append(e)

        g.delete_edges(min_edges); 
        for min_edge in min_edges:
            edges.discard(min_edge)
            u, v = min_edge
            neighbors[u].discard(v); neighbors[v].discard(u)
            degree[u] -= 1; degree[v] -= 1

        n_components_new = len(g.components())

        if n_components_new > n_components:
            result = prune_components(G, g, community_measure=measure)
            n_components = n_components_new
            if result['pruned']:
                orig_communities = result['orig_communities']
                new_communities = result['new_communities']
                remaining = result['remaining']

                for i,c in enumerate(new_communities):
                    s = g.subgraph(c)
                    subcommunities = radicchi_internal(G, s, level+1, measure)
                    if len(subcommunities) == 0:
                        communities.append(orig_communities[i])
                    else:
                        communities.extend(subcommunities)

                orig_remaining = [g.vs[i]['id'] for i in remaining]
                r = g.subgraph(remaining)
                subcommunities = radicchi_internal(G, r, level+1, measure)
                clustered = sum(subcommunities, [])
                isolated_remaining = [i for i in orig_remaining if i not in clustered]
                communities.extend([[i] for i in isolated_remaining])

                break

    return communities

def prune_components(orig, new, community_measure='strong'):
    """ Uses the given community measure to prune connected components in the graph new that
        represent communities in the graph orig, using the given community measure.  """
    components = new.components()
    ids = new.vs['id']

    new_components = [c for c in components]
    orig_components = [[ids[v] for v in component] for component in new_components]

    is_community = is_strong_community if (community_measure=='strong') else is_weak_community
    community_indices = [i for i, component in enumerate(orig_components) if is_community(orig, component)]

    orig_communities = [orig_components[i] for i in community_indices]
    new_communities = [new_components[i] for i in community_indices]

    result_pruned = False
    result_remaining_nodes = None
    result_orig_communities = None
    result_new_communities = None
    if len(community_indices) > 1:
        all_new_community_nodes = sum(new_communities, [])
        all_new_nodes = range(new.vcount())
        all_new_remaining_nodes = list(set(all_new_nodes) - set(all_new_community_nodes))

        result_pruned = True
        result_remaining_nodes = all_new_remaining_nodes
        result_new_communities = new_communities
        result_orig_communities = orig_communities

    return {"pruned": result_pruned, "orig_communities": result_orig_communities, 
            "new_communities": result_new_communities, "remaining": result_remaining_nodes}

def is_strong_community(G, nodes):
    """
    Checks whether the provided set of nodes form a strong community in the graph G.
    """
    # precondition: nodes must be sorted
    subgraph = G.subgraph(nodes)
    degree = G.degree(nodes)
    community_degree = subgraph.degree()
    for i in range(len(nodes)):
        if community_degree[i] <= (degree[i] - community_degree[i]):
            return False

    return True

def is_weak_community(G, nodes):
    """
    Checks whether the provided set of nodes form a weak community in the graph G.
    """
    # precondition: nodes must be sorted
    subgraph = G.subgraph(nodes)
    degree = G.degree(nodes)
    indegree = subgraph.degree()
    tsum = sum(degree)
    insum = sum(indegree)
    outsum = tsum - insum

    return insum > outsum

def edge_clustering_coefficient_3(u, v, degree, neighbors):
    """
    Computes the "edge clustering coefficient" of the given edge, defined as the number of triangles
    in which it participates compared to the maximum number of triangles of which it could be a part.
    """
    udeg = degree[u]
    vdeg = degree[v]
    mdeg = min(udeg-1, vdeg-1)
    if mdeg == 0:
        return float('inf')
    else:
        cdeg = len(neighbors[u] & neighbors[v])
        return (cdeg + 1.0) / mdeg

def edge_clustering_coefficient_4(u, v, degree, neighbors):
    """
    Computes a modified form of the edge clustering coefficient using squares instead of triangles.
    """
    udeg = degree[u]
    vdeg = degree[v]
    mdeg = (udeg-1)*(vdeg-1)
    if mdeg == 0:
        return float('inf')
    else:
        uneighbors = neighbors[u] - {v}
        vneighbors = neighbors[v] - {u} 

        num_squares = 0
        for w in uneighbors:
            wneighbors = neighbors[w] - {u} 
            num_squares += len(wneighbors & vneighbors)
        
        return (num_squares + 1.0) / mdeg

def main():
    parser = argparse.ArgumentParser(description="""Run the Radicchi algorithm from the command line.""")
    parser.add_argument('-s', '--strength', choices=['strong', 'weak'], 
                        help="""Use strong or weak definition of community structure in the graph.""")
    parser.add_argument('file', nargs='?', help="""The path to the file in the GML file format.""")
    args = parser.parse_args()

    if not args.file:
        print("radicchi.py: error: no file specified.")
        print(parser.parse_args(['-h']))
        return

    g = ig.Graph.Read_GML(args.file).as_undirected()
    communities = radicchi(g, measure=args.strength)

    print(communities)

ig.Graph.community_radicchi = radicchi
if __name__ == "__main__":
    main()

