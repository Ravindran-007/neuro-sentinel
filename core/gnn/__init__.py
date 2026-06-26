# core/gnn/__init__.py
# GNN Module for NeuroSentinel - Compromise Propagation Detection

from .models import CompromisePropagationGNN, create_gnn_model
from .graph_builder import AgentGraphBuilder
from .detector import GNNPropagationDetector

__all__ = [
    'CompromisePropagationGNN',
    'create_gnn_model',
    'AgentGraphBuilder',
    'GNNPropagationDetector'
]
