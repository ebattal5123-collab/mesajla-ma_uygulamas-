from flask import Flask, request, jsonify, session, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
import os
import uuid
import logging
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gizli-anahtar-2024')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    transport=['websocket', 'polling']
)

active_users = {}

# ADMIN E-POSTA - Bu e-postaya sahip kullanıcı admin olacak
ADMIN_EMAIL = "nesillericincesurellernice@gmail.com"

MONGODB_URI = os.environ.get(
    'MONGODB_URI',
    'mongodb+srv://Eymen:Eymen6969@cluster0.vqwhlrj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
)

try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    logger.info('✅ MongoDB bağlantısı başarılı!')
    
    db = client.chat_db
    messages_collection = db.messages
    rooms_collection = db.rooms
    users_collection = db.users
    friendships_collection = db.friendships
    friend_requests_collection = db.friend_requests
    
    # Index'leri oluştur
    try:
        messages_collection.create_index([("room", ASCENDING), ("timestamp", DESCENDING)])
        rooms_collection.create_index([("name", ASCENDING)], unique=True)
        users_collection.create_index([("username", ASCENDING)], unique=True)
        users_collection.create_index([("email", ASCENDING)], unique=True)
        users_collection.create_index([("user_id", ASCENDING)], unique=True)
        friendships_collection.create_index([("user_id", ASCENDING), ("friend_id", ASCENDING)], unique=True)
        friend_requests_collection.create_index([("from_id", ASCENDING), ("to_id", ASCENDING)], unique=True)
        logger.info('✅ Index\'ler oluşturuldu')
    except Exception as e:
        logger.info(f'ℹ️ Indexler zaten mevcut: {e}')
    
except Exception as e:
    logger.error(f'❌ MongoDB bağlantı hatası: {e}')
    exit(1)

def init_db():
    default_rooms = ['Genel', 'Teknoloji', 'Spor', 'Müzik', 'Oyun']
    for room_name in default_rooms:
        try:
            rooms_collection.insert_one({
                'name': room_name, 
                'created_at': datetime.now(), 
                'type': 'public',
                'created_by': 'system'
            })
            logger.info(f'✅ Oda oluşturuldu: {room_name}')
        except Exception as e:
            logger.info(f'ℹ️ Oda zaten mevcut: {room_name}')

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_user_id(email):
    """E-posta adresine göre benzersiz ve kalıcı bir ID oluştur"""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:8].upper()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grup Sohbet</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .main-container {
            width: 100%;
            max-width: 1200px;
            height: 90vh;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            display: none;
            overflow: hidden;
        }
        .main-container.active {
            display: flex;
        }
        .sidebar {
            width: 320px;
            background: #2c3e50;
            display: flex;
            flex-direction: column;
        }
        .sidebar-header {
            padding: 25px 20px;
            background: #1a252f;
            color: white;
            border-bottom: 2px solid #34495e;
        }
        .sidebar-header h2 {
            font-size: 20px;
            margin-bottom: 8px;
        }
        .user-info {
            font-size: 13px;
            opacity: 0.8;
            color: #ecf0f1;
            word-break: break-all;
        }
        .user-id-display {
            font-size: 11px;
            color: #95a5a6;
            margin-top: 5px;
            font-family: monospace;
            background: #34495e;
            padding: 5px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .user-id-display:hover {
            background: #667eea;
            color: white;
        }
        .admin-badge {
            background: #e74c3c;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: bold;
            margin-left: 5px;
        }
        .profile-btn, .inbox-btn {
            margin-top: 10px;
            padding: 8px 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
            width: 100%;
        }
        .profile-btn:hover, .inbox-btn:hover {
            background: #764ba2;
        }
        .inbox-btn {
            background: #e74c3c;
        }
        .inbox-btn:hover {
            background: #c0392b;
        }
        .sidebar-tabs {
            display: flex;
            background: #1a252f;
            border-bottom: 2px solid #34495e;
        }
        .sidebar-tab {
            flex: 1;
            padding: 12px;
            background: transparent;
            border: none;
            color: #ecf0f1;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.3s;
        }
        .sidebar-tab.active {
            background: #667eea;
            font-weight: bold;
        }
        .rooms-list, .friends-list {
            flex: 1;
            overflow-y: auto;
            padding: 15px 10px;
            display: none;
        }
        .rooms-list.active, .friends-list.active {
            display: block;
        }
        .room-item, .friend-item {
            padding: 15px;
            margin-bottom: 8px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 12px;
            color: #ecf0f1;
            position: relative;
        }
        .room-item:hover, .friend-item:hover {
            background: #34495e;
            transform: translateX(5px);
        }
        .room-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 600;
        }
        .room-item.private {
            border-left: 3px solid #f39c12;
        }
        .room-item.group {
            border-left: 3px solid #2ecc71;
        }
        .friend-item.online {
            border-left: 3px solid #2ecc71;
        }
        .friend-item.offline {
            border-left: 3px solid #95a5a6;
            opacity: 0.7;
        }
        .room-icon, .friend-icon {
            font-size: 22px;
        }
        .room-name, .friend-name {
            flex: 1;
            font-size: 15px;
        }
        .friend-status {
            font-size: 10px;
            color: #95a5a6;
        }
        .friend-item.online .friend-status {
            color: #2ecc71;
        }
        .delete-room-btn {
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 4px;
            width: 24px;
            height: 24px;
            cursor: pointer;
            font-size: 12px;
            display: none;
            align-items: center;
            justify-content: center;
        }
        .room-item:hover .delete-room-btn {
            display: flex;
        }
        .delete-room-btn:hover {
            background: #c0392b;
        }
        .new-room-section {
            padding: 15px;
            background: #1a252f;
            border-top: 2px solid #34495e;
        }
        .new-room-input, .private-room-input, .group-user-input, .friend-id-input {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            margin-bottom: 10px;
            font-size: 14px;
            background: #34495e;
            color: white;
        }
        .new-room-input::placeholder, .private-room-input::placeholder, 
        .group-user-input::placeholder, .friend-id-input::placeholder {
            color: #95a5a6;
        }
        .new-room-btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: transform 0.2s;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .new-room-btn:hover {
            transform: scale(1.02);
        }
        .private-btn {
            width: 100%;
            padding: 10px;
            background: #f39c12;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 12px;
            transition: transform 0.2s;
            margin-bottom: 8px;
        }
        .private-btn:hover {
            transform: scale(1.02);
        }
        .group-btn {
            width: 100%;
            padding: 10px;
            background: #2ecc71;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 12px;
            transition: transform 0.2s;
            margin-bottom: 8px;
        }
        .group-btn:hover {
            transform: scale(1.02);
        }
        .friend-btn {
            width: 100%;
            padding: 10px;
            background: #9b59b6;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 12px;
            transition: transform 0.2s;
        }
        .friend-btn:hover {
            transform: scale(1.02);
        }
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .chat-header h2 {
            font-size: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .logout-btn {
            padding: 10px 20px;
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.2s;
        }
        .logout-btn:hover {
            background: rgba(255,255,255,0.3);
        }
        .messages {
            flex: 1;
            padding: 25px;
            overflow-y: auto;
            background: #ecf0f1;
        }
        .message {
            margin-bottom: 20px;
            animation: slideIn 0.3s ease;
            display: flex;
            flex-direction: column;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message-content {
            background: white;
            padding: 14px 18px;
            border-radius: 18px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            max-width: 65%;
            word-wrap: break-word;
        }
        .message.own {
            align-items: flex-end;
        }
        .message.own .message-content {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .username {
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 6px;
            color: #667eea;
        }
        .message.own .username {
            color: white;
        }
        .message-text {
            font-size: 15px;
            line-height: 1.5;
            margin-bottom: 6px;
        }
        .timestamp {
            font-size: 11px;
            color: #7f8c8d;
            font-weight: 500;
        }
        .message.own .timestamp {
            color: rgba(255,255,255,0.8);
        }
        .input-area {
            padding: 20px 25px;
            background: white;
            border-top: 2px solid #e0e0e0;
            display: flex;
            gap: 12px;
        }
        input.message-input {
            flex: 1;
            padding: 14px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 15px;
            outline: none;
            transition: border 0.3s;
        }
        input.message-input:focus { 
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102,126,234,0.1);
        }
        button.send-btn {
            padding: 14px 35px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            transition: transform 0.2s;
            font-size: 15px;
        }
        button.send-btn:hover { 
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(102,126,234,0.4);
        }
        button.send-btn:active { transform: scale(0.95); }
        
        .auth-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.85);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .auth-modal.hidden {
            display: none;
        }
        .auth-box {
            background: white;
            padding: 45px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            min-width: 400px;
            max-width: 450px;
        }
        .auth-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .auth-header h2 {
            color: #667eea;
            font-size: 28px;
            margin-bottom: 10px;
        }
        .auth-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            background: #f0f0f0;
            padding: 5px;
            border-radius: 10px;
        }
        .auth-tab {
            flex: 1;
            padding: 12px;
            background: transparent;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            color: #666;
        }
        .auth-tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .auth-form {
            display: none;
        }
        .auth-form.active {
            display: block;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
            font-size: 14px;
        }
        .form-input {
            width: 100%;
            padding: 14px 18px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 15px;
            outline: none;
            transition: border 0.3s;
        }
        .form-input:focus {
            border-color: #667eea;
        }
        .auth-btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-weight: bold;
            font-size: 16px;
            transition: transform 0.2s;
        }
        .auth-btn:hover {
            transform: scale(1.02);
        }
        .error-message {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 14px;
            display: none;
        }
        .success-message {
            background: #efe;
            color: #3c3;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 14px;
            display: none;
        }
        
        .profile-modal, .inbox-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.85);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .profile-modal.active, .inbox-modal.active {
            display: flex;
        }
        .profile-box, .inbox-box {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            min-width: 450px;
            max-width: 500px;
            max-height: 80vh;
            overflow-y: auto;
        }
        .profile-header, .inbox-header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }
        .profile-avatar {
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 40px;
            color: white;
            margin: 0 auto 15px;
        }
        .profile-info {
            margin-bottom: 30px;
        }
        .profile-field {
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        .profile-field label {
            display: block;
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
            font-weight: 600;
        }
        .profile-field-value {
            font-size: 16px;
            color: #333;
            font-weight: 500;
        }
        .profile-actions {
            display: flex;
            gap: 10px;
        }
        .profile-close-btn {
            flex: 1;
            padding: 12px;
            background: #e0e0e0;
            color: #333;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.2s;
        }
        .profile-close-btn:hover {
            background: #d0d0d0;
        }
        
        .inbox-item {
            padding: 15px;
            margin-bottom: 10px;
            background: #f8f9fa;
            border-radius: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .inbox-user {
            font-weight: bold;
            color: #333;
        }
        .inbox-actions {
            display: flex;
            gap: 5px;
        }
        .inbox-accept-btn {
            padding: 8px 15px;
            background: #2ecc71;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
        }
        .inbox-reject-btn {
            padding: 8px 15px;
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
        }
        .empty-inbox {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }
        
        .group-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.85);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .group-modal.active {
            display: flex;
        }
        .group-box {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            min-width: 450px;
            max-width: 500px;
        }
        .group-header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }
        .group-header h2 {
            color: #2ecc71;
            font-size: 24px;
            margin-bottom: 10px;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }
        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
        @media (max-width: 768px) {
            .sidebar { width: 250px; }
            .main-container { height: 95vh; }
            .auth-box, .profile-box, .group-box, .inbox-box { min-width: 90%; }
        }
    </style>
