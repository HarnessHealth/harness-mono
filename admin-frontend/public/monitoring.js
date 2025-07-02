// Real-time client-side monitoring for admin frontend
class FrontendMonitor {
  constructor() {
    this.apiEndpoint = 'https://api.harness.health/admin/logs';
    this.sessionId = this.generateSessionId();
    this.setupErrorHandling();
    this.setupPerformanceMonitoring();
    this.setupNavigationTracking();
  }

  generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  }

  log(level, message, data = {}) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      sessionId: this.sessionId,
      url: window.location.href,
      userAgent: navigator.userAgent,
      ...data
    };

    // Send to API (if available)
    if (navigator.onLine) {
      fetch(this.apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(logEntry)
      }).catch(err => {
        console.warn('Failed to send log to API:', err);
      });
    }

    // Console logging for development
    console.log(`[${level.toUpperCase()}]`, message, data);
  }

  setupErrorHandling() {
    window.addEventListener('error', (event) => {
      this.log('error', 'JavaScript Error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack
      });
    });

    window.addEventListener('unhandledrejection', (event) => {
      this.log('error', 'Unhandled Promise Rejection', {
        reason: event.reason
      });
    });
  }

  setupPerformanceMonitoring() {
    if ('performance' in window) {
      window.addEventListener('load', () => {
        setTimeout(() => {
          const navigation = performance.getEntriesByType('navigation')[0];
          this.log('performance', 'Page Load Performance', {
            loadTime: navigation.loadEventEnd - navigation.loadEventStart,
            domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
            networkTime: navigation.responseEnd - navigation.requestStart
          });
        }, 0);
      });
    }
  }

  setupNavigationTracking() {
    // Track page views
    this.log('navigation', 'Page View', {
      page: window.location.pathname,
      referrer: document.referrer
    });

    // Track hash changes (for SPA routing)
    window.addEventListener('hashchange', () => {
      this.log('navigation', 'Hash Change', {
        newHash: window.location.hash,
        page: window.location.pathname
      });
    });
  }

  // Public methods for manual logging
  info(message, data) { this.log('info', message, data); }
  warn(message, data) { this.log('warn', message, data); }
  error(message, data) { this.log('error', message, data); }
  debug(message, data) { this.log('debug', message, data); }
}

// Initialize monitoring
const monitor = new FrontendMonitor();

// Make it globally available
window.monitor = monitor;

// Example usage:
// monitor.info('User clicked login button', { userId: 123 });
// monitor.error('Login failed', { error: 'Invalid credentials' });