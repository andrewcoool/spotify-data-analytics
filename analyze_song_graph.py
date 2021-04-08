from typing import Union, Any
import song_graph
from song_graph import SongGraph, AttributeVertex, SongVertex, Vertex, Song
import networkx as nx


def get_most_significant_attributes_vertices(graph: SongGraph, n: int = 5, ignore_year=True) -> \
        list[AttributeVertex]:
    """Return the n most significant attribute vertices in the song graph.

    Preconditions:
        - song_graph.are_attributes_created()
    """

    attr_vertices = list(graph.get_attribute_vertices())
    attr_vertices.sort(key=lambda x: len(x.neighbours), reverse=True)

    to_return = []

    for attr in attr_vertices:
        if len(to_return) >= n:
            return to_return
        elif not ignore_year or attr.attribute_name != 'year':
            # If we are ignoring the year attribute, do
            # do not add the attribute if it is the year attribute.

            to_return.append(attr)

    return to_return


def get_most_significant_attributes(
        graph: SongGraph, n: int = 5, ignore_year=True) -> list[str]:
    """Return the n most significant attributes in the song graph.

    Preconditions:
        - song_graph.are_attributes_created()
    """

    to_return = []

    for v in get_most_significant_attributes_vertices(graph, n, ignore_year):
        to_return.append(v.item)

    return to_return


def get_song_similarity_continuous(graph: SongGraph, s1: Song, s2: Song):
    """Return a similarity score between two songs s1 and s2.

    This similarity score follows a continuous algorithm, which
    means that two songs will have a higher similarity score if
    their attributes are close together, rather them being exactly
    in the same range (which is what is used in get_vertex_similarity)
    """

    net_similarity = 0
    num_attributes = 0

    for attr_header in s1.attributes:
        if attr_header in song_graph.EXACT_HEADERS:
            # Then the similarity is:
            # 1 - If the attribute matches
            # 0 - If the attribute does not match
            net_similarity += int(s1.attributes[attr_header] == s2.attributes[attr_header])
        else:
            # Then the similarity is based
            # on the relative distance between the
            # attribute values
            min_, max_, avg, _ = graph.get_attribute_header_stats(attr_header, use_parent=True)

            # The closer they are, the more similar they should be
            net_similarity += 1 - abs(s1.attributes[attr_header] - s2.attributes[attr_header]) / (max_ - min_)

        num_attributes += 1

    return net_similarity / num_attributes


def get_vertex_similarity(v1: Vertex, v2: Vertex):
    """Return a similarity score between v1 and v2.

    The similarity score is calculated with the following formula:
        0.0 - if the number of distinct neighbours between v1 and v2 is 0

        Otherwise, it is equal to the number of length two paths
        between v1 and v2 (number of shared neighbours) divided
        by the number of distinct neighbours of v1 and v2.
    """

    shared = len(v1.neighbours.intersection(v2.neighbours))
    distinct = len(v1.neighbours.union(v2.neighbours))

    if distinct == 0:
        return 0.0
    else:
        return shared / distinct


def get_cluster_similarity(graph: SongGraph, cluster1: set[Vertex], cluster2: set[Vertex],
                           similarity_algorithm: str = 'continuous'):
    """Find the similarity between two clusters.
    The similarity of the two clusters is the average similarity
    between any two pairs of vertices in the two clusters.

    similarity_algorithm identifies which similarity algorithm is to be used.
    Note that this only applies to a vertex of type 'song' as the continuous
    similarity algorithm requires attributes that only song vertices have.

    Raise an AssertionError if similarity_algorithm='continuous' is passed
    and a vertex in any of the two clusters is not a SongVertex.

    Preconditions:
        - len(cluster1) > 0 and len(cluster2) > 0
        - cluster1.isdisjoint(cluster2)
    """

    total_similarity = 0

    for v in cluster1:
        for u in cluster2:
            if similarity_algorithm == 'continuous':
                assert isinstance(v, SongVertex) and isinstance(v, SongVertex)
                total_similarity += get_song_similarity_continuous(graph, v.item, u.item)
            else:
                total_similarity += get_vertex_similarity(v, u)

    return total_similarity / (len(cluster1) * len(cluster2))


def get_pairs(lst: list) -> tuple[Any, Any]:
    """(Iterator) Return all the pairs of items in lst.

    Preconditions:
        - len(lst) >= 2
    """

    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            yield lst[i], lst[j]


