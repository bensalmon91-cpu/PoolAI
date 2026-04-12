<?php
/**
 * PoolAIssistant Web Portal Configuration
 */

// Session settings
define('PORTAL_SESSION_NAME', 'poolai_portal');
define('PORTAL_SESSION_LIFETIME', 60 * 60 * 24 * 7); // 7 days
define('PORTAL_SESSION_SECURE', true); // Require HTTPS

// Password requirements
define('PORTAL_PASSWORD_MIN_LENGTH', 8);
define('PORTAL_PASSWORD_BCRYPT_COST', 12);

// Rate limiting
define('PORTAL_MAX_LOGIN_ATTEMPTS', 5);
define('PORTAL_LOGIN_LOCKOUT_MINUTES', 15);

// Token expiry
define('PORTAL_EMAIL_VERIFY_HOURS', 24);
define('PORTAL_PASSWORD_RESET_HOURS', 1);
define('PORTAL_LINK_CODE_MINUTES', 15);

// Email settings (using Hostinger SMTP)
define('PORTAL_EMAIL_FROM', 'noreply@poolaissistant.modprojects.co.uk');
define('PORTAL_EMAIL_FROM_NAME', 'PoolAIssistant');

// URLs
define('PORTAL_BASE_URL', 'https://poolaissistant.modprojects.co.uk/portal');
define('PORTAL_API_URL', 'https://poolaissistant.modprojects.co.uk/api/portal');

// CSRF token name
define('PORTAL_CSRF_TOKEN_NAME', 'portal_csrf_token');
