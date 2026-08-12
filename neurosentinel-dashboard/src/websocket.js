// src/websocket.js
// WebSocket service for real-time updates

import { io } from 'socket.io-client';

// Create socket connection
const SOCKET_URL = 'https://neuro-sentinel-0nhi.onrender.com';
export const socket = io(SOCKET_URL, {
  autoConnect: false,
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
});

// Connect to socket
export const connectSocket = () => {
  if (!socket.connected) {
    socket.connect();
    console.log('🔌 WebSocket connecting...');
  }
};

// Disconnect socket
export const disconnectSocket = () => {
  if (socket.connected) {
    socket.disconnect();
    console.log('🔌 WebSocket disconnected');
  }
};

// Event listeners
export const onAgentUpdate = (callback) => {
  socket.on('agent:update', callback);
};

export const onAlert = (callback) => {
  socket.on('alert:new', callback);
};

export const onDetection = (callback) => {
  socket.on('detection:new', callback);
};

// Remove listeners
export const offAgentUpdate = () => socket.off('agent:update');
export const offAlert = () => socket.off('alert:new');
export const offDetection = () => socket.off('detection:new');