</head>
<body>
    <div class="auth-modal" id="authModal">
        <div class="auth-box">
            <div class="auth-header">
                <h2>💬 Grup Sohbet</h2>
                <p style="color: #666; font-size: 14px;">Hesabınızla giriş yapın veya yeni hesap oluşturun</p>
            </div>
            
            <div class="auth-tabs">
                <button class="auth-tab active" id="loginTab">Giriş Yap</button>
                <button class="auth-tab" id="registerTab">Kayıt Ol</button>
            </div>
            
            <div id="errorMessage" class="error-message"></div>
            <div id="successMessage" class="success-message"></div>
            
            <div id="loginForm" class="auth-form active">
                <div class="form-group">
                    <label>Kullanıcı Adı</label>
                    <input type="text" class="form-input" id="loginUsername" placeholder="Kullanıcı adınız">
                </div>
                <div class="form-group">
                    <label>Şifre</label>
                    <input type="password" class="form-input" id="loginPassword" placeholder="Şifreniz">
                </div>
                <button class="auth-btn" id="loginBtn">Giriş Yap</button>
            </div>
            
            <div id="registerForm" class="auth-form">
                <div class="form-group">
                    <label>Kullanıcı Adı</label>
                    <input type="text" class="form-input" id="registerUsername" placeholder="Kullanıcı adınız" maxlength="20">
                </div>
                <div class="form-group">
                    <label>E-posta</label>
                    <input type="email" class="form-input" id="registerEmail" placeholder="E-posta adresiniz">
                </div>
                <div class="form-group">
                    <label>Şifre</label>
                    <input type="password" class="form-input" id="registerPassword" placeholder="Şifreniz (min. 6 karakter)">
                </div>
                <div class="form-group">
                    <label>Şifre Tekrar</label>
                    <input type="password" class="form-input" id="registerPasswordConfirm" placeholder="Şifrenizi tekrar girin">
                </div>
                <button class="auth-btn" id="registerBtn">Kayıt Ol</button>
            </div>
        </div>
    </div>
    
    <div class="profile-modal" id="profileModal">
        <div class="profile-box">
            <div class="profile-header">
                <div class="profile-avatar" id="profileAvatar">👤</div>
                <h2 id="profileUsername" style="color: #667eea; margin-bottom: 5px;"></h2>
                <p style="color: #999; font-size: 13px;" id="profileJoinDate"></p>
            </div>
            <div class="profile-info">
                <div class="profile-field">
                    <label>E-POSTA</label>
                    <div class="profile-field-value" id="profileEmail"></div>
                </div>
                <div class="profile-field">
                    <label>KULLANICI ID</label>
                    <div class="profile-field-value" id="profileUserId" style="font-family: monospace;"></div>
                </div>
                <div class="profile-field">
                    <label>YETKİ</label>
                    <div class="profile-field-value" id="profileRole"></div>
                </div>
            </div>
            <div class="profile-actions">
                <button class="profile-close-btn" id="closeProfileBtn">Kapat</button>
            </div>
        </div>
    </div>
    
    <div class="inbox-modal" id="inboxModal">
        <div class="inbox-box">
            <div class="inbox-header">
                <h2 style="color: #e74c3c;">📬 Gelen Kutusu</h2>
                <p style="color: #666; font-size: 14px;">Arkadaşlık istekleriniz</p>
            </div>
            <div id="inboxList">
                <div class="empty-inbox">
                    <div style="font-size: 48px; margin-bottom: 15px;">📭</div>
                    <p>Henüz arkadaşlık isteğiniz yok</p>
                </div>
            </div>
            <div class="profile-actions" style="margin-top: 20px;">
                <button class="profile-close-btn" id="closeInboxBtn">Kapat</button>
            </div>
        </div>
    </div>
    
    <div class="group-modal" id="groupModal">
        <div class="group-box">
            <div class="group-header">
                <h2>👥 Grup Oluştur</h2>
                <p style="color: #666; font-size: 14px;">En fazla 3 kişilik grup oluşturabilirsiniz</p>
            </div>
            
            <div id="groupErrorMessage" class="error-message"></div>
            <div id="groupSuccessMessage" class="success-message"></div>
            
            <div class="form-group">
                <label>Grup Adı</label>
                <input type="text" class="form-input" id="groupNameInput" placeholder="Grup adını girin" maxlength="30">
            </div>
            <div class="form-group">
                <label>1. Kullanıcı ID</label>
                <input type="text" class="form-input group-user-input" id="groupUser1Input" placeholder="İlk kullanıcı ID'si">
            </div>
            <div class="form-group">
                <label>2. Kullanıcı ID</label>
                <input type="text" class="form-input group-user-input" id="groupUser2Input" placeholder="İkinci kullanıcı ID'si">
            </div>
            
            <div class="profile-actions">
                <button class="profile-close-btn" id="closeGroupBtn">İptal</button>
                <button class="auth-btn" id="createGroupBtn" style="flex: 2;">Grup Oluştur</button>
            </div>
        </div>
    </div>
    
    <div class="main-container" id="mainContainer">
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>🏠 Sohbet</h2>
                <div class="user-info" id="userInfo"></div>
                <div class="user-id-display" id="userIdDisplay" title="Kliklayarak kopyala"></div>
                <button class="profile-btn" id="profileBtn">👤 Profilim</button>
                <button class="inbox-btn" id="inboxBtn">📬 Gelen Kutusu <span id="inboxBadge" style="display: none;">0</span></button>
            </div>
            
            <div class="sidebar-tabs">
                <button class="sidebar-tab active" id="roomsTab">Odalar</button>
                <button class="sidebar-tab" id="friendsTab">Arkadaşlar</button>
            </div>
            
            <div class="rooms-list active" id="roomsList"></div>
            <div class="friends-list" id="friendsList"></div>
            
            <div class="new-room-section">
                <input type="text" class="new-room-input" id="newRoomInput" placeholder="Yeni oda adı" maxlength="30">
                <button class="new-room-btn" id="createRoomBtn">➕ Oda Oluştur</button>
                
                <input type="text" class="private-room-input" id="privateUserIdInput" placeholder="Özel sohbet için ID girin" maxlength="50">
                <button class="private-btn" id="privateChatBtn">🔒 Özel Sohbet</button>
                
                <input type="text" class="friend-id-input" id="friendIdInput" placeholder="Arkadaş eklemek için ID girin" maxlength="50">
                <button class="friend-btn" id="friendBtn">👥 Arkadaş Ekle</button>
                
                <button class="group-btn" id="groupBtn">👥 Grup Oluştur</button>
            </div>
        </div>
        <div class="chat-container">
            <div class="chat-header">
                <h2 id="currentRoomName"><span class="room-icon">💬</span> Genel</h2>
                <button class="logout-btn" id="logoutBtn">Çıkış Yap</button>
            </div>
            <div class="messages" id="messages">
                <div class="empty-state">
                    <div class="empty-state-icon">💬</div>
                    <p>Henüz mesaj yok. İlk mesajı sen gönder!</p>
                </div>
            </div>
            <div class="input-area">
                <input type="text" class="message-input" id="messageInput" placeholder="Mesajınızı yazın..." maxlength="500">
                <button class="send-btn" id="sendBtn">Gönder</button>
            </div>
        </div>
    </div>
    
    <script>
        let socket;
        let username = '';
        let userId = '';
        let userEmail = '';
        let currentRoom = 'Genel';
        let isAdmin = false;
        
        // Event Listeners
        document.addEventListener('DOMContentLoaded', function() {
            // Auth tabs
            document.getElementById('loginTab').addEventListener('click', () => switchTab('login'));
            document.getElementById('registerTab').addEventListener('click', () => switchTab('register'));
            
            // Auth buttons
            document.getElementById('loginBtn').addEventListener('click', login);
            document.getElementById('registerBtn').addEventListener('click', register);
            
            // Profile buttons
            document.getElementById('profileBtn').addEventListener('click', showProfile);
            document.getElementById('closeProfileBtn').addEventListener('click', closeProfile);
            
            // Inbox buttons
            document.getElementById('inboxBtn').addEventListener('click', showInbox);
            document.getElementById('closeInboxBtn').addEventListener('click', closeInbox);
            
            // Group buttons
            document.getElementById('groupBtn').addEventListener('click', showGroupModal);
            document.getElementById('closeGroupBtn').addEventListener('click', closeGroupModal);
            document.getElementById('createGroupBtn').addEventListener('click', createGroup);
            
            // Chat buttons
            document.getElementById('createRoomBtn').addEventListener('click', createRoom);
            document.getElementById('privateChatBtn').addEventListener('click', startPrivateChat);
            document.getElementById('friendBtn').addEventListener('click', sendFriendRequest);
            document.getElementById('sendBtn').addEventListener('click', sendMessage);
            document.getElementById('logoutBtn').addEventListener('click', logout);
            
            // Sidebar tabs
            document.getElementById('roomsTab').addEventListener('click', () => switchSidebarTab('rooms'));
            document.getElementById('friendsTab').addEventListener('click', () => switchSidebarTab('friends'));
            
            // Enter key events
            document.getElementById('messageInput').addEventListener('keypress', e => {
                if (e.key === 'Enter') sendMessage();
            });
            
            document.getElementById('newRoomInput').addEventListener('keypress', e => {
                if (e.key === 'Enter') createRoom();
            });
            
            document.getElementById('privateUserIdInput').addEventListener('keypress', e => {
                if (e.key === 'Enter') startPrivateChat();
            });
            
            document.getElementById('friendIdInput').addEventListener('keypress', e => {
                if (e.key === 'Enter') sendFriendRequest();
            });
            
            document.getElementById('loginUsername').addEventListener('keypress', e => {
                if (e.key === 'Enter') login();
            });
            
            document.getElementById('loginPassword').addEventListener('keypress', e => {
                if (e.key === 'Enter') login();
            });
            
            document.getElementById('registerPasswordConfirm').addEventListener('keypress', e => {
                if (e.key === 'Enter') register();
            });
            
            document.getElementById('groupNameInput').addEventListener('keypress', e => {
                if (e.key === 'Enter') createGroup();
            });
            
            // Copy user ID
            document.getElementById('userIdDisplay').addEventListener('click', copyUserId);
        });
        
        function switchTab(tab) {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
            
            if (tab === 'login') {
                document.getElementById('loginTab').classList.add('active');
                document.getElementById('loginForm').classList.add('active');
            } else {
                document.getElementById('registerTab').classList.add('active');
                document.getElementById('registerForm').classList.add('active');
            }
            hideMessages();
        }
        
        function switchSidebarTab(tab) {
            document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.rooms-list, .friends-list').forEach(f => f.classList.remove('active'));
            
            if (tab === 'rooms') {
                document.getElementById('roomsTab').classList.add('active');
                document.getElementById('roomsList').classList.add('active');
            } else {
                document.getElementById('friendsTab').classList.add('active');
                document.getElementById('friendsList').classList.add('active');
                loadFriends();
            }
        }
        
        function hideMessages() {
            document.getElementById('errorMessage').style.display = 'none';
            document.getElementById('successMessage').style.display = 'none';
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('errorMessage');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            setTimeout(hideMessages, 5000);
        }
        
        function showSuccess(message) {
            const successDiv = document.getElementById('successMessage');
            successDiv.textContent = message;
            successDiv.style.display = 'block';
            setTimeout(hideMessages, 3000);
        }
        
        function showGroupError(message) {
            const errorDiv = document.getElementById('groupErrorMessage');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            setTimeout(() => errorDiv.style.display = 'none', 5000);
        }
        
        function showGroupSuccess(message) {
            const successDiv = document.getElementById('groupSuccessMessage');
            successDiv.textContent = message;
            successDiv.style.display = 'block';
            setTimeout(() => successDiv.style.display = 'none', 3000);
        }
        
        function register() {
            const user = document.getElementById('registerUsername').value.trim();
            const email = document.getElementById('registerEmail').value.trim();
            const password = document.getElementById('registerPassword').value;
            const passwordConfirm = document.getElementById('registerPasswordConfirm').value;
            
            if (!user || !email || !password) {
                showError('Tüm alanları doldurun!');
                return;
            }
            
            if (password.length < 6) {
                showError('Şifre en az 6 karakter olmalı!');
                return;
            }
            
            if (password !== passwordConfirm) {
                showError('Şifreler eşleşmiyor!');
                return;
            }
            
            const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
            if (!emailRegex.test(email)) {
                showError('Geçerli bir e-posta adresi girin!');
                return;
            }
            
            fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, email, password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showSuccess('✅ Kayıt başarılı! Giriş yapabilirsiniz.');
                    setTimeout(() => {
                        switchTab('login');
                        document.getElementById('loginUsername').value = user;
                    }, 1500);
                } else {
                    showError(data.message || 'Kayıt başarısız!');
                }
            })
            .catch(() => showError('Bir hata oluştu!'));
        }
        
        function login() {
            const user = document.getElementById('loginUsername').value.trim();
            const pass = document.getElementById('loginPassword').value;
            
            if (!user || !pass) {
                showError('Kullanıcı adı ve şifre girin!');
                return;
            }
            
            fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    username = data.username;
                    userEmail = data.email;
                    userId = data.user_id;
                    isAdmin = data.is_admin || false;
                    
                    document.getElementById('authModal').classList.add('hidden');
                    document.getElementById('mainContainer').classList.add('active');
                    
                    let userInfoText = '👤 ' + username;
                    if (isAdmin) {
                        userInfoText += ' <span class="admin-badge">ADMIN</span>';
                    }
                    document.getElementById('userInfo').innerHTML = userInfoText;
                    
                    document.getElementById('userIdDisplay').textContent = '🔑 ID: ' + userId;
                    initSocket();
                    loadRooms();
                    loadFriends();
                    checkFriendRequests();
                } else {
                    showError(data.message || 'Giriş başarısız!');
                }
            })
            .catch(() => showError('Bir hata oluştu!'));
        }
        
        function logout() {
            fetch('/api/logout', { method: 'POST' })
            .then(() => location.reload());
        }
        
        function showProfile() {
            document.getElementById('profileUsername').textContent = username;
            document.getElementById('profileEmail').textContent = userEmail;
            document.getElementById('profileUserId').textContent = userId;
            document.getElementById('profileAvatar').textContent = username.charAt(0).toUpperCase();
            
            let roleText = 'Kullanıcı';
            if (isAdmin) {
                roleText = '👑 Admin';
            }
            document.getElementById('profileRole').textContent = roleText;
            
            fetch('/api/profile')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const joinDate = new Date(data.created_at);
                    document.getElementById('profileJoinDate').textContent = 
                        'Üyelik: ' + joinDate.toLocaleDateString('tr-TR');
                }
            });
            
            document.getElementById('profileModal').classList.add('active');
        }
        
        function closeProfile() {
            document.getElementById('profileModal').classList.remove('active');
        }
        
        function showInbox() {
            loadFriendRequests();
            document.getElementById('inboxModal').classList.add('active');
        }
        
        function closeInbox() {
            document.getElementById('inboxModal').classList.remove('active');
        }
        
        function showGroupModal() {
            document.getElementById('groupModal').classList.add('active');
        }
        
        function closeGroupModal() {
            document.getElementById('groupModal').classList.remove('active');
            document.getElementById('groupNameInput').value = '';
            document.getElementById('groupUser1Input').value = '';
            document.getElementById('groupUser2Input').value = '';
            document.getElementById('groupErrorMessage').style.display = 'none';
            document.getElementById('groupSuccessMessage').style.display = 'none';
        }
        
        function createGroup() {
            const groupName = document.getElementById('groupNameInput').value.trim();
            const user1Id = document.getElementById('groupUser1Input').value.trim();
            const user2Id = document.getElementById('groupUser2Input').value.trim();
            
            if (!groupName) {
                showGroupError('Grup adı gerekli!');
                return;
            }
            
            if (!user1Id || !user2Id) {
                showGroupError('Her iki kullanıcı ID\\'sini de girin!');
                return;
            }
            
            if (user1Id === userId || user2Id === userId) {
                showGroupError('Kendi ID\\'nizi giremezsiniz!');
                return;
            }
            
            if (user1Id === user2Id) {
                showGroupError('Aynı kullanıcıyı iki kez ekleyemezsiniz!');
                return;
            }
            
            socket.emit('create_group', {
                group_name: groupName,
                user1_id: user1Id,
                user2_id: user2Id,
                creator_id: userId,
                creator_username: username
            });
        }
        
        function sendFriendRequest() {
            const friendId = document.getElementById('friendIdInput').value.trim();
            
            if (!friendId) {
                alert('Lütfen geçerli bir ID girin!');
                return;
            }
            
            if (friendId === userId) {
                alert('Kendinize arkadaşlık isteği gönderemezsiniz!');
                return;
            }
            
            socket.emit('send_friend_request', {
                from_id: userId,
                from_username: username,
                to_id: friendId
            });
            
            document.getElementById('friendIdInput').value = '';
        }
        
        function deleteRoom(roomName) {
            if (!confirm(`"${roomName}" odasını silmek istediğinizden emin misiniz?`)) {
                return;
            }
            
            socket.emit('delete_room', {
                room_name: roomName,
                user_id: userId
            });
        }
        
        function initSocket() {
            socket = io({
                transports: ['websocket', 'polling'],
                upgrade: true,
                rememberUpgrade: true,
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                reconnectionAttempts: 5
            });
            
            socket.on('connect', () => {
                console.log('✅ Socket bağlandı!');
                socket.emit('register_user', { 
                    username: username,
                    user_id: userId,
                    is_admin: isAdmin
                });
            });
            
            socket.on('user_registered', data => {
                console.log('✅ Kullanıcı socket\\'e kaydedildi');
            });
            
            socket.on('disconnect', () => console.log('❌ Socket bağlantısı kesildi'));
            
            socket.on('receive_message', data => {
                if (data.room === currentRoom) {
                    displayMessage(data.username, data.message, data.timestamp);
                }
            });
            
            socket.on('room_created', data => {
                addRoomToList(data.name);
            });
            
            socket.on('private_room_created', data => {
                addRoomToList(data.room, true);
                joinRoom(data.room);
            });
            
            socket.on('group_created', data => {
                addRoomToList(data.room, false, true);
                joinRoom(data.room);
                closeGroupModal();
                showGroupSuccess('✅ Grup başarıyla oluşturuldu!');
            });
            
            socket.on('group_creation_failed', data => {
                showGroupError(data.message);
            });
            
            socket.on('friend_request_received', data => {
                checkFriendRequests();
                if (document.getElementById('inboxModal').classList.contains('active')) {
                    loadFriendRequests();
                }
            });
            
            socket.on('friend_request_accepted', data => {
                loadFriends();
                showSuccess(`✅ ${data.friend_username} arkadaş oldu!`);
            });
            
            socket.on('friend_request_rejected', data => {
                showSuccess(`❌ ${data.friend_username} arkadaşlık isteğinizi reddetti.`);
            });
            
            socket.on('friend_added', data => {
                loadFriends();
                showSuccess(`✅ ${data.friend_username} arkadaş eklendi!`);
            });
            
            socket.on('room_deleted', data => {
                const roomItem = document.querySelector(`[data-room="${data.room_name}"]`);
                if (roomItem) {
                    roomItem.remove();
                }
                
                if (currentRoom === data.room_name) {
                    joinRoom('Genel');
                }
                
                showSuccess('✅ Oda başarıyla silindi!');
            });
            
            socket.on('room_delete_failed', data => {
                alert(data.message);
            });
            
            socket.on('error_message', data => alert(data.message));
        }
        
        function loadRooms() {
            fetch('/api/rooms?user_id=' + userId)
            .then(res => res.json())
            .then(rooms => {
                const roomsList = document.getElementById('roomsList');
                roomsList.innerHTML = '';
                rooms.forEach(room => {
                    const isPrivate = room.name.includes('_private_');
                    const isGroup = room.name.includes('_group_');
                    addRoomToList(room.name, isPrivate, isGroup);
                });
                setActiveRoom('Genel');
                joinRoom('Genel');
            });
        }
        
        function loadFriends() {
            fetch('/api/friends?user_id=' + userId)
            .then(res => res.json())
            .then(friends => {
                const friendsList = document.getElementById('friendsList');
                friendsList.innerHTML = '';
                
                if (friends.length === 0) {
                    friendsList.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👥</div><p>Henüz arkadaşınız yok</p></div>';
                    return;
                }
                
                friends.forEach(friend => {
                    const friendItem = document.createElement('div');
                    friendItem.className = 'friend-item ' + (friend.online ? 'online' : 'offline');
                    friendItem.setAttribute('data-friend-id', friend.user_id);
                    friendItem.onclick = () => startPrivateChatWithFriend(friend.user_id);
                    
                    friendItem.innerHTML = `
                        <span class="friend-icon">👤</span>
                        <div style="flex: 1;">
                            <div class="friend-name">${friend.username}</div>
                            <div class="friend-status">${friend.online ? 'Çevrimiçi' : 'Çevrimdışı'}</div>
                        </div>
                    `;
                    
                    friendsList.appendChild(friendItem);
                });
            });
        }
        
        function loadFriendRequests() {
            fetch('/api/friend_requests?user_id=' + userId)
            .then(res => res.json())
            .then(requests => {
                const inboxList = document.getElementById('inboxList');
                inboxList.innerHTML = '';
                
                if (requests.length === 0) {
                    inboxList.innerHTML = '<div class="empty-inbox"><div style="font-size: 48px; margin-bottom: 15px;">📭</div><p>Henüz arkadaşlık isteğiniz yok</p></div>';
                    return;
                }
                
                requests.forEach(request => {
                    const requestItem = document.createElement('div');
                    requestItem.className = 'inbox-item';
                    requestItem.innerHTML = `
                        <div class="inbox-user">${request.from_username}</div>
                        <div class="inbox-actions">
                            <button class="inbox-accept-btn" onclick="acceptFriendRequest('${request._id}', '${request.from_id}')">Kabul</button>
                            <button class="inbox-reject-btn" onclick="rejectFriendRequest('${request._id}', '${request.from_id}')">Red</button>
                        </div>
                    `;
                    inboxList.appendChild(requestItem);
                });
            });
        }
        
        function checkFriendRequests() {
            fetch('/api/friend_requests/count?user_id=' + userId)
            .then(res => res.json())
            .then(data => {
                const badge = document.getElementById('inboxBadge');
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline';
                } else {
                    badge.style.display = 'none';
                }
            });
        }
        
        function acceptFriendRequest(requestId, fromId) {
            socket.emit('accept_friend_request', {
                request_id: requestId,
                from_id: fromId,
                to_id: userId
            });
        }
        
        function rejectFriendRequest(requestId, fromId) {
            socket.emit('reject_friend_request', {
                request_id: requestId,
                from_id: fromId,
                to_id: userId
            });
        }
        
        function startPrivateChatWithFriend(friendId) {
            socket.emit('start_private_chat', {
                from_id: userId,
                to_id: friendId,
                username
            });
        }
        
        function addRoomToList(roomName, isPrivate = false, isGroup = false) {
            const roomsList = document.getElementById('roomsList');
            const existingRoom = document.querySelector(`[data-room="${roomName}"]`);
            if (existingRoom) return;
            
            const roomItem = document.createElement('div');
            roomItem.className = 'room-item' + (isPrivate ? ' private' : '') + (isGroup ? ' group' : '');
            roomItem.setAttribute('data-room', roomName);
            roomItem.onclick = () => joinRoom(roomName);
            
            const icons = {
                'Genel': '💬',
                'Teknoloji': '💻',
                'Spor': '⚽',
                'Müzik': '🎵',
                'Oyun': '🎮'
            };
            let icon = '📌';
            if (isPrivate) icon = '🔒';
            else if (isGroup) icon = '👥';
            else icon = icons[roomName] || '📌';
            
            // Grup odaları için sadece grup adını göster
            let displayName = roomName;
            if (isGroup) {
                displayName = roomName.split('_')[1]; // Grup adını al
            }
            
            let deleteButton = '';
            if (isAdmin && !isPrivate && !isGroup) {
                deleteButton = `<button class="delete-room-btn" onclick="event.stopPropagation(); deleteRoom('${roomName}')">×</button>`;
            }
            
            roomItem.innerHTML = `<span class="room-icon">${icon}</span><span class="room-name">${displayName}</span>${deleteButton}`;
            roomsList.appendChild(roomItem);
        }
        
        function setActiveRoom(roomName) {
            document.querySelectorAll('.room-item').forEach(item => {
                item.classList.toggle('active', item.getAttribute('data-room') === roomName);
            });
        }
        
        function joinRoom(roomName) {
            if (currentRoom === roomName) return;
            
            if (socket && currentRoom) {
                socket.emit('leave_room', { room: currentRoom, username });
            }
            
            currentRoom = roomName;
            
            if (socket) {
                socket.emit('join_room', { room: roomName, username });
            }
            
            const icons = {
                'Genel': '💬',
                'Teknoloji': '💻',
                'Spor': '⚽',
                'Müzik': '🎵',
                'Oyun': '🎮'
            };
            let icon = '📌';
            let displayName = roomName;
            
            if (roomName.includes('_private_')) {
                icon = '🔒';
            } else if (roomName.includes('_group_')) {
                icon = '👥';
                displayName = roomName.split('_')[1]; // Grup adını al
            } else {
                icon = icons[roomName] || '📌';
            }
            
            document.getElementById('currentRoomName').innerHTML = `<span class="room-icon">${icon}</span> ${displayName}`;
            setActiveRoom(roomName);
            loadMessages(roomName);
        }
        
        function loadMessages(roomName) {
            fetch(`/api/messages?room=${encodeURIComponent(roomName)}`)
            .then(res => res.json())
            .then(messages => {
                const messagesDiv = document.getElementById('messages');
                messagesDiv.innerHTML = '';
                
                if (messages.length === 0) {
                    let roomDisplayName = roomName;
                    if (roomName.includes('_group_')) {
                        roomDisplayName = roomName.split('_')[1];
                    }
                    messagesDiv.innerHTML = `<div class="empty-state"><div class="empty-state-icon">💬</div><p>${roomDisplayName} odasında henüz mesaj yok. İlk mesajı sen gönder!</p></div>`;
                } else {
                    messages.forEach(msg => displayMessage(msg.username, msg.message, msg.timestamp, true));
                }
                scrollToBottom();
            });
        }
        
        function displayMessage(user, message, timestamp, isHistory = false) {
            const messagesDiv = document.getElementById('messages');
            const emptyState = messagesDiv.querySelector('.empty-state');
            if (emptyState) emptyState.remove();
            
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message' + (user === username ? ' own' : '');
            
            messageDiv.innerHTML = `
                <div class="message-content">
                    <div class="username">${user}</div>
                    <div class="message-text">${message}</div>
                    <div class="timestamp">${timestamp}</div>
                </div>`;
            
            messagesDiv.appendChild(messageDiv);
            if (!isHistory) scrollToBottom();
        }
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (message && socket && socket.connected && currentRoom) {
                socket.emit('send_message', { username, message, room: currentRoom });
                input.value = '';
            }
        }
        
        function createRoom() {
            const input = document.getElementById('newRoomInput');
            const roomName = input.value.trim();
            
            if (roomName) {
                fetch('/api/create_room', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: roomName })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        input.value = '';
                        socket.emit('new_room', { name: roomName });
                        addRoomToList(roomName, false);
                        joinRoom(roomName);
                    } else {
                        alert(data.message || 'Oda oluşturulamadı!');
                    }
                });
            }
        }
        
        function startPrivateChat() {
            const input = document.getElementById('privateUserIdInput');
            const targetUserId = input.value.trim();
            
            if (!targetUserId) {
                alert('Lütfen geçerli bir ID girin!');
                return;
            }
            
            if (targetUserId === userId) {
                alert('Kendinizle özel sohbet yapamazsınız!');
                return;
            }
            
            socket.emit('start_private_chat', {
                from_id: userId,
                to_id: targetUserId,
                username
            });
            
            input.value = '';
        }
        
        function copyUserId() {
            navigator.clipboard.writeText(userId).then(() => {
                alert('ID kopyalandı: ' + userId);
            }).catch(() => {
                const textarea = document.createElement('textarea');
                textarea.value = userId;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                alert('ID kopyalandı: ' + userId);
            });
        }
        
        function scrollToBottom() {
            const messagesDiv = document.getElementById('messages');
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        // Global functions for inline event handlers
        window.acceptFriendRequest = acceptFriendRequest;
        window.rejectFriendRequest = rejectFriendRequest;
        window.deleteRoom = deleteRoom;
    </script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not username or not email or not password:
            return jsonify({'success': False, 'message': 'Tüm alanları doldurun!'})
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Şifre en az 6 karakter olmalı!'})
        
        existing_user = users_collection.find_one({'$or': [{'username': username}, {'email': email}]})
        if existing_user:
            if existing_user.get('username') == username:
                return jsonify({'success': False, 'message': 'Bu kullanıcı adı zaten kullanılıyor!'})
            else:
                return jsonify({'success': False, 'message': 'Bu e-posta adresi zaten kullanılıyor!'})
        
        # Kalıcı kullanıcı ID'si oluştur
        user_id = generate_user_id(email)
        
        # Admin kontrolü - belirtilen e-posta admin olacak
        is_admin = (email.lower() == ADMIN_EMAIL.lower())
        
        hashed_password = hash_password(password)
        user_doc = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'user_id': user_id,
            'is_admin': is_admin,
            'created_at': datetime.now()
        }
        
        users_collection.insert_one(user_doc)
        logger.info(f'✅ Yeni kullanıcı kaydedildi: {username}, ID: {user_id}, Admin: {is_admin}')
        
        return jsonify({'success': True, 'message': 'Kayıt başarılı!'})
    
    except Exception as e:
        logger.error(f'❌ Kayıt hatası: {e}')
        return jsonify({'success': False, 'message': 'Bir hata oluştu!'})

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Kullanıcı adı ve şifre girin!'})
        
        user = users_collection.find_one({'username': username})
        
        if not user:
            return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı!'})
        
        hashed_password = hash_password(password)
        if user['password'] != hashed_password:
            return jsonify({'success': False, 'message': 'Şifre hatalı!'})
        
        session['username'] = user['username']
        session['email'] = user['email']
        session['user_id'] = user['user_id']
        session['is_admin'] = user.get('is_admin', False)
        
        logger.info(f'✅ Kullanıcı giriş yaptı: {username}, ID: {user["user_id"]}, Admin: {user.get("is_admin", False)}')
        
        return jsonify({
            'success': True,
            'username': user['username'],
            'email': user['email'],
            'user_id': user['user_id'],
            'is_admin': user.get('is_admin', False)
        })
    
    except Exception as e:
        logger.error(f'❌ Giriş hatası: {e}')
        return jsonify({'success': False, 'message': 'Bir hata oluştu!'})

