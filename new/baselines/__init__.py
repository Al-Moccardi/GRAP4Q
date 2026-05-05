"""Offline baselines for Bugs4Q repair: QChecker (static) + rule-based APR."""
from . import qchecker, rule_based_apr

__all__ = ["qchecker", "rule_based_apr"]
