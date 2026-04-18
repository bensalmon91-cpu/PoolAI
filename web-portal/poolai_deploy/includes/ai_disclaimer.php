<?php
/**
 * AI guidance disclaimer partial.
 *
 * Included anywhere AI-generated content is rendered to a customer. Reuse
 * this rather than duplicating wording so legal text is changed in one place.
 *
 * Usage:
 *   require __DIR__ . '/includes/ai_disclaimer.php';
 *   render_ai_disclaimer();               // default severity
 *   render_ai_disclaimer('public_pool');   // stronger banner for HSG 179 contexts
 */

if (!function_exists('render_ai_disclaimer')) {
    function render_ai_disclaimer(string $context = 'standard'): void {
        $strong = ($context === 'public_pool');
        ?>
        <div class="ai-disclaimer<?= $strong ? ' ai-disclaimer--strong' : '' ?>"
             role="note" aria-label="AI guidance disclaimer">
            <strong>AI guidance is advisory only.</strong>
            You remain responsible for verifying any dosing, equipment, or
            safety recommendation before acting on it. Do not treat AI
            suggestions as a substitute for a competent pool operator or
            your local regulations.
            <?php if ($strong): ?>
            <div class="ai-disclaimer__hsg">
                Public pool operators: this tool does not replace the duties
                and risk assessments required by HSG 179 and your site's
                written safe-operating procedures.
            </div>
            <?php endif; ?>
        </div>
        <?php
    }
}
