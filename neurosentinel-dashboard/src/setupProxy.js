const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'https://neuro-sentinel-0nhi.onrender.com',
      changeOrigin: true,
    })
  );
};