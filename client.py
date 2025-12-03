import asyncio
from datetime import datetime
import websockets
import sys
import json
import requests # <-- Yeni: HTTP istekleri için eklendi

# Server adresi ve portu (Şu an RAILWAY'e hazır olmalı)
# Yerel test için: ws://127.0.0.1:8000/ws/ (Terminalde Uvicorn çalışırken)
# Canlı Railway adresi: wss://eb-mini-chat-production.up.railway.app/ws/
URI = "ws://127.0.0.1:8000/ws/" # <-- Yerel test için bu adresi kullanıyoruz

# API adresi (mesaj geçmişi için)
HISTORY_API = "http://127.0.0.1:8000/messages" # <-- Yerel test için bu adresi kullanıyoruz

async def handle_send(websocket, username):
    """Kullanıcıdan input alır ve aynı WebSocket üzerinden mesajı gönderir."""
    while True:
        try:
            message = await asyncio.to_thread(input, f"{username}> ")
            
            if message.lower() == 'exit':
                print("Sohbetten ayrılıyorsunuz...")
                return

            await websocket.send(message)

        except EOFError:
            break
        except Exception as e:
            print(f" [HATA] Gönderme hatası: {e}")
            break

async def handle_receive(websocket, username):
    """Sürekli olarak sunucudan mesaj dinler."""
    while True:
        try:
            message = await websocket.recv()
            
            # Mesajı ekrana temizce yazdır
            sys.stdout.write('\r' + ' ' * 80 + '\r') 
            print(message)
            sys.stdout.write(f"\r{username}> ")
            sys.stdout.flush()
            
        except websockets.exceptions.ConnectionClosed:
            print(" [BİLGİ] Sunucu bağlantıyı kapattı.")
            break
        except Exception as e:
            break

def fetch_history():
    """Senkron olarak mesaj geçmişini API'den çeker."""
    try:
        response = requests.get(HISTORY_API)
        response.raise_for_status() # HTTP hatalarını yakala
        return response.json()
    except requests.exceptions.ConnectionError:
        print("\n [HATA] Mesaj geçmişi çekilemedi: Sunucu (API) kapalı.")
        return []
    except Exception as e:
        print(f"\n [HATA] Geçmiş çekilirken hata: {e}")
        return []

def display_history(history):
    """Çekilen geçmişi terminalde görüntüler."""
    if not history:
        print(" [BİLGİ] Henüz kaydedilmiş mesaj bulunmamaktadır.")
        return

    print("\n--- MESAJ GEÇMİŞİ YÜKLENDİ ---")
    for msg in history:
        try:
            # Tarih formatını kısaltalım
            ts = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] {msg['username']}: {msg['content']}")
        except:
            print(f"[ESKİ] {msg['username']}: {msg['content']}")
    print("--------------------------------")


async def start_client(username):
    """Ana istemci bağlantısını kurar ve gönder/al işlevlerini eş zamanlı çalıştırır."""
    
    # 1. Mesaj Geçmişini Çek ve Göster (Senkron işlem)
    history = await asyncio.to_thread(fetch_history)
    display_history(history)
    
    print(f"\n--- Emirhan Mini Chat Başlatıcı ---")
    
    try:
        # 2. WebSocket bağlantısını kur
        async with websockets.connect(f"{URI}{username}") as websocket:
            print(f" [BAĞLANDI] Sohbete hoş geldiniz. Çıkmak için 'exit' yazın.")
            
            # Gönderme ve alma işlevlerini eş zamanlı çalıştır
            receive_task = asyncio.create_task(handle_receive(websocket, username))
            send_task = asyncio.create_task(handle_send(websocket, username))

            await asyncio.wait([receive_task, send_task], return_when=asyncio.FIRST_COMPLETED)
            
    except ConnectionRefusedError:
        print(" [HATA] Sunucu kapalı veya bağlantı reddedildi. Uvicorn'un çalıştığından emin olun.")
    except Exception as e:
        print(f" [HATA] Genel bağlantı hatası: {e}")

# --- Başlatıcı ---
if __name__ == "__main__":
    
    # Eksik kütüphaneleri kontrol edelim
    try:
        import requests
    except ImportError:
        print(" [HATA] Yeni özellik için 'requests' kütüphanesi eksik.")
        print(" Lütfen terminalde: pip install requests komutunu çalıştırın.")
        sys.exit(1)
    
    username = input("Kullanıcı Adınız: ").strip()
    if username:
        try:
            asyncio.run(start_client(username))
        except RuntimeError:
            print("\n [HATA] Birden fazla asyncio run yapmayın. Lütfen client'i yeni terminalde çalıştırın.")
    else:
        print("Geçerli bir kullanıcı adı girmelisiniz.")