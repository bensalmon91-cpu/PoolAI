"""
Simple translation system for PoolAIssistant.
Uses JSON dictionaries for each supported language.
"""

SUPPORTED_LANGUAGES = {
    'en': {'name': 'English', 'flag': '🇬🇧'},
    'fr': {'name': 'Français', 'flag': '🇫🇷'},
    'es': {'name': 'Español', 'flag': '🇪🇸'},
    'de': {'name': 'Deutsch', 'flag': '🇩🇪'},
    'it': {'name': 'Italiano', 'flag': '🇮🇹'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺'},
}

# Translation dictionaries
# English is the base - if a translation is missing, English is used
TRANSLATIONS = {
    'en': {
        # Settings page - Headers
        'settings': 'Settings',
        'quick_connect': 'Quick Connect',
        'connection_details': 'Connection Details',
        'ip_address': 'IP Address',
        'hostname': 'Hostname',
        'save': 'Save',
        'language': 'Language',

        # Settings page - Controllers
        'controllers': 'Controllers',
        'add_controller': 'Add Controller',
        'controller_name': 'Controller Name',
        'controller_ip': 'IP Address',
        'controller_port': 'Port',
        'pool_volume': 'Pool Volume (litres)',
        'enabled': 'Enabled',
        'disabled': 'Disabled',
        'delete': 'Delete',
        'no_controllers': 'No controllers configured',
        'add_your_first': 'Add your first controller above',

        # Settings page - WiFi
        'wifi_settings': 'WiFi Settings',
        'current_network': 'Current Network',
        'not_connected': 'Not Connected',
        'wifi_network': 'WiFi Network',
        'wifi_password': 'Password',
        'connect': 'Connect',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Maintenance Actions',
        'actions_hint': 'One action per line. These appear in the quick-log dropdown.',
        'save_actions': 'Save Actions',

        # Settings page - Data Upload
        'data_upload': 'Data Upload',
        'upload_interval': 'Upload Interval',
        'minutes': 'minutes',

        # Settings page - System
        'system_settings': 'System Settings',
        'software_version': 'Software Version',
        'check_updates': 'Check for Updates',
        'screen_rotation': 'Screen Rotation',
        'rotate_screen': 'Rotate Screen',
        'reboot_device': 'Reboot Device',
        'reboot': 'Reboot',

        # Settings page - Additional sections
        'change_network': 'Change Network',
        'ethernet_network': 'Ethernet Network',
        'rs485_water_tester': 'RS485 Water Tester',
        'quick_log_actions': 'Quick Log Actions',
        'scan': 'Scan',
        'disconnect': 'Disconnect',
        'manual_entry': 'Manual Entry',
        'hidden_networks': 'Hidden Networks',
        'auto_update': 'Auto-Update',
        'appearance': 'Appearance',
        'theme': 'Theme',
        'storage': 'Storage',
        'external_storage': 'External Storage',
        'protected_settings': 'Protected Settings',
        'remote_access': 'Remote Access (SSH)',
        'device_identity': 'Device Identity',
        'danger_zone': 'Danger Zone',
        'factory_reset': 'Factory Reset',
        'setup_wizard': 'Setup Wizard',

        # Common
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'back': 'Back',
        'loading': 'Loading...',
        'error': 'Error',
        'success': 'Success',
        'warning': 'Warning',
        'unknown': 'Unknown',
    },

    'fr': {
        # Settings page - Headers
        'settings': 'Paramètres',
        'quick_connect': 'Connexion Rapide',
        'connection_details': 'Détails de Connexion',
        'ip_address': 'Adresse IP',
        'hostname': 'Nom d\'hôte',
        'save': 'Enregistrer',
        'language': 'Langue',

        # Settings page - Controllers
        'controllers': 'Contrôleurs',
        'add_controller': 'Ajouter un Contrôleur',
        'controller_name': 'Nom du Contrôleur',
        'controller_ip': 'Adresse IP',
        'controller_port': 'Port',
        'pool_volume': 'Volume de la Piscine (litres)',
        'enabled': 'Activé',
        'disabled': 'Désactivé',
        'delete': 'Supprimer',
        'no_controllers': 'Aucun contrôleur configuré',
        'add_your_first': 'Ajoutez votre premier contrôleur ci-dessus',

        # Settings page - WiFi
        'wifi_settings': 'Paramètres WiFi',
        'current_network': 'Réseau Actuel',
        'not_connected': 'Non Connecté',
        'wifi_network': 'Réseau WiFi',
        'wifi_password': 'Mot de passe',
        'connect': 'Connecter',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Actions de Maintenance',
        'actions_hint': 'Une action par ligne. Elles apparaissent dans le menu déroulant du journal rapide.',
        'save_actions': 'Enregistrer les Actions',

        # Settings page - Data Upload
        'data_upload': 'Téléchargement des Données',
        'upload_interval': 'Intervalle de Téléchargement',
        'minutes': 'minutes',

        # Settings page - System
        'system_settings': 'Paramètres Système',
        'software_version': 'Version du Logiciel',
        'check_updates': 'Vérifier les Mises à Jour',
        'screen_rotation': 'Rotation de l\'Écran',
        'rotate_screen': 'Rotation de l\'Écran',
        'reboot_device': 'Redémarrer l\'Appareil',
        'reboot': 'Redémarrer',

        # Settings page - Additional sections
        'change_network': 'Changer de Réseau',
        'ethernet_network': 'Réseau Ethernet',
        'rs485_water_tester': 'Testeur d\'Eau RS485',
        'quick_log_actions': 'Actions Rapides',
        'scan': 'Scanner',
        'disconnect': 'Déconnecter',
        'manual_entry': 'Saisie Manuelle',
        'hidden_networks': 'Réseaux Cachés',
        'auto_update': 'Mise à Jour Auto',
        'appearance': 'Apparence',
        'theme': 'Thème',
        'storage': 'Stockage',
        'external_storage': 'Stockage Externe',
        'protected_settings': 'Paramètres Protégés',
        'remote_access': 'Accès Distant (SSH)',
        'device_identity': 'Identité de l\'Appareil',
        'danger_zone': 'Zone Dangereuse',
        'factory_reset': 'Réinitialisation Usine',
        'setup_wizard': 'Assistant de Configuration',

        # Common
        'cancel': 'Annuler',
        'confirm': 'Confirmer',
        'back': 'Retour',
        'loading': 'Chargement...',
        'error': 'Erreur',
        'success': 'Succès',
        'warning': 'Avertissement',
        'unknown': 'Inconnu',
    },

    'es': {
        # Settings page - Headers
        'settings': 'Configuración',
        'quick_connect': 'Conexión Rápida',
        'connection_details': 'Detalles de Conexión',
        'ip_address': 'Dirección IP',
        'hostname': 'Nombre de Host',
        'save': 'Guardar',
        'language': 'Idioma',

        # Settings page - Controllers
        'controllers': 'Controladores',
        'add_controller': 'Añadir Controlador',
        'controller_name': 'Nombre del Controlador',
        'controller_ip': 'Dirección IP',
        'controller_port': 'Puerto',
        'pool_volume': 'Volumen de la Piscina (litros)',
        'enabled': 'Habilitado',
        'disabled': 'Deshabilitado',
        'delete': 'Eliminar',
        'no_controllers': 'No hay controladores configurados',
        'add_your_first': 'Añade tu primer controlador arriba',

        # Settings page - WiFi
        'wifi_settings': 'Configuración WiFi',
        'current_network': 'Red Actual',
        'not_connected': 'No Conectado',
        'wifi_network': 'Red WiFi',
        'wifi_password': 'Contraseña',
        'connect': 'Conectar',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Acciones de Mantenimiento',
        'actions_hint': 'Una acción por línea. Aparecen en el menú desplegable del registro rápido.',
        'save_actions': 'Guardar Acciones',

        # Settings page - Data Upload
        'data_upload': 'Carga de Datos',
        'upload_interval': 'Intervalo de Carga',
        'minutes': 'minutos',

        # Settings page - System
        'system_settings': 'Configuración del Sistema',
        'software_version': 'Versión del Software',
        'check_updates': 'Buscar Actualizaciones',
        'screen_rotation': 'Rotación de Pantalla',
        'rotate_screen': 'Rotar Pantalla',
        'reboot_device': 'Reiniciar Dispositivo',
        'reboot': 'Reiniciar',

        # Settings page - Additional sections
        'change_network': 'Cambiar Red',
        'ethernet_network': 'Red Ethernet',
        'rs485_water_tester': 'Probador de Agua RS485',
        'quick_log_actions': 'Acciones Rápidas',
        'scan': 'Escanear',
        'disconnect': 'Desconectar',
        'manual_entry': 'Entrada Manual',
        'hidden_networks': 'Redes Ocultas',
        'auto_update': 'Actualización Automática',
        'appearance': 'Apariencia',
        'theme': 'Tema',
        'storage': 'Almacenamiento',
        'external_storage': 'Almacenamiento Externo',
        'protected_settings': 'Configuración Protegida',
        'remote_access': 'Acceso Remoto (SSH)',
        'device_identity': 'Identidad del Dispositivo',
        'danger_zone': 'Zona de Peligro',
        'factory_reset': 'Restablecer de Fábrica',
        'setup_wizard': 'Asistente de Configuración',

        # Common
        'cancel': 'Cancelar',
        'confirm': 'Confirmar',
        'back': 'Volver',
        'loading': 'Cargando...',
        'error': 'Error',
        'success': 'Éxito',
        'warning': 'Advertencia',
        'unknown': 'Desconocido',
    },

    'de': {
        # Settings page - Headers
        'settings': 'Einstellungen',
        'quick_connect': 'Schnellverbindung',
        'connection_details': 'Verbindungsdetails',
        'ip_address': 'IP-Adresse',
        'hostname': 'Hostname',
        'save': 'Speichern',
        'language': 'Sprache',

        # Settings page - Controllers
        'controllers': 'Steuerungen',
        'add_controller': 'Steuerung Hinzufügen',
        'controller_name': 'Steuerungsname',
        'controller_ip': 'IP-Adresse',
        'controller_port': 'Port',
        'pool_volume': 'Poolvolumen (Liter)',
        'enabled': 'Aktiviert',
        'disabled': 'Deaktiviert',
        'delete': 'Löschen',
        'no_controllers': 'Keine Steuerungen konfiguriert',
        'add_your_first': 'Fügen Sie oben Ihre erste Steuerung hinzu',

        # Settings page - WiFi
        'wifi_settings': 'WLAN-Einstellungen',
        'current_network': 'Aktuelles Netzwerk',
        'not_connected': 'Nicht Verbunden',
        'wifi_network': 'WLAN-Netzwerk',
        'wifi_password': 'Passwort',
        'connect': 'Verbinden',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Wartungsaktionen',
        'actions_hint': 'Eine Aktion pro Zeile. Diese erscheinen im Schnellprotokoll-Dropdown.',
        'save_actions': 'Aktionen Speichern',

        # Settings page - Data Upload
        'data_upload': 'Daten-Upload',
        'upload_interval': 'Upload-Intervall',
        'minutes': 'Minuten',

        # Settings page - System
        'system_settings': 'Systemeinstellungen',
        'software_version': 'Softwareversion',
        'check_updates': 'Nach Updates Suchen',
        'screen_rotation': 'Bildschirmdrehung',
        'rotate_screen': 'Bildschirm Drehen',
        'reboot_device': 'Gerät Neustarten',
        'reboot': 'Neustart',

        # Settings page - Additional sections
        'change_network': 'Netzwerk Wechseln',
        'ethernet_network': 'Ethernet-Netzwerk',
        'rs485_water_tester': 'RS485-Wassertester',
        'quick_log_actions': 'Schnellprotokoll-Aktionen',
        'scan': 'Scannen',
        'disconnect': 'Trennen',
        'manual_entry': 'Manuelle Eingabe',
        'hidden_networks': 'Versteckte Netzwerke',
        'auto_update': 'Automatische Aktualisierung',
        'appearance': 'Erscheinungsbild',
        'theme': 'Thema',
        'storage': 'Speicher',
        'external_storage': 'Externer Speicher',
        'protected_settings': 'Geschützte Einstellungen',
        'remote_access': 'Fernzugriff (SSH)',
        'device_identity': 'Geräteidentität',
        'danger_zone': 'Gefahrenzone',
        'factory_reset': 'Werkseinstellungen',
        'setup_wizard': 'Einrichtungsassistent',

        # Common
        'cancel': 'Abbrechen',
        'confirm': 'Bestätigen',
        'back': 'Zurück',
        'loading': 'Laden...',
        'error': 'Fehler',
        'success': 'Erfolg',
        'warning': 'Warnung',
        'unknown': 'Unbekannt',
    },

    'it': {
        # Settings page - Headers
        'settings': 'Impostazioni',
        'quick_connect': 'Connessione Rapida',
        'connection_details': 'Dettagli Connessione',
        'ip_address': 'Indirizzo IP',
        'hostname': 'Nome Host',
        'save': 'Salva',
        'language': 'Lingua',

        # Settings page - Controllers
        'controllers': 'Controllori',
        'add_controller': 'Aggiungi Controllore',
        'controller_name': 'Nome Controllore',
        'controller_ip': 'Indirizzo IP',
        'controller_port': 'Porta',
        'pool_volume': 'Volume Piscina (litri)',
        'enabled': 'Abilitato',
        'disabled': 'Disabilitato',
        'delete': 'Elimina',
        'no_controllers': 'Nessun controllore configurato',
        'add_your_first': 'Aggiungi il tuo primo controllore sopra',

        # Settings page - WiFi
        'wifi_settings': 'Impostazioni WiFi',
        'current_network': 'Rete Attuale',
        'not_connected': 'Non Connesso',
        'wifi_network': 'Rete WiFi',
        'wifi_password': 'Password',
        'connect': 'Connetti',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Azioni di Manutenzione',
        'actions_hint': 'Un\'azione per riga. Appaiono nel menu a discesa del registro rapido.',
        'save_actions': 'Salva Azioni',

        # Settings page - Data Upload
        'data_upload': 'Caricamento Dati',
        'upload_interval': 'Intervallo di Caricamento',
        'minutes': 'minuti',

        # Settings page - System
        'system_settings': 'Impostazioni di Sistema',
        'software_version': 'Versione Software',
        'check_updates': 'Controlla Aggiornamenti',
        'screen_rotation': 'Rotazione Schermo',
        'rotate_screen': 'Ruota Schermo',
        'reboot_device': 'Riavvia Dispositivo',
        'reboot': 'Riavvia',

        # Settings page - Additional sections
        'change_network': 'Cambia Rete',
        'ethernet_network': 'Rete Ethernet',
        'rs485_water_tester': 'Tester Acqua RS485',
        'quick_log_actions': 'Azioni Rapide',
        'scan': 'Scansiona',
        'disconnect': 'Disconnetti',
        'manual_entry': 'Inserimento Manuale',
        'hidden_networks': 'Reti Nascoste',
        'auto_update': 'Aggiornamento Automatico',
        'appearance': 'Aspetto',
        'theme': 'Tema',
        'storage': 'Archiviazione',
        'external_storage': 'Archiviazione Esterna',
        'protected_settings': 'Impostazioni Protette',
        'remote_access': 'Accesso Remoto (SSH)',
        'device_identity': 'Identità Dispositivo',
        'danger_zone': 'Zona Pericolosa',
        'factory_reset': 'Reset di Fabbrica',
        'setup_wizard': 'Procedura Guidata',

        # Common
        'cancel': 'Annulla',
        'confirm': 'Conferma',
        'back': 'Indietro',
        'loading': 'Caricamento...',
        'error': 'Errore',
        'success': 'Successo',
        'warning': 'Attenzione',
        'unknown': 'Sconosciuto',
    },

    'ru': {
        # Settings page - Headers
        'settings': 'Настройки',
        'quick_connect': 'Быстрое Подключение',
        'connection_details': 'Данные Подключения',
        'ip_address': 'IP-адрес',
        'hostname': 'Имя хоста',
        'save': 'Сохранить',
        'language': 'Язык',

        # Settings page - Controllers
        'controllers': 'Контроллеры',
        'add_controller': 'Добавить Контроллер',
        'controller_name': 'Название Контроллера',
        'controller_ip': 'IP-адрес',
        'controller_port': 'Порт',
        'pool_volume': 'Объём Бассейна (литры)',
        'enabled': 'Включен',
        'disabled': 'Отключен',
        'delete': 'Удалить',
        'no_controllers': 'Контроллеры не настроены',
        'add_your_first': 'Добавьте первый контроллер выше',

        # Settings page - WiFi
        'wifi_settings': 'Настройки WiFi',
        'current_network': 'Текущая Сеть',
        'not_connected': 'Не Подключено',
        'wifi_network': 'Сеть WiFi',
        'wifi_password': 'Пароль',
        'connect': 'Подключить',

        # Settings page - Maintenance Actions
        'maintenance_actions': 'Действия по Обслуживанию',
        'actions_hint': 'Одно действие на строку. Они появляются в выпадающем меню быстрого журнала.',
        'save_actions': 'Сохранить Действия',

        # Settings page - Data Upload
        'data_upload': 'Загрузка Данных',
        'upload_interval': 'Интервал Загрузки',
        'minutes': 'минут',

        # Settings page - System
        'system_settings': 'Системные Настройки',
        'software_version': 'Версия ПО',
        'check_updates': 'Проверить Обновления',
        'screen_rotation': 'Поворот Экрана',
        'rotate_screen': 'Повернуть Экран',
        'reboot_device': 'Перезагрузить Устройство',
        'reboot': 'Перезагрузка',

        # Settings page - Additional sections
        'change_network': 'Сменить Сеть',
        'ethernet_network': 'Сеть Ethernet',
        'rs485_water_tester': 'RS485 Тестер Воды',
        'quick_log_actions': 'Быстрые Действия',
        'scan': 'Сканировать',
        'disconnect': 'Отключить',
        'manual_entry': 'Ручной Ввод',
        'hidden_networks': 'Скрытые Сети',
        'auto_update': 'Автообновление',
        'appearance': 'Внешний Вид',
        'theme': 'Тема',
        'storage': 'Хранилище',
        'external_storage': 'Внешнее Хранилище',
        'protected_settings': 'Защищённые Настройки',
        'remote_access': 'Удалённый Доступ (SSH)',
        'device_identity': 'Идентификация Устройства',
        'danger_zone': 'Опасная Зона',
        'factory_reset': 'Сброс до Заводских',
        'setup_wizard': 'Мастер Настройки',

        # Common
        'cancel': 'Отмена',
        'confirm': 'Подтвердить',
        'back': 'Назад',
        'loading': 'Загрузка...',
        'error': 'Ошибка',
        'success': 'Успех',
        'warning': 'Предупреждение',
        'unknown': 'Неизвестно',
    },
}


def get_translator(lang_code: str):
    """Return a translation function for the given language."""
    lang = lang_code if lang_code in TRANSLATIONS else 'en'

    def translate(key: str) -> str:
        """Translate a key to the current language, falling back to English."""
        # Try current language first
        if key in TRANSLATIONS.get(lang, {}):
            return TRANSLATIONS[lang][key]
        # Fall back to English
        if key in TRANSLATIONS.get('en', {}):
            return TRANSLATIONS['en'][key]
        # Return key itself if not found
        return key

    return translate


def get_all_translations(lang_code: str) -> dict:
    """Get all translations for a language (with English fallback)."""
    lang = lang_code if lang_code in TRANSLATIONS else 'en'
    result = dict(TRANSLATIONS.get('en', {}))  # Start with English
    result.update(TRANSLATIONS.get(lang, {}))   # Override with target language
    return result
