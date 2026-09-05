"""Current, read-only blueprint reporting; never imported by frozen evaluators."""

from .parser import PARSER_VERSION, build_requirement_inventory, parse_source_blocks

__all__ = ["PARSER_VERSION", "build_requirement_inventory", "parse_source_blocks"]
