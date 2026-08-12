import torch
import torch.nn as nn

class LSTMAutoencoder(nn.Module):
    def __init__(self, sequence_length: int, feature_dim: int, hidden_dim: int = 8):
        super(LSTMAutoencoder, self).__init__()
        self.sequence_length = sequence_length
        self.feature_dim = feature_dim
        
        self.encoder_lstm = nn.LSTM(
            input_size=feature_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True
        )
        
        self.decoder_lstm = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True
        )
        
        self.output_layer = nn.Linear(hidden_dim, feature_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.encoder_lstm(x)
        repeat_hidden = hidden.permute(1, 0, 2).repeat(1, self.sequence_length, 1)
        decoder_out, _ = self.decoder_lstm(repeat_hidden)
        reconstructed = self.output_layer(decoder_out)
        return reconstructed

class AnomalyEvaluator:
    @staticmethod
    def compute_reconstruction_loss(original: torch.Tensor, reconstructed: torch.Tensor) -> torch.Tensor:
        criterion = nn.MSELoss(reduction='none')
        return torch.mean(criterion(reconstructed, original), dim=2)