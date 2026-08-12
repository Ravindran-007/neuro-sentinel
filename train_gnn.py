#!/usr/bin/env python
# train_gnn.py
# Train GNN model for compromise propagation detection

import os
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import networkx as nx
from torch_geometric.data import Data, DataLoader
from torch_geometric.nn import SAGEConv
from datetime import datetime
import logging
from typing import List, Dict, Tuple, Optional
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.gnn import CompromisePropagationGNN, AgentGraphBuilder, GNNPropagationDetector

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("GNN-Training")


# ─────────────────────────────────────────────────────────────
# DATA GENERATOR
# ─────────────────────────────────────────────────────────────
class PropagationDataGenerator:
    """
    Generate synthetic data for training GNN propagation detection.
    """
    
    def __init__(self, num_nodes: int = 5, num_samples: int = 1000):
        self.num_nodes = num_nodes
        self.num_samples = num_samples
        
        # Agent roles
        self.roles = ['Researcher', 'Analyst', 'Reporter']
        
        # Compromise patterns
        self.compromise_patterns = [
            'single_agent',
            'two_agents',
            'propagation_path',
            'cluster'
        ]
    
    def generate_sample(self) -> Tuple[Data, int]:
        """
        Generate a single training sample.
        
        Returns:
            (Data, label): PyG data object and binary label
        """
        # Create random graph
        graph = nx.erdos_renyi_graph(self.num_nodes, 0.3)
        
        # Assign roles
        for node in graph.nodes():
            graph.nodes[node]['role'] = np.random.choice(self.roles)
        
        # Generate features
        features = []
        for node in graph.nodes():
            structural_score = np.random.uniform(0.0, 1.0)
            semantic_drift = np.random.uniform(0.0, 0.5)
            confidence = np.random.uniform(0.5, 1.0)
            
            role_encoding = 1.0 if graph.nodes[node]['role'] == 'Researcher' else (
                0.5 if graph.nodes[node]['role'] == 'Analyst' else 0.0
            )
            
            features.append([structural_score, semantic_drift, confidence, role_encoding])
        
        x = torch.tensor(features, dtype=torch.float)
        
        # Build edge index
        edge_index = []
        for edge in graph.edges():
            edge_index.append([edge[0], edge[1]])
        
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).T
        else:
            edge_index = torch.tensor([[], []], dtype=torch.long)
        
        # Generate label (0 = no compromise, 1 = compromised)
        # Randomly compromise some nodes
        compromised_nodes = np.random.choice(
            range(self.num_nodes),
            size=np.random.randint(0, 3),
            replace=False
        )
        
        # Create binary label (1 if any node compromised)
        label = 1 if len(compromised_nodes) > 0 else 0
        
        # Create node labels for training
        node_labels = torch.zeros(self.num_nodes, dtype=torch.long)
        for node in compromised_nodes:
            node_labels[node] = 1
        
        data = Data(
            x=x,
            edge_index=edge_index,
            y=label,
            node_labels=node_labels,
            num_nodes=self.num_nodes
        )
        
        return data, label
    
    def generate_dataset(self, num_samples: int) -> List[Data]:
        """
        Generate a dataset of samples.
        """
        dataset = []
        for _ in range(num_samples):
            data, _ = self.generate_sample()
            dataset.append(data)
        
        return dataset


