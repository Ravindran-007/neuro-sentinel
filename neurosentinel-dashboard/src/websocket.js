import { io } from 'socket.io-client';

const SOCKET_URL = 'https://neuro-sentinel-0nhi.onrender.com';
export const socket = io(SOCKET_URL, {
  autoConnect: false,
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
});

export const connectSocket = () => {
  if (!socket.connected) {
    socket.connect();
  }
};

export const disconnectSocket = () => {
  if (socket.connected) {
    socket.disconnect();
  }
};

export const onAgentUpdate = (callback) => {
  socket.on('agent:update', callback);
};

export const onAlert = (callback) => {
  socket.on('alert:new', callback);
};

export const onDetection = (callback) => {
  socket.on('detection:new', callback);
};

export const offAgentUpdate = () => socket.off('agent:update');
export const offAlert = () => socket.off('alert:new');
export const offDetection = () => socket.off('detection:new');