@app.route('/api/logout', methods=['POST'])
def logout_route():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/profile')
def get_profile():
    try:
        username = session.get('username')
        if not username:
            return jsonify({'success': False, 'message': 'Oturum bulunamadı!'})
        
        user = users_collection.find_one({'username': username})
        if not user:
            return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı!'})
        
        return jsonify({
            'success': True,
            'username': user['username'],
            'email': user['email'],
            'user_id': user['user_id'],
            'is_admin': user.get('is_admin', False),
            'created_at': user['created_at'].isoformat()
        })
    
    except Exception as e:
        logger.error(f'❌ Profil hatası: {e}')
        return jsonify({'success': False, 'message': 'Bir hata oluştu!'})

@app.route('/api/rooms')
def get_rooms():
    try:
        user_id = request.args.get('user_id')
        
        # Genel odaları getir
        public_rooms = list(rooms_collection.find(
            {'type': {'$ne': 'group'}}, 
            {'_id': 0, 'name': 1}
        ).sort('name', ASCENDING))
        
        # Kullanıcının üye olduğu grup odalarını getir
        user_groups = list(rooms_collection.find(
            {'type': 'group', 'members': user_id},
            {'_id': 0, 'name': 1}
        ).sort('name', ASCENDING))
        
        # Tüm odaları birleştir
        all_rooms = public_rooms + user_groups
        
        return jsonify(all_rooms)
    except Exception as e:
        logger.error(f'❌ Oda listesi hatası: {e}')
        return jsonify([])

