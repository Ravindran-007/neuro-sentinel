import { render, screen, waitFor, act } from '@testing-library/react';
import App from './App';
import axios from 'axios';

jest.mock('axios');

const mockHealthData = {
  uptime_requests: 1250,
  redis: 'connected',
  status: 'operational'
};

const mockThresholdsData = {
  structural_thresholds: {
    Researcher: 0.02,
    Analyst: 0.015,
    Reporter: 0.018
  },
  semantic_drift_limits: {
    Researcher: 0.05,
    Analyst: 0.04,
    Reporter: 0.045
  }
};

const mockDetectData = {
  overall_status: 'CLEAN',
  structural_score: 0.001,
  semantic_drift: 0.0,
  confidence: 0.95,
  agent_role: 'Analyst',
  request_id: 'test_123'
};

describe('NeuroSentinel Dashboard', () => {
  beforeEach(() => {
    axios.get.mockClear();
    axios.post.mockClear();
    
    axios.get.mockImplementation((url) => {
      if (url.includes('/api/health')) {
        return Promise.resolve({ data: mockHealthData });
      }
      if (url.includes('/api/thresholds')) {
        return Promise.resolve({ data: mockThresholdsData });
      }
      return Promise.resolve({ data: {} });
    });
    
    axios.post.mockResolvedValue({ data: mockDetectData });
  });

  test('renders NeuroSentinel header', async () => {
    await act(async () => {
      render(<App />);
    });
    const elements = screen.getAllByText(/NEUROSENTINEL/i);
    expect(elements.length).toBeGreaterThan(0);
  });

  test('shows loading state initially', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/System State/i)).toBeInTheDocument();
    });
  });

  test('renders agent network section', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Agent Network/i)).toBeInTheDocument();
    });
  });

  test('renders Researcher, Analyst, and Reporter agents', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/Researcher/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Analyst/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Reporter/i).length).toBeGreaterThan(0);
    });
  });

  test('renders Custom Payload Test section', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Custom Payload Test/i)).toBeInTheDocument();
    });
  });

  test('renders agent selector dropdown', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      const selects = screen.getAllByRole('combobox');
      expect(selects.length).toBeGreaterThanOrEqual(2);
    });
  });

  test('renders preset test buttons', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/🌿 Clean/i)).toBeInTheDocument();
      expect(screen.getByText(/💉 Injection/i)).toBeInTheDocument();
      expect(screen.getByText(/☠️ Poisoning/i)).toBeInTheDocument();
      expect(screen.getByText(/🔓 Malicious/i)).toBeInTheDocument();
    });
  });

  test('renders Request Activity chart section', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Request Activity/i)).toBeInTheDocument();
    });
  });

  test('renders Alert Log section', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Alert Log/i)).toBeInTheDocument();
    });
  });

  test('renders footer with version info', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/NEUROSENTINEL v2.0/i)).toBeInTheDocument();
    });
  });

  test('displays system state readout', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/OPERATIONAL/i)).toBeInTheDocument();
    });
  });

  test('displays requests logged', async () => {
    await act(async () => {
      render(<App />);
    });
    await waitFor(() => {
      expect(screen.getByText(/1250/i)).toBeInTheDocument();
    });
  });
});