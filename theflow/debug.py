from .base import Function


def has_cycle(graph: dict[str, list[str]]) -> bool:
    """Check if a graph has cycle

    Args:
        graph: A graph represented by an adjacency list

    Returns:
        True if the graph has cycle, False otherwise
    """
    visited: set[str] = set()
    path: set[str] = set()

    def visit(vertex):
        if vertex in visited:
            return False
        visited.add(vertex)
        path.add(vertex)
        for neighbour in graph.get(vertex, []):
            if neighbour in path or visit(neighbour):
                return True
        path.remove(vertex)
        return False

    return any(visit(v) for v in graph)


def has_cyclic_dependency(cls: type[Function]):
    """Check if a component's nodes and params has cyclic dependency

    Args:
        cls: A function

    Returns:
        True if the function has cyclic dependency, False otherwise
    """
    params, nodes = cls._collect_registered_params_and_nodes()
    specs: dict[str, dict] = {}
    graph: dict[str, list[str]] = {}

    # construct dependency graph
    for attr in nodes + params:
        graph[attr] = []
        spec: dict = specs.get(attr, {}) or getattr(cls, attr).to_dict()
        if spec["auto_callback"] or spec["default_callback"]:
            if not spec["depends_on"]:
                continue
            for src in spec["depends_on"]:
                src_spec: dict = specs.get(src, {}) or getattr(cls, src).to_dict()
                if src_spec["auto_callback"] or src_spec["default_callback"]:
                    graph[attr].append(src)

    return has_cycle(graph)
