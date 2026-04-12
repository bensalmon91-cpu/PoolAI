/**
 * PoolAIssistant - Main Application JavaScript
 */

(function() {
  'use strict';

  // Set current year in footer
  function setYear() {
    const yearElement = document.getElementById('year');
    if (yearElement) {
      yearElement.textContent = new Date().getFullYear();
    }
  }

  // Handle form submissions with loading states
  function setupForms() {
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', function(e) {
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.disabled) {
          submitBtn.disabled = true;
          submitBtn.dataset.originalText = submitBtn.textContent;
          submitBtn.textContent = 'Loading...';

          // Re-enable after timeout (in case form doesn't navigate)
          setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = submitBtn.dataset.originalText;
          }, 5000);
        }
      });
    });
  }

  // Smooth scroll for anchor links
  function setupSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
          e.preventDefault();
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      });
    });
  }

  // Show/hide password toggle
  function setupPasswordToggles() {
    document.querySelectorAll('input[type="password"]').forEach(input => {
      const wrapper = document.createElement('div');
      wrapper.style.position = 'relative';
      input.parentNode.insertBefore(wrapper, input);
      wrapper.appendChild(input);

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn-ghost';
      toggle.style.cssText = 'position: absolute; right: 8px; top: 50%; transform: translateY(-50%); padding: 4px 8px; font-size: 12px;';
      toggle.textContent = 'Show';
      toggle.setAttribute('aria-label', 'Toggle password visibility');

      toggle.addEventListener('click', () => {
        if (input.type === 'password') {
          input.type = 'text';
          toggle.textContent = 'Hide';
        } else {
          input.type = 'password';
          toggle.textContent = 'Show';
        }
      });

      wrapper.appendChild(toggle);
    });
  }

  // Flash messages auto-dismiss
  function setupAlerts() {
    document.querySelectorAll('.alert').forEach(alert => {
      // Add close button
      const closeBtn = document.createElement('button');
      closeBtn.innerHTML = '&times;';
      closeBtn.className = 'btn-ghost';
      closeBtn.style.cssText = 'position: absolute; top: 8px; right: 8px; padding: 2px 8px; font-size: 18px; line-height: 1;';
      closeBtn.setAttribute('aria-label', 'Dismiss');
      closeBtn.addEventListener('click', () => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 200);
      });

      alert.style.position = 'relative';
      alert.appendChild(closeBtn);

      // Auto-dismiss success alerts
      if (alert.classList.contains('alert-success')) {
        setTimeout(() => {
          alert.style.opacity = '0';
          setTimeout(() => alert.remove(), 200);
        }, 5000);
      }
    });
  }

  // Keyboard navigation improvements
  function setupKeyboardNav() {
    // Close modals with Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal[style*="flex"]').forEach(modal => {
          modal.style.display = 'none';
        });
      }
    });
  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    setYear();
    setupForms();
    setupSmoothScroll();
    setupAlerts();
    setupKeyboardNav();

    // Add loaded class for CSS animations
    document.body.classList.add('loaded');
  });

  // Expose utilities globally
  window.PoolAI = {
    formatDate: (date) => {
      return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    },

    formatNumber: (num, decimals = 2) => {
      return Number(num).toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      });
    },

    showNotification: (message, type = 'info') => {
      const notification = document.createElement('div');
      notification.className = `alert alert-${type}`;
      notification.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px; animation: slideUp 0.3s ease-out;';
      notification.textContent = message;

      document.body.appendChild(notification);

      setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 200);
      }, 4000);
    },

    debounce: (func, wait) => {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }
  };

})();
