import os
import torch
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import networkx as nx

from .models import CompromisePropagationGNN
from .graph_builder import AgentGraphBuilder

logger = logging.getLogger("NeuroSentinel-GNN")


class GNNPropagationDetector:
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = 'cpu',
        threshold: float = 0.5
    ):
        self.device = torch.device(device)
        self.threshold = threshold
        
        self.model = CompromisePropagationGNN(
            in_channels=4,
            hidden_channels=128,
            out_channels=2,
            num_layers=4
        )
        
        self.graph_builder = AgentGraphBuilder()
        
        if model_path and os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            logger.info(f"Loaded GNN model from: {model_path}")
        else:
            logger.info("Using untrained GNN model (placeholder)")
        
        self.model.to(self.device)
        self.model.eval()
    
    def detect_propagation(
        self,
        agents: List[Dict],
        connections: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        for agent in agents:
            self.graph_builder.add_agent(
                agent['id'],
                agent['role'],
                {
                    'structural_score': agent.get('structural_score', 0.0),
                    'semantic_drift': agent.get('semantic_drift', 0.0),
                    'confidence': agent.get('confidence', 0.0)
                }
            )
        
        for a, b in connections:
            self.graph_builder.add_connection(a, b)
        
        data = self.graph_builder.to_pyg_data().to(self.device)
        
        with torch.no_grad():
            result = self.model.forward(data.x, data.edge_index, return_embeddings=True)
        
        probabilities = torch.exp(result['predictions'])
        nodes = list(self.graph_builder.graph.nodes())
        
        node_predictions = {}
        for i, node in enumerate(nodes):
            prob = float(probabilities[i, 1])
            node_predictions[node] = {
                'compromise_probability': prob,
                'status': 'COMPROMISED' if prob > self.threshold else 'CLEAN',
                'propagation_score': float(result['propagation_score'][i])
            }
        
        paths = self._find_propagation_paths(node_predictions)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'node_predictions': node_predictions,
            'propagation_paths': paths,
            'compromised_count': sum(1 for p in node_predictions.values() if p['status'] == 'COMPROMISED'),
            'total_agents': len(node_predictions),
            'overall_risk': max(p['compromise_probability'] for p in node_predictions.values()),
            'graph_stats': {
                'nodes': self.graph_builder.get_node_count(),
                'edges': self.graph_builder.get_edge_count()
            }
        }
    
    def _find_propagation_paths(self, predictions: Dict) -> List:
        compromised = [n for n, p in predictions.items() if p['status'] == 'COMPROMISED']
        
        if len(compromised) < 2:
            return []
        
        graph = self.graph_builder.graph
        paths = []
        
        for i in range(len(compromised)):
            for j in range(i + 1, len(compromised)):
                try:
                    path = nx.shortest_path(graph, compromised[i], compromised[j])
                    paths.append({
                        'source': compromised[i],
                        'target': compromised[j],
                        'path': path,
                        'length': len(path)
                    })
                except:
                    pass
        
        return paths
    
    def reset_graph(self):
        self.graph_builder = AgentGraphBuilder()
    
    def get_graph_data(self) -> Dict:
        graph = self.graph_builder.graph
        nodes = list(graph.nodes(data=True))
        edges = list(graph.edges(data=True))
        
        return {
            'nodes': [{'id': n, **attrs} for n, attrs in nodes],
            'edges': [{'source': u, 'target': v, **attrs} for u, v, attrs in edges]
        }