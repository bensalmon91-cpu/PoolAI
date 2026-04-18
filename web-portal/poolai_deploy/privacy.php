<?php
/**
 * Privacy Policy - STUB.
 *
 * Placeholder. Replace with a legally reviewed privacy notice before any
 * paid rollout. In the UK this sits inside UK GDPR obligations: we need to
 * disclose controller identity, lawful basis, retention periods, third-party
 * processors (Stripe, Anthropic for AI, Hostinger for hosting), data
 * subject rights, and transfer mechanisms where relevant.
 */
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - PoolAIssistant</title>
    <link rel="stylesheet" href="/assets/css/portal.css">
    <style>
        body { max-width: 760px; margin: 2rem auto; padding: 0 1.25rem; line-height: 1.55; }
        .stub-warning {
            background: #fef2f2; border: 1px solid #fecaca; color: #991b1b;
            padding: 1rem; border-radius: 6px; margin: 1rem 0;
        }
        h1 { margin-bottom: 0.25rem; }
        h2 { margin-top: 2rem; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p class="muted">Last updated: <?= date('d F Y') ?></p>

    <div class="stub-warning">
        <strong>Draft / placeholder.</strong> This notice has not been
        reviewed for UK GDPR compliance. Do not rely on it as a legal
        document until replaced by reviewed language.
    </div>

    <h2>1. Who we are</h2>
    <p>PoolAIssistant is operated from the United Kingdom. Contact:
    <a href="mailto:ben.salmon91@gmail.com">ben.salmon91@gmail.com</a>.</p>

    <h2>2. What we collect</h2>
    <ul>
        <li><strong>Account data:</strong> email address, hashed password,
        optional display name, time of sign-up, time of ToS acceptance.</li>
        <li><strong>Pool telemetry:</strong> pH, chlorine, ORP, temperature,
        alarm events, and device health. These readings are associated with
        the account that linked the Pi device.</li>
        <li><strong>AI interactions:</strong> questions and answers exchanged
        with the AI assistant, plus admin review notes.</li>
        <li><strong>Billing data (when enabled):</strong> subscription state;
        payment details are handled by Stripe, not stored by us.</li>
    </ul>

    <h2>3. Why we process it</h2>
    <p>To provide the monitoring service, alert you to unsafe conditions,
    improve AI suggestions, run billing, and meet legal obligations.</p>

    <h2>4. Third-party processors</h2>
    <ul>
        <li>Hostinger (hosting &amp; database)</li>
        <li>Stripe (payments, when enabled)</li>
        <li>Anthropic (AI model queries) - pool telemetry may be included
        in the prompt context sent to generate suggestions.</li>
    </ul>

    <h2>5. Retention</h2>
    <p>Telemetry is retained for 12 months by default. Account data is
    retained while the account is active and for 30 days after deletion.</p>

    <h2>6. Your rights</h2>
    <p>Under UK GDPR you can request access, correction, deletion,
    portability, and object to processing. Email the address above.</p>

    <h2>7. Cookies</h2>
    <p>We use a session cookie to keep you logged in. No advertising or
    tracking cookies.</p>

    <h2>8. Changes</h2>
    <p>Material changes will be announced on the portal.</p>

    <p style="margin-top: 3rem;"><a href="/">&larr; Back to portal</a></p>
</body>
</html>