def find_clusters(graph: SongGraph, vertex_type: str = 'song', similarity_algorithm: str = 'continuous',
                  similarity_threshold: float = 0.75) -> list[set[Union[AttributeVertex, SongVertex]]]:
    """Find clusters in a song graph. This function uses an altered
    greedy clustering algorithm and instead maintains that the only clusters
    that should be merged together are those which are "similar enough".

    Rather than stopping when enough clusters are reached, the algorithm
    halts when there is either one cluster, or when any merging would
    merge two clusters which are too dissimilar to be merged.

    similarity_threshold identifies the minimum similarity that is
    needed for two clusters to be merged.

    similarity_algorithm identifies which similarity algorithm is to be used.
    Note that this only applies to vertex_type 'song' as the continuous
    similarity algorithm requires attributes that only song vertices have.

    Preconditions:
        - vertex_type in {'song', 'attribute'}
        - 0 <= similarity_threshold <= 1
    """
    if vertex_type == 'song':
        clusters = [{graph.get_vertex_by_item(song)} for song in graph.get_songs()]
    else:
        clusters = [{attr_v} for attr_v in graph.get_attribute_vertices()]

    max_similarity = 1

    while max_similarity >= similarity_threshold and len(clusters) >= 2:
        max_similarity_pair = None
        max_similarity = 0

        for c1, c2 in get_pairs(clusters):
            similarity = get_cluster_similarity(graph, c1, c2, similarity_algorithm)

            if similarity > max_similarity:
                max_similarity_pair = c1, c2
                max_similarity = similarity

        if max_similarity >= similarity_threshold:
            # Then merge the two most similar clusters
            max_similarity_pair[0].update(max_similarity_pair[1])
            clusters.remove(max_similarity_pair[1])

    return clusters


def get_top_attributes_from_song_cluster(graph: SongGraph, cluster: set[SongVertex], n: int = 3):
    """Return the top n attributes of the song cluster.

    (i.e.) the attribute with the most edges to songs in the cluster.
    """

    attribute_vertices = list(graph.get_attribute_vertices())
    attribute_vertices.sort(
        key=lambda x: len([0 for v in x.neighbours if v in cluster]),
        reverse=True)

    return attribute_vertices[:n]


def add_top_attribute_vertices_to_song_cluster(graph: SongGraph, graph_nx: nx.Graph,
                                               cluster: set[SongVertex], added_count: dict[str, int]):
    """Add the top two attribute vertices of the song cluster to a
    graph_nx graph. Get the top three attribute vertices from data
    stored in the SongGraph graph.

    Create an edge between each of the new attribute vertices to
    each of the song between the song clusters.

    added_count is a dictionary mapping an attribute label to
    the number of times it has already been added to the graph
    (from other clusters).

    Update added_count with any attribute_vertices which have
    been added to graph_nx.

    Preconditions:
        - all(song_v in graph_nx.nodes for song_v in cluster)
    """

    top_attributes = get_top_attributes_from_song_cluster(graph, cluster, 2)
    for attr in top_attributes:
        # Add a number to the end of the attributes to differentiate
        # the top attributes of one cluster to another if they are
        # the same. (I.e. prevent edges between clusters which
        # share the same top attribute).

        attr_label = attr.item

        if attr_label in added_count:
            added_vertex_label = attr_label + str(added_count[attr_label])
            graph_nx.add_node(added_vertex_label, kind='attribute', ends_with_int=True)

            added_count[attr_label] += 1

        else:
            added_vertex_label = attr_label + ' 0'
            graph_nx.add_node(added_vertex_label, kind='attribute', ends_with_int=True)

            added_count[attr_label] = 1

        for song_v in cluster:
            song_name = song_v.item.name

            graph_nx.add_edge(song_name, added_vertex_label)


def create_clustered_networkx_song_graph(graph: SongGraph, similarity_threshold: float = 0.75):
    """Return a focused networkx song graph based on the
    songs in the song graph.

    Create clusters and join song vertices in the same cluster
    with an edge given a similarity_threshold (see find_clusters).

    For each song cluster with 5 or more songs, create 2
    attribute vertices for the top 2 attributes of the song cluster
    and create an edge between each of the attribute vertices
    and each of the song vertices.

    Preconditions:
        - 0 <= similarity_threshold <= 1
    """

    clusters = find_clusters(graph, vertex_type='song',
                             similarity_threshold=similarity_threshold)
    graph_nx = nx.Graph()

    for song in graph.get_songs():
        graph_nx.add_node(song.name, kind='song')

    # The number of times an attribute has been added to graph_nx
    added_count = {}

    for cluster in clusters:
        cluster_lst = list(cluster)

        for i in range(1, len(cluster_lst)):
            graph_nx.add_edge(cluster_lst[0].item.name, cluster_lst[i].item.name)

        # Get top three attributes for large enough clusters
        if len(cluster) >= 5:
            add_top_attribute_vertices_to_song_cluster(graph, graph_nx, cluster, added_count)

    return graph_nx


def get_attribute_header_deviation(graph: SongGraph, attribute_header: str) -> float:
    """Return the deviation score with an attribute header between
    a child graph and its parent graph.

    The deviation score is equal to the absolute value difference
    between the averages from the child and parent graph, divided
    by the standard deviation of the parent graph. (Comparable to the
    z-score or standard score).

    Preconditions:
        - attribute_header in song_graph.INT_HEADERS.union(song_graph.FLOAT_HEADERS))
    """
    p_average, st_dev = graph.get_attribute_header_stats(attribute_header, use_parent=True)
    c_average, _ = graph.get_attribute_header_stats(attribute_header)


def get_most_deviated_attribute_headers(graph: SongGraph, n: int) -> list[str]:
    """Return the top n attribute headers of a child SongGraph
    which deviate the most from median of the parent SongGraph.

    Preconditions:
        - graph.parent_graph is not None
    """

    # attr_headers = list(song_graph.INT_HEADERS.union(song_graph.FLOAT_HEADERS))
    # attr_headers.sort(key=lambda x: 1graph.get_attribute_header_stats())


