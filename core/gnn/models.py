# core/gnn/models.py
# Graph Neural Network models for compromise propagation detection

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, GATConv
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger("NeuroSentinel-GNN")


class CompromisePropagationGNN(nn.Module):
    """
    Graph Neural Network for detecting compromise propagation.
    """
    
    def __init__(
        self,
        in_channels: int = 4,
        hidden_channels: int = 64,
        out_channels: int = 2,
        num_layers: int = 3,
        dropout: float = 0.3
    ):
        super().__init__()
        
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        
        # First layer
        self.convs.append(SAGEConv(in_channels, hidden_channels))
        self.norms.append(nn.BatchNorm1d(hidden_channels))
        
        # Hidden layers
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden_channels, hidden_channels))
            self.norms.append(nn.BatchNorm1d(hidden_channels))
        
        # Final layer
        self.convs.append(SAGEConv(hidden_channels, out_channels))
        
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU()
        
        # Attention for propagation path detection
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_channels,
            num_heads=4,
            batch_first=True
        )
        
        # Propagation classifier
        self.propagation_head = nn.Linear(hidden_channels, 1)
        
        logger.info(f"✅ GNN Model initialized: {num_layers} layers, {hidden_channels} hidden")
    
    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        return_embeddings: bool = False
    ) -> Dict[str, torch.Tensor]:
        """Forward pass through the GNN."""
        h = x
        embeddings = []
        
        for i, (conv, norm) in enumerate(zip(self.convs[:-1], self.norms)):
            h = conv(h, edge_index)
            h = norm(h)
            h = self.relu(h)
            h = self.dropout(h)
            embeddings.append(h)
        
        # Final layer
        h = self.convs[-1](h, edge_index)
        predictions = F.log_softmax(h, dim=1)
        
        # Attention for propagation
        if embeddings:
            attn_input = embeddings[-1].unsqueeze(0)
            attn_output, _ = self.attention(attn_input, attn_input, attn_input)
            propagation_score = torch.sigmoid(
                self.propagation_head(attn_output.squeeze(0))
            )
        else:
            propagation_score = torch.zeros(x.size(0), 1)
        
        result = {
            'predictions': predictions,
            'propagation_score': propagation_score.squeeze(-1)
        }
        
        if return_embeddings and embeddings:
            result['embeddings'] = embeddings[-1]
        
        return result
    
    def predict(self, x: torch.Tensor, edge_index: torch.Tensor) -> Dict[str, Any]:
        """Predict compromise probabilities for all nodes."""
        with torch.no_grad():
            result = self.forward(x, edge_index)
        
        probabilities = torch.exp(result['predictions'])
        
        return {
            'probabilities': probabilities[:, 1].tolist(),
            'propagation_scores': result['propagation_score'].tolist()
        }


def create_gnn_model(
    model_type: str = 'graphsage',
    in_channels: int = 4,
    hidden_channels: int = 64,
    num_layers: int = 3
) -> nn.Module:
    """Factory function for GNN models."""
    if model_type == 'graphsage':
        return CompromisePropagationGNN(
            in_channels=in_channels,
            hidden_channels=hidden_channels,
            num_layers=num_layers
        )
    elif model_type == 'gat':
        from torch_geometric.nn import GATConv
        class GATDetector(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv1 = GATConv(in_channels, hidden_channels, heads=4)
                self.conv2 = GATConv(hidden_channels * 4, 2, heads=1)
            
            def forward(self, x, edge_index):
                x = self.conv1(x, edge_index)
                x = F.relu(x)
                x = F.dropout(x, training=self.training)
                x = self.conv2(x, edge_index)
                return F.log_softmax(x, dim=1)
        return GATDetector()
    else:
        raise ValueError(f"Unknown model type: {model_type}")
