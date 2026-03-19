<?php
// Update DB credentials
define('DB_HOST','localhost');
define('DB_USER','root');
define('DB_PASS','');
define('DB_NAME','ecn');

// Upload settings
define('UPLOAD_DIR', __DIR__ . '/uploads/');
define('UPLOAD_MAX', 2 * 1024 * 1024); // 2MB
$ALLOWED_MIME = ['image/jpeg','image/png','image/gif','image/webp'];

function db_connect(){
    $conn = new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);
    if($conn->connect_error) die('DB Connect Error: ' . $conn->connect_error);
    $conn->set_charset('utf8mb4');
    return $conn;
}

?>