@app.route('/api/friends')
def get_friends():
    try:
        user_id = request.args.get('user_id')
        
        # Arkadaşlıkları getir
        friendships = list(friendships_collection.find({
            '$or': [
                {'user_id': user_id},
                {'friend_id': user_id}
            ]
        }))
        
        friends = []
        for friendship in friendships:
            if friendship['user_id'] == user_id:
                friend_id = friendship['friend_id']
            else:
                friend_id = friendship['user_id']
            
            # Kullanıcı bilgilerini getir
            friend_user = users_collection.find_one({'user_id': friend_id})
            if friend_user:
                # Çevrimiçi durumunu kontrol et
                online = any(user_data['user_id'] == friend_id for user_data in active_users.values())
                
                friends.append({
                    'user_id': friend_id,
                    'username': friend_user['username'],
                    'online': online
                })
        
        return jsonify(friends)
    except Exception as e:
        logger.error(f'❌ Arkadaş listesi hatası: {e}')
        return jsonify([])

@app.route('/api/friend_requests')
def get_friend_requests():
    try:
        user_id = request.args.get('user_id')
        
        requests = list(friend_requests_collection.find({
            'to_id': user_id,
            'status': 'pending'
        }).sort('created_at', DESCENDING))
        
        # ObjectId'yi string'e çevir
        for req in requests:
            req['_id'] = str(req['_id'])
        
        return jsonify(requests)
    except Exception as e:
        logger.error(f'❌ Arkadaşlık istekleri hatası: {e}')
        return jsonify([])

