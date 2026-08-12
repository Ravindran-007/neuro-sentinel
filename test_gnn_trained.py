from core.gnn import GNNPropagationDetector

# Load trained model
detector = GNNPropagationDetector(model_path='models/gnn/gnn_model.pt')
print('✅ Trained GNN model loaded!')

# Test with sample agents
agents = [
    {'id': 'agent1', 'role': 'Researcher', 'structural_score': 0.3, 'semantic_drift': 0.1, 'confidence': 0.9},
    {'id': 'agent2', 'role': 'Analyst', 'structural_score': 0.8, 'semantic_drift': 0.4, 'confidence': 0.5},
    {'id': 'agent3', 'role': 'Reporter', 'structural_score': 0.1, 'semantic_drift': 0.05, 'confidence': 0.95}
]
connections = [('agent1', 'agent2'), ('agent2', 'agent3')]

result = detector.detect_propagation(agents, connections)
print('✅ Detection complete!')
print(f'   Compromised: {result["compromised_count"]}')
print(f'   Overall risk: {result["overall_risk"]:.2f}')
print(f'   Nodes: {result["graph_stats"]["nodes"]}')
print(f'   Edges: {result["graph_stats"]["edges"]}')
