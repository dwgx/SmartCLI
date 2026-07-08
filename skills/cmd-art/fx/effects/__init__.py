"""Effect modules live here; ``fx.registry.load_all()`` imports every ``*.py``
in this folder (via pkgutil), so a new file with an ``@register``-ed Effect
subclass appears in the CLI automatically. Names starting with ``_`` are
skipped. Keep one effect family per module."""