@app.route('/api/friend_requests/count')
def get_friend_requests_count():
    try:
        user_id = request.args.get('user_id')
        
        count = friend_requests_collection.count_documents({
            'to_id': user_id,
            'status': 'pending'
        })
        
        return jsonify({'count': count})
    except Exception as e:
        logger.error(f'❌ Arkadaşlık istekleri sayısı hatası: {e}')
        return jsonify({'count': 0})

@app.route('/api/create_room', methods=['POST'])
def create_room():
    data = request.json
    room_name = data.get('name', '').strip()
    
    if not room_name:
        return jsonify({'success': False, 'message': 'Oda adı boş olamaz!'})
    
    try:
        rooms_collection.insert_one({
            'name': room_name, 
            'type': 'public',
            'created_at': datetime.now(),
            'created_by': session.get('user_id', 'unknown')
        })
        return jsonify({'success': True, 'name': room_name})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Bu oda zaten mevcut!'})

@app.route('/api/messages')
def get_messages():
    room = request.args.get('room', 'Genel')
    try:
        messages = list(messages_collection.find(
            {'room': room}, 
            {'_id': 0, 'username': 1, 'message': 1, 'timestamp': 1}
        ).sort('_id', ASCENDING).limit(100))
        
        logger.info(f'✅ Oda: {room}, Mesaj sayısı: {len(messages)}')
        return jsonify(messages)
    except Exception as e:
        logger.error(f'❌ Mesaj yükleme hatası: {e}')
        return jsonify([])

