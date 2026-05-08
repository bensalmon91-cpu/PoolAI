<?php
/**
 * Allow-list of pooldash settings that admin can change remotely.
 *
 * DO NOT add secrets / device identity / backend URLs to this list - those
 * must be changed only via the device's local UI or a software update.
 * This list is the authoritative definition of "safely admin-editable".
 *
 * The Pi agent (pi-software/PoolDash_v6/scripts/health_reporter.py) must
 * use the SAME key set for its settings_snapshot payload; keep in sync.
 */

final class RemoteSettings {
    /**
     * @return array{type:string, label:string, min?:int, max?:int, options?:array, pattern?:string}[]
     *         Keyed by pooldash_settings.json key.
     */
    public static function schema(): array {
        return [
            'cloud_upload_enabled' => [
                'type' => 'bool', 'label' => 'Cloud upload enabled',
                'section' => 'Cloud sync',
            ],
            'cloud_upload_interval_minutes' => [
                'type' => 'int', 'label' => 'Cloud upload interval (minutes)',
                'min' => 1, 'max' => 60, 'section' => 'Cloud sync',
            ],
            'upload_interval_minutes' => [
                'type' => 'int', 'label' => 'Remote sync interval (minutes)',
                'min' => 1, 'max' => 1440, 'section' => 'Cloud sync',
            ],
            'data_retention_enabled' => [
                'type' => 'bool', 'label' => 'Data retention cleanup enabled',
                'section' => 'Data retention',
            ],
            'data_retention_full_days' => [
                'type' => 'int', 'label' => 'Keep full-resolution readings (days)',
                'min' => 1, 'max' => 365, 'section' => 'Data retention',
            ],
            'data_retention_hourly_days' => [
                'type' => 'int', 'label' => 'Keep hourly averages (days)',
                'min' => 1, 'max' => 730, 'section' => 'Data retention',
            ],
            'data_retention_daily_days' => [
                'type' => 'int', 'label' => 'Keep daily averages (days)',
                'min' => 1, 'max' => 3650, 'section' => 'Data retention',
            ],
            'storage_threshold_percent' => [
                'type' => 'int', 'label' => 'Aggressive cleanup at % disk used',
                'min' => 50, 'max' => 99, 'section' => 'Data retention',
            ],
            'screen_rotation' => [
                'type' => 'choice', 'label' => 'Screen rotation (deg)',
                'options' => [0 => '0', 90 => '90', 180 => '180', 270 => '270'],
                'section' => 'Display',
            ],
            'appearance_theme' => [
                'type' => 'choice', 'label' => 'Theme',
                'options' => ['light' => 'Light', 'dark' => 'Dark', 'system' => 'System'],
                'section' => 'Display',
            ],
            'appearance_font_size' => [
                'type' => 'choice', 'label' => 'Font size',
                'options' => ['small' => 'Small', 'medium' => 'Medium', 'large' => 'Large'],
                'section' => 'Display',
            ],
            'appearance_accent_color' => [
                'type' => 'choice', 'label' => 'Accent colour',
                'options' => [
                    'blue' => 'Blue', 'green' => 'Green', 'purple' => 'Purple',
                    'orange' => 'Orange', 'teal' => 'Teal',
                ],
                'section' => 'Display',
            ],
            'appearance_compact_mode' => [
                'type' => 'bool', 'label' => 'Compact UI mode',
                'section' => 'Display',
            ],
            'eco_mode_enabled' => [
                'type' => 'bool', 'label' => 'Eco mode (dim screen)',
                'section' => 'Eco mode',
            ],
            'eco_timeout_minutes' => [
                'type' => 'int', 'label' => 'Eco timeout (minutes)',
                'min' => 1, 'max' => 60, 'section' => 'Eco mode',
            ],
            'eco_brightness_percent' => [
                'type' => 'int', 'label' => 'Eco brightness (%)',
                'min' => 0, 'max' => 100, 'section' => 'Eco mode',
            ],
            'eco_wake_on_touch' => [
                'type' => 'bool', 'label' => 'Wake on touch',
                'section' => 'Eco mode',
            ],
            'chart_downsample' => [
                'type' => 'bool', 'label' => 'Downsample charts',
                'section' => 'Charts',
            ],
            'chart_max_points' => [
                'type' => 'int', 'label' => 'Max chart points',
                'min' => 500, 'max' => 20000, 'section' => 'Charts',
            ],
            'language' => [
                'type' => 'choice', 'label' => 'Language',
                'options' => ['en' => 'English', 'fr' => 'French', 'es' => 'Spanish',
                              'de' => 'German', 'it' => 'Italian', 'ru' => 'Russian'],
                'section' => 'Locale',
            ],
            'scheduled_reboot_enabled' => [
                'type' => 'bool', 'label' => 'Scheduled daily reboot',
                'section' => 'Maintenance',
            ],
            'scheduled_reboot_time' => [
                'type' => 'time', 'label' => 'Daily reboot time (HH:MM)',
                'pattern' => '/^\d{2}:\d{2}$/', 'section' => 'Maintenance',
            ],
        ];
    }

    /** Filter an input array of proposed settings down to validated values. */
    public static function validate(array $proposed): array {
        $schema = self::schema();
        $clean = [];
        $errors = [];

        foreach ($proposed as $key => $value) {
            if (!isset($schema[$key])) {
                $errors[$key] = 'not remotely editable';
                continue;
            }
            $def = $schema[$key];
            switch ($def['type']) {
                case 'bool':
                    $clean[$key] = (bool)(is_string($value)
                        ? in_array(strtolower($value), ['1', 'true', 'yes', 'on'], true)
                        : $value);
                    break;
                case 'int':
                    if (!is_numeric($value)) {
                        $errors[$key] = 'must be numeric'; break;
                    }
                    $v = (int)$value;
                    if (isset($def['min']) && $v < $def['min']) { $errors[$key] = 'below min'; break; }
                    if (isset($def['max']) && $v > $def['max']) { $errors[$key] = 'above max'; break; }
                    $clean[$key] = $v;
                    break;
                case 'choice':
                    $opts = $def['options'] ?? [];
                    // Accept either string or numeric keys.
                    if (!array_key_exists((string)$value, $opts) && !array_key_exists($value, $opts)) {
                        $errors[$key] = 'not an allowed option';
                        break;
                    }
                    $clean[$key] = is_numeric($value) ? (int)$value : (string)$value;
                    break;
                case 'time':
                    if (!is_string($value) || !preg_match($def['pattern'] ?? '/.*/', $value)) {
                        $errors[$key] = 'must be HH:MM'; break;
                    }
                    $clean[$key] = $value;
                    break;
                default:
                    $errors[$key] = 'unknown field type';
            }
        }
        return ['clean' => $clean, 'errors' => $errors];
    }

    /** @return string[] List of keys the Pi should report in heartbeat snapshots. */
    public static function snapshotKeys(): array {
        return array_keys(self::schema());
    }
}
