# graph_features/ (Person B)

`import_graph.py` - static `ast` import graph per repo; blast radius and depth per package (see its docstring).

    python graph_features/import_graph.py --repos aio-libs/yarl aio-libs/multidict Textualize/rich
    python -m unittest discover -s graph_features/tests

Limitations: HEAD snapshot only (per-PR point-in-time graphs: Weeks 5-7); static imports only
(`importlib` / `__import__` not followed); import-name -> package-name mapping uses a small alias table.
A package with `blast_direct = 0` is declared but never imported directly (dev tool, plugin, transitive pin).
