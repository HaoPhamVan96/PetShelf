# Pet Shelf 🐾

Ứng dụng Python desktop để quản lý và chạy pet từ spritesheet WebP, giao diện lấy cảm hứng từ danh sách Pets của Codex. Chạy trên macOS và Windows.

## Cấu trúc thư mục pet

Chọn **thư mục cha**. App quét các thư mục con trực tiếp:

```text
my-pets/
├── pet-1/
│   ├── pet.json
│   └── spritesheet.webp
└── pet-2/
    ├── pet.json
    └── spritesheet.webp
```

`pet.json` chuẩn v2:

```json
{
  "id": "pet-1",
  "displayName": "Pet One",
  "description": "A tiny desktop companion.",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

V2 yêu cầu spritesheet `1536x2288` (8 cột × 11 hàng, mỗi cell `192x208`). App cũng đọc pet v1 `1536x1872`.

## Chạy từ source

```bash
python -m venv .venv
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m pet_shelf
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pet_shelf
```

Trong app: **Open Pet Folder** → chọn `my-pets` → **Show** một hoặc nhiều pet. Giữ chuột trái và kéo pet sang trái/phải để phát đúng `running-left`/`running-right` từ JSON; thả chuột pet quay về `idle`. Chuột phải để đổi animation hoặc ẩn pet.

Khi minimize Pet Shelf hoặc chuyển sang ứng dụng khác, pet vẫn tiếp tục hiển thị và chạy animation độc lập trên desktop.

## Nút chức năng

- **Show / Hide** trên từng dòng: bật hoặc ẩn độc lập nhiều pet cùng lúc.
- **Edit**: mở Sprite & Action Editor để thay/xóa/export frame, import cả atlas, preview và cấu hình action.
- **Open Pet Folder**: chọn/thay thư mục cha chứa pet.
- **Refresh**: quét lại toàn bộ danh sách.
- **PetDex**: mở gallery PetDex, tìm kiếm và cài pet bằng CLI chính thức; app tự đồng bộ vào thư mục đang chọn và refresh danh sách.
- **Settings popup**: gom Follow Cursor, Speed slider, Pet size và Pet Outline vào một cửa sổ gọn.
- **Follow Cursor**: pet v2 dùng 16 ô look-direction để nhìn theo con trỏ, gồm cả trái/phải.
- **Speed slider**: kéo tốc độ toàn bộ animation từ `0.1×` đến `5×`; timing gốc vẫn lấy từ JSON.
- **Pet size**: phóng/thu đồng thời mọi pet từ `50%` đến `300%` mà vẫn giữ tỉ lệ khung hình.
- **Pet Outline**: viền mảnh 1px ôm theo alpha/silhouette; khi tắt, renderer trả nguyên frame không thêm viền Qt hay raster.

App nhớ thư mục, danh sách pet đang hiển thị, tốc độ, kích thước pet (50%–300%), follow-pointer và màu viền giữa các lần chạy.

Nếu `pet.json` có `interactions.hover`, `interactions.click` và các animation tùy chỉnh
trong `animations`, Pet Shelf sẽ phát đúng `sourceRow`, `frameCount`, `timingMs` và
chế độ `loop`/`once`. Click dạng `mode: "cycle"` sẽ luân phiên các animation được liệt kê.

Editor làm việc trên bản sao trong RAM. Chỉ khi bấm **Save**, app mới ghi lossless
spritesheet và `pet.json`; file gốc được sao lưu một lần dưới đuôi `.bak`.

## Tạo dữ liệu mẫu

```bash
python scripts/make_sample_pets.py
python -m pet_shelf
```

Sau đó chọn thư mục `sample-pets`.

## Build app độc lập

macOS (chạy trên máy macOS):

```bash
pip install -r requirements-dev.txt
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

Windows (chạy trên máy Windows):

```powershell
pip install -r requirements-dev.txt
.\scripts\build_windows.ps1
```

Hoặc build một-lệnh (tự tạo venv, cài dependency và đóng gói ZIP):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_release.ps1
```

Kết quả: `dist\PetShelf\PetShelf.exe` và `outputs\PetShelf-Windows-x64.zip`.

PyInstaller phải build trực tiếp trên từng hệ điều hành; không cross-compile `.app` sang `.exe`.
