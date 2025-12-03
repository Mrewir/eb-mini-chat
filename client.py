import asyncio
import websockets
import sys
import json
import requests
import threading
from datetime import datetime
from typing import List

# --- SES İMPORTLARI ---
import sounddevice as sd
import numpy as np

# --- AĞ AYARLARI ---
# Lütfen buradaki adresi, Railway'de canlı yayına almadan önce wss://... olarak değiştirin.
URI = "ws://127.0.0.1:8000/ws/" 
HISTORY_API = "http://127.0.0.1:8000/messages"

# --- SES AYARLARI ---
SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = 'int16'
CHUNK_SIZE = 1024

# --- SES KAYIT/OYNATMA FONKSİYONLARI ---

def record_audio_chunk():
    """Mikrofondan tek bir ses bloğu okur."""
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, blocksize=CHUNK_SIZE) as stream:
            audio_data, overflowed = stream.read(CHUNK_SIZE)
            if overflowed:
                pass
            return audio_data.tobytes()
            
    except Exception as e:
        # print(f" [HATA] Ses kaydı hatası: {e}") 
        return None

def play_audio_chunk(audio_bytes):
    """Gelen ikili ses bloğunu hoparlörden oynatır."""
    try:
        audio_data = np.frombuffer(audio_bytes, dtype=DTYPE)
        
        with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE) as stream:
            stream.write(audio_data)
            
    except Exception as e:
        print(f" [HATA] Ses oynatma hatası: {e}")

# --- TARİHÇE VE GÖRÜNTÜLEME FONKSİYONLARI ---

def fetch_history():
    """Senkron olarak mesaj geçmişini API'den çeker."""
    try:
        response = requests.get(HISTORY_API)
        response.raise_for_status() 
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
            ts = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] {msg['username']}: {msg['content']}")
        except:
            print(f"[ESKİ] {msg['username']}: {msg['content']}")
    print("--------------------------------")

# --- WEB SOCKET İŞLEYİCİ GÖREVLERİ ---

async def handle_text_send(websocket, username):
    """Kullanıcıdan yazılı mesaj inputu alır ve metin olarak gönderir."""
    while True:
        try:
            message = await asyncio.to_thread(input, f"{username}> ")
            
            if message.lower() == 'exit':
                return 

            await websocket.send(message)

        except EOFError:
            break
        except Exception as e:
            # print(f" [HATA] Metin gönderme hatası: {e}")
            break

async def handle_audio_send(websocket):
    """Mikrofondan sürekli ses okur ve ikili (binary) formatta gönderir."""
    while True:
        try:
            audio_chunk = await asyncio.to_thread(record_audio_chunk)
            
            if audio_chunk:
                await websocket.send(audio_chunk)
            
            await asyncio.sleep(0.005) 

        except Exception as e:
            # print(f" [HATA] Ses gönderme akışı kesildi: {e}")
            break

async def handle_receive(websocket, username):
    """Sunucudan gelen metin veya ikili (ses) verisini sürekli dinler."""
    while True:
        try:
            data = await websocket.receive()
            
            if data.get("text"):
                message = data["text"]
                sys.stdout.write('\r' + ' ' * 80 + '\r') 
                print(message)
                sys.stdout.write(f"\r{username}> ")
                sys.stdout.flush()

            elif data.get("bytes"):
                audio_chunk = data["bytes"]
                play_audio_chunk(audio_chunk)
            
        except websockets.exceptions.ConnectionClosed:
            print(" [BİLGİ] Sunucu bağlantıyı kapattı.")
            break
        except Exception as e:
            break

# --- ANA CLIENT BAĞLANTISI (Doğru Sırada Tanımlandı!) ---

async def start_client(username):
    """Ana istemci bağlantısını kurar ve gönder/al/ses işlevlerini eş zamanlı çalıştırır."""
    
    # 1. Mesaj Geçmişini Çek ve Göster
    history = await asyncio.to_thread(fetch_history)
    display_history(history)
    
    print(f"\n--- Emirhan Mini Chat Başlatıcı ---")
    
    try:
        # 2. WebSocket bağlantısını kur
        async with websockets.connect(f"{URI}{username}") as websocket:
            print(f" [BAĞLANDI] Sohbete hoş geldiniz. Çıkmak için 'exit' yazın.")
            
            # Gönderme, alma ve SES GÖNDERME işlevlerini eş zamanlı çalıştır
            receive_task = asyncio.create_task(handle_receive(websocket, username))
            send_task = asyncio.create_task(handle_text_send(websocket, username))
            audio_task = asyncio.create_task(handle_audio_send(websocket))

            # İki görevden biri bittiğinde diğerini iptal et ve çık
            done, pending = await asyncio.wait(
                [receive_task, send_task, audio_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            for task in pending:
                task.cancel()
                
    except ConnectionRefusedError:
        print(" [HATA] Sunucu kapalı veya bağlantı reddedildi. Lütfen Uvicorn'un çalıştığından emin olun.")
    except Exception as e:
        print(f" [HATA] Genel bağlantı hatası: {e}")

# --- BAŞLATICI (Çağıran Kısım) ---
if __name__ == "__main__":
    
    try:
        # requests, sounddevice kütüphaneleri yüklü mü kontrol et
        import requests
        import numpy
        import sounddevice
    except ImportError as e:
        print(f"\n [KRİTİK HATA] Sesli sohbet için bir kütüphane eksik: {e}")
        print(" Lütfen terminalde: pip install sounddevice numpy requests komutunu tekrar çalıştırın.")
        sys.exit(1)
        
    username = input("Kullanıcı Adınız: ").strip()
    if username:
        try:
            # start_client'ı çağır
            asyncio.run(start_client(username)) 
        except RuntimeError:
            pass 
    else:
        print("Geçerli bir kullanıcı adı girmelisiniz.")