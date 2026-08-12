import networkx as nx
import torch
from torch_geometric.data import Data
from typing import Dict, List, Tuple, Optional, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger("NeuroSentinel-GNN")


class AgentGraphBuilder:
    def __init__(self):
        self.graph = nx.Graph()
        self.node_features = {}
        self.edge_weights = {}
        self.timestamps = {}
    
    def add_agent(
        self,
        agent_id: str,
        role: str,
        features: Dict[str, float],
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.graph.add_node(
            agent_id,
            role=role,
            **features
        )
        self.node_features[agent_id] = features
        self.timestamps[agent_id] = datetime.now().isoformat()
        logger.debug(f"Added agent: {agent_id} ({role})")
    
    def add_connection(
        self,
        agent_a: str,
        agent_b: str,
        weight: float = 1.0
    ):
        self.graph.add_edge(agent_a, agent_b, weight=weight)
        self.edge_weights[(agent_a, agent_b)] = weight
        logger.debug(f"Added connection: {agent_a} ↔ {agent_b}")
    
    def remove_agent(self, agent_id: str):
        if agent_id in self.graph:
            self.graph.remove_node(agent_id)
            self.node_features.pop(agent_id, None)
            logger.debug(f"Removed agent: {agent_id}")
    
    def update_features(self, agent_id: str, features: Dict[str, float]):
        if agent_id in self.graph:
            self.graph.nodes[agent_id].update(features)
            self.node_features[agent_id].update(features)
    
    def to_pyg_data(self) -> Data:
        nodes = list(self.graph.nodes())
        
        features = []
        for node in nodes:
            node_data = self.graph.nodes[node]
            feature_vector = [
                node_data.get('structural_score', 0.0),
                node_data.get('semantic_drift', 0.0),
                node_data.get('confidence', 0.0),
                1.0 if node_data.get('role') == 'Researcher' else
                0.5 if node_data.get('role') == 'Analyst' else 0.0
            ]
            features.append(feature_vector)
        
        x = torch.tensor(features, dtype=torch.float)
        
        edge_index = []
        for edge in self.graph.edges():
            try:
                i = nodes.index(edge[0])
                j = nodes.index(edge[1])
                edge_index.append([i, j])
            except ValueError:
                continue
        
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).T
        else:
            edge_index = torch.tensor([[], []], dtype=torch.long)
        
        return Data(x=x, edge_index=edge_index, num_nodes=len(nodes))
    
    def get_node_count(self) -> int:
        return len(self.graph.nodes())
    
    def get_edge_count(self) -> int:
        return len(self.graph.edges())
    
    def to_json(self) -> str:
        return json.dumps({
            'nodes': list(self.graph.nodes(data=True)),
            'edges': list(self.graph.edges(data=True)),
            'timestamp': datetime.now().isoformat()
        }, default=str)
    
    def save_to_file(self, filepath: str):
        with open(filepath, 'w') as f:
            f.write(self.to_json())
        logger.info(f"Graph saved to: {filepath}")
    
    def load_from_file(self, filepath: str):
        with open(filepath, 'r') as f:
            data = f.read()
        loaded = json.loads(data)
        self.graph = nx.Graph()
        for node, attrs in loaded.get('nodes', []):
            self.graph.add_node(node, **attrs)
        for u, v, attrs in loaded.get('edges', []):
            self.graph.add_edge(u, v, **attrs)
        logger.info(f"Graph loaded from: {filepath}")