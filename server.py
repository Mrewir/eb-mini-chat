import os 
from fastapi import FastAPI, WebSocket, Depends, HTTPException
from starlette.websockets import WebSocketDisconnect
from typing import List, Generator, Dict
from datetime import datetime
import asyncio # <-- Gerekliydi, eklenmiştir.

# --- SQLALCHEMY VE POSTGRESQL AYARLARI ---
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import select 

# Ortam değişkenlerinden veritabanı bağlantısını al (Railway veya yerel SQLite)
DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(
    DATABASE_URL, 
    # Cloud ortamları için bağlantı stabilitesi sağlar (ÇOK KRİTİK)
    pool_pre_ping=True, 
    # Yerel test için SQLite fix'i (bunun kalması önemli)
    connect_args={"check_same_thread": False} 
)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Veritabanı Modeli: Mesajların tutulacağı tablo
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# --- YARDIMCI VERİTABANI VE YAYIN FONKSİYONLARI ---

def save_message(db: Session, username: str, content: str):
    """Gelen metin mesajını veritabanına kaydeder."""
    db_message = Message(username=username, content=content)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

# Ses/Metin yayını için tüm aktif WebSocket bağlantıları
CONNECTIONS: Dict[str, WebSocket] = {} # <-- CONNECTIONS tanımlandı!

# Gelen ses verisini tüm aktif bağlantılara yayan fonksiyon
async def broadcast_audio(audio_chunk: bytes, sender: str):
    """Gelen ikili (binary) ses verisini, gönderen hariç tüm bağlı istemcilere yayınlar."""
    
    # asyncio.gather ile eş zamanlı olarak tüm istemcilere gönder
    await asyncio.gather(
        *[
            # Sadece gönderen olmayanlara ikili veriyi gönder
            websocket.send_bytes(audio_chunk)
            for user, websocket in CONNECTIONS.items()
            if user != sender
        ]
    )

# --- ANA FASTAPI UYGULAMASI ---
app = FastAPI()

# Gelen metin mesajını tüm aktif bağlantılara yayan fonksiyon (Sadece metin mesajları için)
async def broadcast_message(message: str, sender: str):
    # Sadece metin göndermek için kullanılır (Ses değil)
    for user, websocket in CONNECTIONS.items():
        try:
            if user != sender:
                await websocket.send_text(message)
        except Exception as e:
            print(f"Mesaj gönderme hatası: {e}")

# Geçmiş mesajları çekme API'si (Client bu adresi kullanacak)
@app.get("/messages", response_model=List[dict])
def get_messages(db: Session = Depends(get_db)):
    """Uygulama açıldığında geçmiş mesajları çekmek için yeni API."""
    
    messages = db.query(Message).order_by(Message.timestamp.asc()).limit(50).all() # Sadece son 50 mesajı çek
    
    message_list = [
        {
            "username": m.username, 
            "content": m.content, 
            "timestamp": m.timestamp.isoformat()
        } 
        for m in messages
    ]
    return message_list

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, db: Session = Depends(get_db)):
    """
    WebSocket bağlantısını yönetir ve gelen metin/ses verilerini işler.
    """
    await websocket.accept()
    
    # Bağlantıyı aktif listeye ekle
    CONNECTIONS[username] = websocket
    print(f"[BAĞLANTI] Kullanıcı '{username}' bağlandı. Toplam: {len(CONNECTIONS)}")
    
    try:
        while True:
            # Gelen veriyi bekler (FastAPI'da hem metin hem binary veri alabiliriz)
            data = await websocket.receive()
            
            if data.get("text"):
                # --- METİN MESAJI İŞLEME ---
                message = data["text"]
                
                # 1. Mesajı veritabanına kaydet
                save_message(db, username, message) 
                
                # 2. Mesajı biçimlendir ve yayınla
                full_message = f"[{username}]: {message}"
                await broadcast_message(full_message, username)
                
            elif data.get("bytes"):
                # --- İKİLİ (SES) VERİSİ İŞLEME ---
                audio_chunk = data["bytes"]
                
                # Ses verisini, gönderen kişi hariç diğer tüm kullanıcılara yayınla
                await broadcast_audio(audio_chunk, username)
                
            # Eğer 'close' mesajı gelirse bağlantıyı sonlandır
            if data.get("code") == 1000:
                break
                

    except WebSocketDisconnect:
        # 2. Bağlantı Kesildi
        pass # Son durum temizliği aşağıda yapılır
        
    except Exception as e:
        print(f"[HATA] {username} için beklenmedik hata: {e}")
        
    finally:
        # Bağlantı kesildiğinde veya hata oluştuğunda listeden çıkar
        if username in CONNECTIONS:
            del CONNECTIONS[username]
            print(f"[AYRILDI] Kullanıcı '{username}' ayrıldı. Kalan: {len(CONNECTIONS)}")