from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
from typing import List

# FastAPI uygulamasını başlat
app = FastAPI()

# Bağlı olan tüm istemcileri (kullanıcıları) tutacağımız liste
active_connections: List[WebSocket] = []

# Sunucuya gelen her yeni bağlantı için bu kod çalışacak
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # 1. Bağlantı Kabul Ediliyor
    await websocket.accept()
    # Bağlantıyı aktif listeye ekle
    active_connections.append(websocket)

    # Yeni bir kullanıcının bağlandığını tüm aktif kullanıcılara duyur
    join_message = f"📢 Kullanıcı {username} sohbete katıldı!"
    await broadcast_message(join_message, sender_socket=websocket)

    try:
        # Kullanıcı bağlantısı açık kaldığı sürece mesajları dinle
        while True:
            # İstemciden (client) gelen mesajı al
            data = await websocket.receive_text()

            # Mesajı biçimlendir
            message = f"[{username}]: {data}"

            # Mesajı aktif olan diğer tüm kullanıcılara gönder
            await broadcast_message(message, sender_socket=websocket)

    except WebSocketDisconnect:
        # 2. Bağlantı Kesildi
        active_connections.remove(websocket)

        # Ayrılma mesajını duyur
        leave_message = f"❌ Kullanıcı {username} sohbetten ayrıldı."
        await broadcast_message(leave_message)

    except Exception as e:
        # Diğer hataları yakala
        print(f"Hata oluştu: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


# Gelen mesajı tüm aktif bağlantılara yayan fonksiyon
async def broadcast_message(message: str, sender_socket: WebSocket = None):
    # Tüm bağlantılar üzerinde döngü yap
    for connection in active_connections:
        try:
            # Eğer bir gönderici tanımlanmışsa, mesajı sadece diğerlerine gönder
            if connection != sender_socket:
                await connection.send_text(message)
        except Exception as e:
            # Eğer bir bağlantı hata verirse, onu listeden çıkar
            print(f"Mesaj gönderme hatası: {e}")
            if connection in active_connections:
                active_connections.remove(connection)