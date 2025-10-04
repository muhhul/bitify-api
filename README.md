# bitify-api

# 1. Nama dan Deskripsi Program
Bitify API adalah layanan backend yang menyediakan fungsionalitas untuk menyisipkan (embed) dan mengekstrak (extract) file rahasia dari file audio MP3 menggunakan teknik steganografi. Program ini menerapkan metode 

multiple-LSB dan mendukung enkripsi extended Vigenère cipher untuk meningkatkan keamanan data.

# 2. Kumpulan Teknologi (Tech Stack)
* Framework: FastAPI (Python)
* Server: Uvicorn
* Containerization: Docker
* Core Libraries:
  * NumPy untuk manipulasi data numerik.
  * FFmpeg untuk pemrosesan file audio.
  * Mutagen untuk menangani metadata ID3 pada file MP3.

# 3. Dependensi
Berikut adalah dependensi utama yang dibutuhkan oleh backend:
```
fastapi
uvicorn
python-multipart
numpy
mutagen
```

# 4. Tata Cara Menjalankan Program
### a. Build Docker Image

Pastikan Anda berada di direktori bitify-api, lalu jalankan perintah berikut:
```
docker build -t bitify-api .
```

### b. Menjalankan Docker Container

Setelah image berhasil dibuat, jalankan container dengan perintah berikut. Anda dapat menyesuaikan ALLOWED_ORIGINS sesuai dengan alamat frontend Anda.
```
docker run --name bitify-api -d -p 8000:8000 `
  -e ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000" `
  bitify-api
```