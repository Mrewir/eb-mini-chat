import os 
from fastapi import FastAPI, WebSocket, Depends, HTTPException
from starlette.websockets import WebSocketDisconnect
from typing import List, Generator
from datetime import datetime

# --- SQLALCHEMY İMPORTLARI ---
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import select # Veri çekmek için eklendi

# Railway'den gelen veritabanı bağlantı URI'si
DATABASE_URL = os.environ.get("DATABASE_URL")

# Engine ve Base tanımlama
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Veritabanı Modeli: Mesajların tutulacağı tablo
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Veritabanını oluşturma veya mevcutsa kullanma
Base.metadata.create_all(bind=engine)

# Veritabanı oturumu almak için bir fonksiyon (FastAPI bağımlılığı)
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# --- MESAJ KAYDETME MANTIĞI ---

def save_message(db: Session, username: str, content: str):
    """Gelen mesajı veritabanına kaydeder."""
    db_message = Message(username=username, content=content)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message
    
# --- ANA FASTAPI UYGULAMASI ---
app = FastAPI()

# Bağlı olan tüm istemcileri (kullanıcıları) tutacağımız liste
active_connections: List[WebSocket] = []

# Gelen mesajı tüm aktif bağlantılara yayan fonksiyon
async def broadcast_message(message: str, sender_socket: WebSocket = None):
    # ... (Bu fonksiyonun içeriği değişmedi)
    for connection in active_connections:
        try:
            if connection != sender_socket:
                await connection.send_text(message)
        except Exception as e:
            print(f"Mesaj gönderme hatası: {e}")
            if connection in active_connections:
                active_connections.remove(connection)

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, db: Session = Depends(get_db)): # <-- Depends EKLENDİ
    # 1. Bağlantı Kabul Ediliyor
    await websocket.accept()
    active_connections.append(websocket)

    # Yeni bir kullanıcının bağlandığını tüm aktif kullanıcılara duyur
    join_message = f"📢 Kullanıcı {username} sohbete katıldı!"
    await broadcast_message(join_message, sender_socket=websocket)

    try:
        # Kullanıcı bağlantısı açık kaldığı sürece mesajları dinle
        while True:
            # İstemciden (client) gelen mesajı al
            data = await websocket.receive_text()

            # Yeni Mesajı Kaydet (YENİ EKLEME)
            save_message(db, username, data) 

            # Mesajı biçimlendir ve yay
            message = f"[{username}]: {data}"
            await broadcast_message(message, sender_socket=websocket)

    except WebSocketDisconnect:
        # 2. Bağlantı Kesildi
        active_connections.remove(websocket)
        leave_message = f"❌ Kullanıcı {username} sohbetten ayrıldı."
        await broadcast_message(leave_message)

    except Exception as e:
        # Diğer hataları yakala
        print(f"Hata oluştu: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

# --- Yeni Endpoint: Geçmiş Mesajları Çekme ---

@app.get("/messages", response_model=List[dict])
def get_messages(db: Session = Depends(get_db)):
    """Uygulama açıldığında geçmiş mesajları çekmek için yeni API."""
    
    messages = db.query(Message).order_by(Message.timestamp.asc()).all()
    
    # SQLAlchemy objelerini JSON'a çevirecek basit bir liste oluşturma
    message_list = [
        {
            "username": m.username, 
            "content": m.content, 
            "timestamp": m.timestamp.isoformat()
        } 
        for m in messages
    ]
    return message_list

# --- Buraya kadar. ---