# ─────────────────────────────────────────────────────────────
# TRAINER
# ─────────────────────────────────────────────────────────────
class GNNTrainer:
    """
    Train the GNN model for compromise detection.
    """
    
    def __init__(
        self,
        model: nn.Module,
        learning_rate: float = 0.001,
        epochs: int = 100,
        device: str = 'cpu'
    ):
        self.model = model.to(device)
        self.device = device
        self.learning_rate = learning_rate
        self.epochs = epochs
        
        self.optimizer = torch.optim.Adam(
            model.parameters(),
            lr=learning_rate
        )
        self.criterion = nn.CrossEntropyLoss()
    
    def train_step(self, data: Data) -> float:
        """
        Perform a single training step.
        """
        self.model.train()
        self.optimizer.zero_grad()
        
        data = data.to(self.device)
        result = self.model(data.x, data.edge_index)
        
        # Use node labels for training
        loss = self.criterion(result['predictions'], data.node_labels)
        loss.backward()
        self.optimizer.step()
        
        return loss.item()
    
    def train_epoch(self, dataloader: DataLoader) -> float:
        """
        Train for one epoch.
        """
        total_loss = 0.0
        num_batches = 0
        
        for batch in dataloader:
            loss = self.train_step(batch)
            total_loss += loss
            num_batches += 1
        
        return total_loss / num_batches if num_batches > 0 else 0.0
    
    def evaluate(self, dataloader: DataLoader) -> Dict:
        """
        Evaluate the model on a test set.
        """
        self.model.eval()
        
        total_correct = 0
        total_samples = 0
        total_loss = 0.0
        
        with torch.no_grad():
            for data in dataloader:
                data = data.to(self.device)
                result = self.model(data.x, data.edge_index)
                
                # Node-level prediction
                pred = result['predictions'].argmax(dim=1)
                correct = (pred == data.node_labels).sum().item()
                total_correct += correct
                total_samples += data.num_nodes
                
                # Calculate loss
                loss = self.criterion(result['predictions'], data.node_labels)
                total_loss += loss.item()
        
        return {
            'accuracy': total_correct / total_samples if total_samples > 0 else 0.0,
            'loss': total_loss / len(dataloader) if len(dataloader) > 0 else 0.0
        }
    
    def train(
        self,
        train_loader: DataLoader,
        test_loader: Optional[DataLoader] = None,
        epochs: Optional[int] = None
    ):
        """
        Full training loop.
        """
        if epochs is None:
            epochs = self.epochs
        
        logger.info(f"🚀 Starting training for {epochs} epochs...")
        
        for epoch in range(epochs):
            train_loss = self.train_epoch(train_loader)
            
            if test_loader is not None:
                metrics = self.evaluate(test_loader)
                logger.info(
                    f"Epoch {epoch+1}/{epochs} | "
                    f"Train Loss: {train_loss:.4f} | "
                    f"Test Acc: {metrics['accuracy']:.4f}"
                )
            else:
                logger.info(f"Epoch {epoch+1}/{epochs} | Train Loss: {train_loss:.4f}")
        
        logger.info("✅ Training complete!")
    
    def save_model(self, filepath: str):
        """
        Save the trained model.
        """
        torch.save(self.model.state_dict(), filepath)
        logger.info(f"✅ Model saved to: {filepath}")
    
    def load_model(self, filepath: str):
        """
        Load a trained model.
        """
        self.model.load_state_dict(torch.load(filepath, map_location=self.device))
        logger.info(f"✅ Model loaded from: {filepath}")


# ─────────────────────────────────────────────────────────────
# MAIN TRAINING SCRIPT
# ─────────────────────────────────────────────────────────────
def main():
    """Main training function."""
    
    # Configuration
    NUM_NODES = 5
    NUM_TRAIN_SAMPLES = 5000
    NUM_TEST_SAMPLES = 1000
    BATCH_SIZE = 32
    EPOCHS = 50
    HIDDEN_CHANNELS = 64
    LEARNING_RATE = 0.001
    
    logger.info("=" * 60)
    logger.info("🧠 GNN Training for NeuroSentinel")
    logger.info("=" * 60)
    logger.info(f"Nodes per graph: {NUM_NODES}")
    logger.info(f"Training samples: {NUM_TRAIN_SAMPLES}")
    logger.info(f"Test samples: {NUM_TEST_SAMPLES}")
    logger.info(f"Batch size: {BATCH_SIZE}")
    logger.info(f"Epochs: {EPOCHS}")
    
    # Generate data
    logger.info("📊 Generating training data...")
    generator = PropagationDataGenerator(num_nodes=NUM_NODES)
    train_data = generator.generate_dataset(NUM_TRAIN_SAMPLES)
    test_data = generator.generate_dataset(NUM_TEST_SAMPLES)
    
    # Create dataloaders
    train_loader = DataLoader(train_data, batch_size=BATCH_SIZE, shuffle=True)
    test_loader = DataLoader(test_data, batch_size=BATCH_SIZE, shuffle=False)
    
    # Create model
    logger.info("🔧 Initializing GNN model...")
    model = CompromisePropagationGNN(
        in_channels=4,
        hidden_channels=HIDDEN_CHANNELS,
        out_channels=2,
        num_layers=3
    )
    
    # Create trainer
    trainer = GNNTrainer(
        model=model,
        learning_rate=LEARNING_RATE,
        epochs=EPOCHS
    )
    
    # Train
    logger.info("🚀 Starting training...")
    trainer.train(train_loader, test_loader)
    
    # Save model
    model_path = os.path.join("models", "gnn", "gnn_model.pt")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    trainer.save_model(model_path)
    
    # Evaluate final
    logger.info("📊 Final evaluation...")
    metrics = trainer.evaluate(test_loader)
    logger.info(f"✅ Final Test Accuracy: {metrics['accuracy']:.4f}")
    
    # Save training config
    config = {
        'num_nodes': NUM_NODES,
        'train_samples': NUM_TRAIN_SAMPLES,
        'test_samples': NUM_TEST_SAMPLES,
        'batch_size': BATCH_SIZE,
        'epochs': EPOCHS,
        'hidden_channels': HIDDEN_CHANNELS,
        'learning_rate': LEARNING_RATE,
        'final_accuracy': metrics['accuracy'],
        'timestamp': datetime.now().isoformat()
    }
    
    with open(os.path.join("models", "gnn", "training_config.json"), 'w') as f:
        json.dump(config, f, indent=2)
    
    logger.info("✅ Training complete! Model saved to models/gnn/gnn_model.pt")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
