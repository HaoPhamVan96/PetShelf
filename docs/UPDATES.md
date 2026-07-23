# Cập nhật tự động cho Pet Shelf

## Cách phát hành bản mới

Cách nhanh trên Windows: double-click `release.bat`. Script sẽ tăng patch version tự động, hỏi xác nhận, commit toàn bộ thay đổi hiện có, push code, tạo tag và push tag.

Nếu không có thay đổi code, script vẫn tạo một commit chỉ chứa version bump — việc này cần thiết để bản build mới nhận đúng version.

Thủ công:

```bash
git add pyproject.toml pet_shelf/__init__.py
git commit -m "Release 1.0.1"
git push origin main
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions trong `.github/workflows/release.yml` sẽ tự động build Windows x64, macOS Intel (`macos-15-intel`) và macOS Apple Silicon (`macos-15`), rồi tạo GitHub Release.

## Cách app cập nhật

App kiểm tra GitHub Releases khoảng 1,8 giây sau khi mở, hoặc người dùng bấm **Check for Updates**. Khi có version mới, app tải đúng ZIP cho hệ điều hành, đóng Pet Shelf, thay bản cũ và mở lại bản mới.

## Điều kiện quan trọng

- Người dùng cài từ file ZIP/Release đã build, không chạy trực tiếp từ source Python.
- GitHub Release phải public.
- macOS chưa được ký/notarize Apple; lần đầu có thể cần chuột phải → **Open**.
- Nếu đổi repo, sửa `GITHUB_REPOSITORY` trong `pet_shelf/updater.py`.
