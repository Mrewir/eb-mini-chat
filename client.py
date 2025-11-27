import asyncio
import websockets
import sys

# Server adresi ve portu
URI = "ws://127.0.0.1:8000/ws/"

async def handle_send(websocket, username):
    """Kullanıcıdan input alır ve aynı WebSocket üzerinden mesajı gönderir."""
    while True:
        try:
            # Kullanıcıdan mesajı al (Bu, terminal inputunu bloklamaz)
            message = await asyncio.to_thread(input, f"{username}> ")
            
            if message.lower() == 'exit':
                print("Sohbetten ayrılıyorsunuz...")
                return # Bağlantıyı kapatmak için döngüden çık

            # Mesajı sunucuya gönder
            await websocket.send(message)

        except EOFError:
            print("Çıkış algılandı.")
            break
        except Exception as e:
            print(f" [HATA] Gönderme hatası: {e}")
            break

async def handle_receive(websocket):
    """Sürekli olarak sunucudan mesaj dinler."""
    while True:
        try:
            # Sunucudan gelen mesajı al
            message = await websocket.recv()
            
            # Mesajı ekrana temizce yazdır
            sys.stdout.write('\r' + ' ' * 80 + '\r') 
            print(message)
            sys.stdout.flush() # Ekranı hemen güncelle
            
        except websockets.exceptions.ConnectionClosed:
            print(" [BİLGİ] Sunucu bağlantıyı kapattı.")
            break
        except Exception as e:
            print(f" [HATA] Alma hatası: {e}")
            break

async def start_client(username):
    """Ana istemci bağlantısını kurar ve gönder/al işlevlerini eş zamanlı çalıştırır."""
    print(f"\n--- Emirhan Mini Chat Başlatıcı ---")
    print(f" [BAĞLANIYOR] Kullanıcı: {username}")
    
    try:
        # Tek bir kalıcı bağlantı kur
        async with websockets.connect(f"{URI}{username}") as websocket:
            print(" [BAĞLANDI] Sohbete hoş geldiniz. Çıkmak için 'exit' yazın.")
            
            # Gönderme ve alma işlevlerini eş zamanlı çalıştır
            receive_task = asyncio.create_task(handle_receive(websocket))
            send_task = asyncio.create_task(handle_send(websocket, username))

            # İki görevden biri bittiğinde diğerini iptal et ve çık
            done, pending = await asyncio.wait(
                [receive_task, send_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            for task in pending:
                task.cancel()
                
    except ConnectionRefusedError:
        print(" [HATA] Sunucu kapalı veya bağlantı reddedildi. Lütfen Uvicorn'un çalıştığından emin olun.")
    except Exception as e:
        print(f" [HATA] Genel bağlantı hatası: {e}")

# --- Başlatıcı ---
if __name__ == "__main__":
    # Kullanıcı adı sorma
    username = input("Kullanıcı Adınız: ").strip()
    if username:
        # asyncio.run() sadece main thread'de çalışabilir.
        # Bu, terminal inputu ile asenkronlüğü birleştirmek için gereklidir.
        try:
            asyncio.run(start_client(username))
        except RuntimeError:
            print("\n [HATA] Birden fazla asyncio run yapmayın. Lütfen client'i yeni terminalde çalıştırın.")
    else:
        print("Geçerli bir kullanıcı adı girmelisiniz.") 