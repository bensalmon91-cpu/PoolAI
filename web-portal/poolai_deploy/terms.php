<?php
/**
 * Terms of Service - STUB.
 *
 * This is a placeholder so the sign-up flow can link to a canonical URL.
 * Replace the body with legally reviewed text BEFORE enabling billing or
 * charging any customer. A qualified lawyer should draft this - the risk
 * of shipping unreviewed ToS is strictly greater than not having any at
 * all, because this stub creates a contract reference from the signup
 * checkbox.
 */
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service - PoolAIssistant</title>
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
    <h1>Terms of Service</h1>
    <p class="muted">Last updated: <?= date('d F Y') ?></p>

    <div class="stub-warning">
        <strong>Draft / placeholder.</strong> These terms have not yet been
        reviewed by a qualified lawyer. Do not enable paid subscriptions
        until this document is replaced with reviewed language.
    </div>

    <h2>1. Service description</h2>
    <p>PoolAIssistant provides monitoring, alerting, and AI-assisted
    suggestions for swimming pool operators. The service includes a
    cloud portal at <code>poolai.modprojects.co.uk</code> and on-site
    Raspberry Pi devices that relay telemetry from pool controllers.</p>

    <h2>2. AI guidance is advisory only</h2>
    <p>Any recommendation, dosing suggestion, or analysis produced by
    the AI component of the service is advisory only. You, the pool
    operator, remain solely responsible for verifying and acting on any
    suggestion. The service does not replace a competent pool operator
    or any applicable regulations (including but not limited to HSG 179
    for public pools in the United Kingdom).</p>

    <h2>3. Acceptable use</h2>
    <p>Do not reverse engineer, resell, or use the service in any way
    that could endanger bathers. Do not upload data you are not
    entitled to share.</p>

    <h2>4. Data</h2>
    <p>See our <a href="/privacy.php">Privacy Policy</a> for how we
    handle pool telemetry and account information.</p>

    <h2>5. Billing (when enabled)</h2>
    <p>Subscriptions are processed by Stripe. Charges, refunds, and
    cancellations follow the plan's stated billing cycle. Access may be
    suspended for non-payment after any grace period we publish.</p>

    <h2>6. Limitation of liability</h2>
    <p>To the maximum extent permitted by applicable law, the service
    is provided "as is" without warranty. We are not liable for damages
    arising from reliance on AI suggestions, device outages, or
    telemetry gaps. Operators must maintain independent monitoring and
    manual checks as required by site procedure and law.</p>

    <h2>7. Changes</h2>
    <p>We may update these terms. Material changes will be announced on
    the portal at least 14 days before they take effect.</p>

    <h2>8. Contact</h2>
    <p>Questions: <a href="mailto:ben.salmon91@gmail.com">ben.salmon91@gmail.com</a>.</p>

    <p style="margin-top: 3rem;"><a href="/">&larr; Back to portal</a></p>
</body>
</html>
