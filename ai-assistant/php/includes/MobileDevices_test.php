<?php
class MobileDevices {
    private $userId;
    public function __construct($userId) {
        $this->userId = $userId;
    }
    public function getDevices() {
        return array();
    }
}