@socketio.on('register_user')
def handle_register_user(data):
    username = data.get('username', 'Anonim')
    user_id = data.get('user_id')
    is_admin = data.get('is_admin', False)
    
    active_users[request.sid] = {
        'username': username,
        'user_id': user_id,
        'is_admin': is_admin,
        'socket_id': request.sid
    }
    
    logger.info(f'✅ Kullanıcı kaydedildi - Adı: {username}, ID: {user_id}, Admin: {is_admin}, SID: {request.sid}')
    
    # Çevrimiçi arkadaşlara bildir
    notify_friends_online_status(user_id, True)
    
    emit('user_registered', {'user_id': user_id})

@socketio.on('send_message')
def handle_message(data):
    username = data.get('username', 'Anonim')
    message = data.get('message', '')
    room = data.get('room', 'Genel')
    timestamp = datetime.now().strftime('%H:%M')
    
    logger.info(f'📨 Mesaj alındı -> Kullanıcı: {username}, Oda: {room}, Mesaj: {message}')
    
    socketio.emit('receive_message', {
        'username': username,
        'message': message,
        'timestamp': timestamp,
        'room': room
    }, to=room)
    
    logger.info(f'📢 Mesaj {room} odasındaki herkese yayınlandı')
    
    try:
        is_private = '_private_' in room
        is_group = '_group_' in room
        messages_collection.insert_one({
            'username': username,
            'message': message,
            'timestamp': timestamp,
            'room': room,
            'private': is_private,
            'group': is_group,
            'created_at': datetime.now()
        })
        logger.info(f'💾 Mesaj MongoDB\'ye kaydedildi')
    except Exception as e:
        logger.error(f'❌ MongoDB kayıt hatası: {e}')

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room', 'Genel')
    username = data.get('username', 'Anonim')
    join_room(room)
    logger.info(f'✅ {username} (SID: {request.sid}) -> {room} odasına katıldı')
    
    if '_private_' not in room and '_group_' not in room:
        socketio.emit('receive_message', {
            'username': 'Sistem',
            'message': f'{username} odaya katıldı',
            'timestamp': datetime.now().strftime('%H:%M'),
            'room': room
        }, to=room)

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data.get('room')
    username = data.get('username', 'Anonim')
    leave_room(room)
    logger.info(f'❌ {username} {room} odasından ayrıldı')

