import numpy as np
import networkx as nx
import torch
from torch_geometric.data import Data
import random
from typing import List, Tuple
import pickle
from tqdm import tqdm
import os

class LargeScaleDataGenerator:
    def __init__(self):
        self.min_nodes = 5
        self.max_nodes = 50
        self.edge_probability = 0.3
        
    def generate_graph(self):
        num_nodes = random.randint(self.min_nodes, self.max_nodes)
        
        if random.random() > 0.5:
            graph = nx.barabasi_albert_graph(num_nodes, 2)
        else:
            graph = nx.erdos_renyi_graph(num_nodes, self.edge_probability)
        
        roles = ['Researcher', 'Analyst', 'Reporter']
        for node in graph.nodes():
            graph.nodes[node]['role'] = random.choice(roles)
        
        features = []
        for node in graph.nodes():
            structural_score = np.random.beta(0.5, 2)
            semantic_drift = np.random.exponential(0.2)
            confidence = np.random.beta(2, 0.5)
            
            role_encoding = 1.0 if graph.nodes[node]['role'] == 'Researcher' else (
                0.5 if graph.nodes[node]['role'] == 'Analyst' else 0.0
            )
            
            features.append([structural_score, semantic_drift, confidence, role_encoding])
        
        x = torch.tensor(features, dtype=torch.float)
        
        edge_index = []
        for edge in graph.edges():
            edge_index.append([edge[0], edge[1]])
        
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).T
        else:
            edge_index = torch.tensor([[], []], dtype=torch.long)
        
        compromised_nodes = self._generate_compromise_pattern(graph)
        
        node_labels = torch.zeros(num_nodes, dtype=torch.long)
        for node in compromised_nodes:
            node_labels[node] = 1
        
        label = 1 if len(compromised_nodes) > 0 else 0
        
        data = Data(
            x=x,
            edge_index=edge_index,
            y=label,
            node_labels=node_labels,
            num_nodes=num_nodes
        )
        
        return data, label
    
    def _generate_compromise_pattern(self, graph):
        num_nodes = len(graph.nodes())
        
        if random.random() > 0.3:
            return []
        
        start_nodes = random.sample(range(num_nodes), random.randint(1, 3))
        
        compromised = set(start_nodes)
        for _ in range(random.randint(1, 3)):
            new_nodes = set()
            for node in compromised:
                neighbors = list(graph.neighbors(node))
                if neighbors:
                    spread_to = random.sample(neighbors, min(random.randint(1, 2), len(neighbors)))
                    new_nodes.update(spread_to)
            compromised.update(new_nodes)
        
        return list(compromised)
    
    def generate_dataset(self, num_samples):
        dataset = []
        for _ in tqdm(range(num_samples), desc="Generating samples"):
            data, _ = self.generate_graph()
            dataset.append(data)
        return dataset

os.makedirs('data', exist_ok=True)

if __name__ == "__main__":
    generator = LargeScaleDataGenerator()
    
    print("Generating 80,000 training samples...")
    train_data = generator.generate_dataset(80000)
    
    print("Generating 20,000 test samples...")
    test_data = generator.generate_dataset(20000)
    
    with open('data/train_data.pkl', 'wb') as f:
        pickle.dump(train_data, f)
    with open('data/test_data.pkl', 'wb') as f:
        pickle.dump(test_data, f)
    
    print("Dataset generated successfully!")
    print(f"Training samples: {len(train_data)}")
    print(f"Test samples: {len(test_data)}")
