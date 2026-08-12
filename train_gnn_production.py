import os
import torch
import torch.nn as nn
import pickle
from torch_geometric.data import DataLoader
from torch_geometric.nn import SAGEConv
import logging
from datetime import datetime
import json
import numpy as np

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.gnn import CompromisePropagationGNN

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("GNN-Training-Prod")

class ProductionGNNTrainer:
    def __init__(self, model, learning_rate=0.001, device='cpu'):
        self.model = model.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
        self.criterion = nn.CrossEntropyLoss()
    
    def train_epoch(self, loader):
        self.model.train()
        total_loss = 0
        for data in loader:
            data = data.to(self.device)
            self.optimizer.zero_grad()
            result = self.model(data.x, data.edge_index)
            loss = self.criterion(result['predictions'], data.node_labels)
            loss.backward()
            self.optimizer.step()
            total_loss += loss.item()
        return total_loss / len(loader)
    
    def evaluate(self, loader):
        self.model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for data in loader:
                data = data.to(self.device)
                result = self.model(data.x, data.edge_index)
                pred = result['predictions'].argmax(dim=1)
                correct += (pred == data.node_labels).sum().item()
                total += data.num_nodes
        return correct / total if total > 0 else 0
    
    def train(self, train_loader, test_loader, epochs=50):
        logger.info(f"Starting training for {epochs} epochs...")
        best_acc = 0
        
        for epoch in range(epochs):
            loss = self.train_epoch(train_loader)
            acc = self.evaluate(test_loader)
            
            if acc > best_acc:
                best_acc = acc
                torch.save(self.model.state_dict(), "models/gnn/production_model.pt")
            
            if (epoch + 1) % 5 == 0:
                logger.info(f"Epoch {epoch+1}/{epochs} | Loss: {loss:.4f} | Acc: {acc:.4f}")
        
        logger.info(f"Training complete! Best accuracy: {best_acc:.4f}")
        return best_acc

def main():
    # Create directories
    os.makedirs("models/gnn", exist_ok=True)
    
    # Load data
    logger.info("Loading datasets...")
    with open("data/train_data.pkl", "rb") as f:
        train_data = pickle.load(f)
    with open("data/test_data.pkl", "rb") as f:
        test_data = pickle.load(f)
    
    logger.info(f"Training samples: {len(train_data)}")
    logger.info(f"Test samples: {len(test_data)}")
    
    # Create loaders
    train_loader = DataLoader(train_data, batch_size=64, shuffle=True)
    test_loader = DataLoader(test_data, batch_size=64, shuffle=False)
    
    # Initialize model
    logger.info("Initializing model...")
    model = CompromisePropagationGNN(
        in_channels=4,
        hidden_channels=128,
        out_channels=2,
        num_layers=4
    )
    
    # Train
    trainer = ProductionGNNTrainer(model, learning_rate=0.001)
    best_acc = trainer.train(train_loader, test_loader, epochs=30)
    
    # Save config
    with open("models/gnn/production_config.json", "w") as f:
        json.dump({
            "train_samples": len(train_data),
            "test_samples": len(test_data),
            "epochs": 30,
            "hidden_channels": 128,
            "num_layers": 4,
            "best_accuracy": best_acc,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    
    logger.info(f"Production model saved with accuracy: {best_acc:.4f}")

if __name__ == "__main__":
    main()