@socketio.on('new_room')
def handle_new_room(data):
    emit('room_created', {'name': data['name']}, broadcast=True)

@socketio.on('start_private_chat')
def handle_start_private_chat(data):
    from_id = data.get('from_id')
    to_id = data.get('to_id')
    username = data.get('username')
    
    target_user = None
    target_socket_id = None
    
    for sid, user_data in active_users.items():
        if user_data['user_id'] == to_id:
            target_user = user_data
            target_socket_id = sid
            break
    
    if not target_user:
        emit('error_message', {
            'message': '❌ Kullanıcı çevrimiçi değil veya ID hatalı!'
        })
        logger.info(f'❌ Özel sohbet hatası: Hedef kullanıcı {to_id} bulunamadı')
        return
    
    private_room = f'_private_{sorted([from_id, to_id])[0]}_{sorted([from_id, to_id])[1]}'
    
    logger.info(f'🔒 Özel sohbet başlatılıyor: {username} ({from_id}) <-> {target_user["username"]} ({to_id})')
    logger.info(f'🔒 Oda adı: {private_room}')
    
    socketio.emit('private_room_created', {
        'room': private_room,
        'other_username': target_user['username'],
        'other_id': to_id
    }, to=request.sid)
    
    socketio.emit('private_room_created', {
        'room': private_room,
        'other_username': username,
        'other_id': from_id
    }, to=target_socket_id)
    
    logger.info(f'✅ Özel oda oluşturuldu: {private_room}')

@socketio.on('create_group')
def handle_create_group(data):
    group_name = data.get('group_name', '').strip()
    user1_id = data.get('user1_id', '').strip()
    user2_id = data.get('user2_id', '').strip()
    creator_id = data.get('creator_id')
    creator_username = data.get('creator_username')
    
    # Kullanıcıları kontrol et
    user1 = None
    user2 = None
    user1_socket = None
    user2_socket = None
    
    for sid, user_data in active_users.items():
        if user_data['user_id'] == user1_id:
            user1 = user_data
            user1_socket = sid
        if user_data['user_id'] == user2_id:
            user2 = user_data
            user2_socket = sid
    
    if not user1 or not user2:
        emit('group_creation_failed', {
            'message': '❌ Bir veya daha fazla kullanıcı çevrimiçi değil!'
        })
        return
    
    if user1_id == user2_id:
        emit('group_creation_failed', {
            'message': '❌ Aynı kullanıcıyı iki kez ekleyemezsiniz!'
        })
        return
    
    # Grup odası oluştur
    group_room = f'_group_{group_name}_{creator_id}_{user1_id}_{user2_id}'
    
    try:
        # Odayı veritabanına kaydet
        rooms_collection.insert_one({
            'name': group_room,
            'display_name': group_name,
            'type': 'group',
            'members': [creator_id, user1_id, user2_id],
            'created_by': creator_id,
            'created_at': datetime.now()
        })
        
        logger.info(f'👥 Grup oluşturuldu: {group_name} - Üyeler: {creator_username}, {user1["username"]}, {user2["username"]}')
        
        # Tüm kullanıcılara grup odasını bildir
        socketio.emit('group_created', {
            'room': group_room,
            'name': group_name
        }, to=request.sid)
        
        socketio.emit('group_created', {
            'room': group_room,
            'name': group_name
        }, to=user1_socket)
        
        socketio.emit('group_created', {
            'room': group_room,
            'name': group_name
        }, to=user2_socket)
        
    except Exception as e:
        logger.error(f'❌ Grup oluşturma hatası: {e}')
        emit('group_creation_failed', {
            'message': '❌ Grup oluşturulurken bir hata oluştu!'
        })

@socketio.on('send_friend_request')
def handle_send_friend_request(data):
    from_id = data.get('from_id')
    from_username = data.get('from_username')
    to_id = data.get('to_id')
    
    # Kullanıcı var mı kontrol et
    target_user = users_collection.find_one({'user_id': to_id})
    if not target_user:
        emit('error_message', {'message': '❌ Geçersiz kullanıcı ID!'})
        return
    
    # Zaten arkadaş mı kontrol et
    existing_friendship = friendships_collection.find_one({
        '$or': [
            {'user_id': from_id, 'friend_id': to_id},
            {'user_id': to_id, 'friend_id': from_id}
        ]
    })
    if existing_friendship:
        emit('error_message', {'message': '❌ Zaten arkadaşsınız!'})
        return
    
    # Bekleyen istek var mı kontrol et
    existing_request = friend_requests_collection.find_one({
        'from_id': from_id,
        'to_id': to_id,
        'status': 'pending'
    })
    if existing_request:
        emit('error_message', {'message': '❌ Zaten arkadaşlık isteği gönderdiniz!'})
        return
    
    # Arkadaşlık isteği oluştur
    friend_request = {
        'from_id': from_id,
        'from_username': from_username,
        'to_id': to_id,
        'to_username': target_user['username'],
        'status': 'pending',
        'created_at': datetime.now()
    }
    
    friend_requests_collection.insert_one(friend_request)
    
    logger.info(f'👥 Arkadaşlık isteği: {from_username} -> {target_user["username"]}')
    
    # Hedef kullanıcı çevrimiçi ise bildir
    target_socket_id = None
    for sid, user_data in active_users.items():
        if user_data['user_id'] == to_id:
            target_socket_id = sid
            break
    
    if target_socket_id:
        socketio.emit('friend_request_received', {
            'from_username': from_username,
            'from_id': from_id
        }, to=target_socket_id)
    
    emit('friend_request_sent', {
        'message': f'✅ Arkadaşlık isteği {target_user["username"]} kullanıcısına gönderildi!'
    })

