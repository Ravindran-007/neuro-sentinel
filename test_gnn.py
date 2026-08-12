from core.gnn import GNNPropagationDetector

# Create detector
detector = GNNPropagationDetector()

# Sample agents
agents = [
    {'id': 'agent1', 'role': 'Researcher', 'structural_score': 0.3},
    {'id': 'agent2', 'role': 'Analyst', 'structural_score': 0.8},
    {'id': 'agent3', 'role': 'Reporter', 'structural_score': 0.1}
]
connections = [('agent1', 'agent2'), ('agent2', 'agent3')]

# Detect propagation
result = detector.detect_propagation(agents, connections)

print('✅ GNN detection working!')
print(f'Compromised: {result["compromised_count"]}')
print(f'Overall risk: {result["overall_risk"]:.2f}')
print(f'Graph nodes: {result["graph_stats"]["nodes"]}')
print(f'Graph edges: {result["graph_stats"]["edges"]}')

# Print node predictions
for node, pred in result["node_predictions"].items():
    print(f'  {node}: {pred["status"]} (prob: {pred["compromise_probability"]:.2f})')