@socketio.on('accept_friend_request')
def handle_accept_friend_request(data):
    request_id = data.get('request_id')
    from_id = data.get('from_id')
    to_id = data.get('to_id')
    
    # İsteği bul ve güncelle
    friend_request = friend_requests_collection.find_one({'_id': ObjectId(request_id)})
    if not friend_request:
        return
    
    friend_requests_collection.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {'status': 'accepted', 'responded_at': datetime.now()}}
    )
    
    # Arkadaşlık oluştur
    friendship = {
        'user_id': from_id,
        'friend_id': to_id,
        'created_at': datetime.now()
    }
    
    friendships_collection.insert_one(friendship)
    
    logger.info(f'✅ Arkadaşlık kabul edildi: {friend_request["from_username"]} <-> {friend_request["to_username"]}')
    
    # İstek gönderene bildir
    from_socket_id = None
    for sid, user_data in active_users.items():
        if user_data['user_id'] == from_id:
            from_socket_id = sid
            break
    
    if from_socket_id:
        socketio.emit('friend_request_accepted', {
            'friend_username': friend_request['to_username'],
            'friend_id': to_id
        }, to=from_socket_id)
    
    # İstek alana bildir
    to_socket_id = None
    for sid, user_data in active_users.items():
        if user_data['user_id'] == to_id:
            to_socket_id = sid
            break
    
    if to_socket_id:
        socketio.emit('friend_added', {
            'friend_username': friend_request['from_username'],
            'friend_id': from_id
        }, to=to_socket_id)

@socketio.on('reject_friend_request')
def handle_reject_friend_request(data):
    request_id = data.get('request_id')
    from_id = data.get('from_id')
    to_id = data.get('to_id')
    
    # İsteği bul ve güncelle
    friend_request = friend_requests_collection.find_one({'_id': ObjectId(request_id)})
    if not friend_request:
        return
    
    friend_requests_collection.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {'status': 'rejected', 'responded_at': datetime.now()}}
    )
    
    logger.info(f'❌ Arkadaşlık isteği reddedildi: {friend_request["from_username"]} -> {friend_request["to_username"]}')
    
    # İstek gönderene bildir
    from_socket_id = None
    for sid, user_data in active_users.items():
        if user_data['user_id'] == from_id:
            from_socket_id = sid
            break
    
    if from_socket_id:
        socketio.emit('friend_request_rejected', {
            'friend_username': friend_request['to_username']
        }, to=from_socket_id)

@socketio.on('delete_room')
def handle_delete_room(data):
    room_name = data.get('room_name')
    user_id = data.get('user_id')
    
    logger.info(f'🔧 Oda silme isteği: {room_name}, Kullanıcı: {user_id}')
    
    # Kullanıcı admin mi kontrol et - aktif kullanıcılardan kontrol et
    user_is_admin = False
    for sid, user_data in active_users.items():
        if user_data['user_id'] == user_id:
            user_is_admin = user_data.get('is_admin', False)
            break
    
    # Eğer aktif kullanıcılarda bulunamazsa, veritabanından kontrol et
    if not user_is_admin:
        user = users_collection.find_one({'user_id': user_id})
        user_is_admin = user.get('is_admin', False) if user else False
    
    logger.info(f'🔧 Kullanıcı admin mi: {user_is_admin}')
    
    if not user_is_admin:
        emit('room_delete_failed', {'message': '❌ Bu işlem için admin yetkisi gerekiyor!'})
        return
    
    # Sistem odalarını (varsayılan odalar) koru
    default_rooms = ['Genel', 'Teknoloji', 'Spor', 'Müzik', 'Oyun']
    if room_name in default_rooms:
        emit('room_delete_failed', {'message': '❌ Sistem odalarını silemezsiniz!'})
        return
    
    # Özel ve grup odalarını koru
    if '_private_' in room_name or '_group_' in room_name:
        emit('room_delete_failed', {'message': '❌ Özel ve grup odalarını silemezsiniz!'})
        return
    
    # Odayı sil
    result = rooms_collection.delete_one({'name': room_name, 'type': 'public'})
    
    if result.deleted_count > 0:
        # Odadaki mesajları da sil
        messages_collection.delete_many({'room': room_name})
        
        logger.info(f'✅ Admin tarafından oda silindi: {room_name}')
        emit('room_deleted', {'room_name': room_name}, broadcast=True)
    else:
        emit('room_delete_failed', {'message': '❌ Oda silinemedi veya zaten silinmiş!'})

def notify_friends_online_status(user_id, online):
    """Arkadaşlara çevrimiçi/çevrimdışı durumu bildir"""
    # Kullanıcının arkadaşlarını bul
    friendships = friendships_collection.find({
        '$or': [
            {'user_id': user_id},
            {'friend_id': user_id}
        ]
    })
    
    for friendship in friendships:
        if friendship['user_id'] == user_id:
            friend_id = friendship['friend_id']
        else:
            friend_id = friendship['user_id']
        
        # Arkadaş çevrimiçi ise bildir
        friend_socket_id = None
        for sid, user_data in active_users.items():
            if user_data['user_id'] == friend_id:
                friend_socket_id = sid
                break
        
        if friend_socket_id:
            socketio.emit('friend_status_changed', {
                'friend_id': user_id,
                'online': online
            }, to=friend_socket_id)

@socketio.on('connect')
def handle_connect():
    user_ip = request.remote_addr
    sid = request.sid
    logger.info(f'✅ Kullanıcı bağlandı - SID: {sid}, IP: {user_ip}')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in active_users:
        user_info = active_users[sid]
        logger.info(f'❌ Kullanıcı ayrıldı - Adı: {user_info["username"]}, ID: {user_info["user_id"]}, Admin: {user_info.get("is_admin", False)}, SID: {sid}')
        
        # Arkadaşlara çevrimdışı olduğunu bildir
        notify_friends_online_status(user_info['user_id'], False)
        
        del active_users[sid]
    else:
        logger.info(f'❌ Kullanıcı ayrıldı - SID: {sid}')

if __name__ == '__main__':
    print('\n' + '='*60)
    print('🚀 GRUP SOHBET SUNUCUSU BAŞLATILDI!')
    print('='*60)
    print('📍 Render\'da çalışıyor...')
    print('='*60)
    print('✨ Özellikler:')
    print('   • ✅ Kullanıcı Kayıt ve Giriş Sistemi')
    print('   • ✅ Güvenli Şifre Hash\'leme (SHA-256)')
    print('   • ✅ Kalıcı Kullanıcı ID\'leri')
    print('   • ✅ Oturum Yönetimi (Flask Session)')
    print('   • ✅ Kullanıcı Profil Sayfası')
    print('   • ✅ 👑 ADMIN SİSTEMİ (DÜZELTİLDİ)')
    print('   • ✅ Oda Silme Yetkisi (Admin)')
    print('   • ✅ 3 Kişilik Özel Grup Sistemi')
    print('   • ✅ Özel Sohbet Odaları')
    print('   • ✅ Sadece Grup Üyeleri Grupları Görür')
    print('   • ✅ ARKADAŞLIK SİSTEMİ')
    print('   • ✅ GELEN KUTUSU (Arkadaşlık İstekleri)')
    print('   • ✅ ÇEVRİMİÇİ/ÇEVRİMDIŞI DURUMU')
    print('   • MongoDB Atlas bağlantısı')
    print('   • 5 Varsayılan oda (Genel, Teknoloji, Spor, Müzik, Oyun)')
    print('   • Yeni oda oluşturma')
    print('   • Her odanın bağımsız mesaj sistemi')
    print('   • Gerçek zamanlı mesajlaşma')
    print('   • Her kullanıcıya benzersiz ve kalıcı ID verilir')
    print('   • Özel sohbet sistemi (sadece 2 kullanıcı görür)')
    print('   • Grup sohbet sistemi (sadece 3 kullanıcı görür)')
    print('   • Modern ve şık tasarım')
    print('='*60 + '\n')

    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )
