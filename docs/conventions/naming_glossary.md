# Bảng tên gọi chung (Naming Glossary)

Mục đích: chỉ Tường Vi và AI của Tường Vi gọi đúng một tên cho mỗi trang, popup, phần giao diện và module. Khi báo lỗi, giao việc hay viết PR, hãy dùng tên ở cột **Tên gọi**.

## 1. Màn hình chính

| Tên gọi           | Các phần bên trong                                                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Landing**       | **Intro**: lời giới thiệu và nút. **Auth Panel**: form đăng nhập/đăng ký, kèm **Signup Extra** (chọn giọng, chủ đề).                                                                        |
| **Top Bar**       | **Nav** (Home / Script / Practice), **User Menu** (Profile, Audio settings, Permissions, Change password, Log out)                                                                          |
| **Home**          | **Latest Panel**: kết quả gần nhất và biểu đồ. **History**: danh sách các buổi tập.                                                                                                         |
| **Script Studio** | **Chat Feed**, **Composer** (ô nhập, chọn topic, đính PDF), **Script Bubble** (script trả về với các nút Practice / Copy / Download / Regenerate), **Refusal Bubble** (khi yêu cầu bị chặn) |
| **Practice**      | **Text Picker**, 3 tab: _Mine_ (script đã tạo), _Sample_ (mẫu), _Own_ (tự dán). **Voice Input**, 2 tab: _Record_ và _Upload_.                                                               |
| **Report**        | **Score Summary** (điểm overall và 4 thành phần), **Transcript View** (từng từ được tô màu), **Charts** (pitch, volume...), **Player** (phát lại ghi âm)                                    |
| **Profile**       | Thông tin cá nhân và baseline                                                                                                                                                               |

## 2. Popup (modal)

| Tên gọi                | Chức năng                               |
| ---------------------- | --------------------------------------- |
| **Profile Modal**      | Điền giới tính, tuổi, giọng, chủ đề     |
| **Consent Modal**      | Đồng ý ghi âm và lưu dữ liệu            |
| **Password Modal**     | Đổi mật khẩu                            |
| **Audio Settings**     | Chọn mic, thử mic                       |
| **Permissions**        | Quyền micro                             |
| **Safety Alert**       | Báo nội dung bị cấm                     |
| **Confirm Dialog**     | Xác nhận xoá hoặc thoát                 |
| **Evaluating Overlay** | Màn hình chờ chấm điểm                  |
| **Error Dialog**       | Báo lỗi                                 |
| **Baseline Gate**      | Ghi âm 30 giây giọng mẫu                |
| **Component Detail**   | Giải thích chi tiết một thành phần điểm |

## 3. Trang và phần sẽ thêm (dự kiến)

| Tên gọi             | Mô tả                                                    |
| ------------------- | -------------------------------------------------------- |
| **Guide**           | Trang hướng dẫn sử dụng và giải thích ý nghĩa các chỉ số |
| **Coach Notes**     | Phần LLM nhận xét và khuyên, nằm trong Report            |
| **Feedback Page**   | Trang để người dùng báo lỗi và góp ý                     |
| **Feedback Button** | Icon nhỏ trên mọi trang để báo lỗi tại chỗ               |

## 4. Backend

| Tên gọi               | Mô tả                                                                                   |
| --------------------- | --------------------------------------------------------------------------------------- |
| **Evaluate Pipeline** | Chấm điểm một bài nói: probe → decode → VAD → STT → align → scoring                     |
| **Baseline Pipeline** | Phân tích giọng mẫu: probe → decode → VAD → pause profile + F0                          |
| **Script Pipeline**   | Sinh script: parser → sanitizer → generator. Sắp thêm **Template Matcher** và **Guard** |
| **Template Matcher**  | Dò kho template, chọn bài phù hợp trước khi phải gọi LLM (sắp làm)                      |
| **Guard**             | Chặn prompt injection và nội dung độc hại (sắp làm)                                     |
| **Template Corpus**   | Kho bài mẫu: 6 chủ đề, mỗi chủ đề khoảng 100 bài                                        |

---

### Nhóm việc 1.4: Việc vặt và sửa lỗi

**Người làm:** chia đều, ưu tiên ai rảnh trước.

**Chủ đề và dữ liệu**

- Đổi `TEXT.topics` (politics, current_affairs, arts, charity) thành 6 chủ đề thật: Cinematography, Gender Studies, Information Technology, Learning Experiences, Sports, Wildlife.
- Sửa theo: `PREFILL.topics`, `SCRIPTS`, chip chủ đề ở Signup Extra và Profile Modal, dropdown topic trong Composer. Tốt nhất thêm `GET /api/topics` đọc từ `data/templates/`.

**Tắt chế độ demo**

- `SEED_SAMPLE_DATA`, `ALWAYS_ASK_BASELINE`, `PREFILL_ONBOARDING`, `?sim=1` cùng `simulate()` và `LEVELS`, dropdown `demoScenario`, nhãn "Sample data / Demo only".

**Lỗi backend**

- Path traversal: upload dùng `audio.filename` làm đường dẫn. Chỉ lấy đuôi file, đặt tên cố định.
- Chưa chặn dung lượng khi đang ghi file (100 MB chỉ kiểm tra sau khi ghi xong).
- STT gọi Deepgram/Gladia không có `timeout`.
- Gladia lỗi thì trả 500 không có thông báo; cần mã lỗi `stt_unavailable`.
- Endpoint `async` chạy việc nặng làm chặn server; đổi sang `def` thường hoặc `run_in_threadpool`.
- Validate `script` ở `/api/evaluate` (rỗng, quá dài) và độ dài audio ở `/api/baseline`.
- Server không báo khi thiếu API key lúc khởi động.

**Repo và tài liệu**

- README: sửa cách cài (`uv sync` / `pip install -e .`), STT là Deepgram/Gladia chứ không phải Groq Whisper, điền Usage / Team / License.
- `.env.example`: bỏ `GROQ_STT_MODEL`, ghi rõ biến nào bắt buộc.
- Xoá `demo_ui_static.html` (trùng lặp) hoặc ghi rõ công dụng.
- Sửa comment lỗi encoding trong `config.py`, xoá `[cite: 1]` trong `main.py`.
- Xoá `__pycache__` và `*.egg-info` khỏi repo.
- Thông báo trên UI ("PDF up to 25 MB, 3,000 words") phải khớp backend (backend còn giới hạn 10 trang).
- Test thật đoạn "UNTESTED trick" về thời lượng file webm (`demo_ui.html` khoảng dòng 3301).
- CI: chạy thêm test JS trong `tests/web/`.

---

## Phần 3. Phiên 2: sau tuần này

**Kết quả cần đạt cuối phiên:** người không rành chỉ số vẫn hiểu kết quả và biết cách cải thiện; nhóm có tài liệu kiến trúc và số liệu tối ưu để trình bày.

### Nhóm việc 2.1: Refactor UI

- Tách `demo_ui.html` (khoảng 3.600 dòng) thành các file HTML, CSS, JS và i18n riêng.
- Xem lại luồng người dùng từ Landing → Script Studio → Practice → Report, bớt bước thừa.
- Thông báo lỗi dễ hiểu, gắn với mã lỗi từ backend.
- **Sửa User Menu** thành 3 mục: **Profile**, **Settings**, **Log out**.
  - Bấm **Settings** mở **Settings Modal**, màn đầu tiên là danh sách 4 lựa chọn: **Permissions**, **Audio**, **Change password**, **Delete account**.
  - Chọn một mục thì nội dung trượt sang màn của mục đó **ngay trong cùng khung popup** (khung giữ nguyên kích thước và vị trí). Có nút **Back** để trượt về danh sách Settings.
  - Gộp các popup riêng hiện có (Permissions, Audio Settings, Password Modal) vào Settings Modal; thêm màn **Delete account** (có bước xác nhận, gọi API xoá tài khoản của nhóm việc 1.3).
  - Hiệu ứng chuyển màn tôn trọng cài đặt giảm chuyển động của hệ điều hành (`prefers-reduced-motion`).

### Nhóm việc 2.2: Guide

- **Tầng 1, "Cách dùng":** hướng dẫn từng bước cho từng màn hình.
- **Tầng 2, "Hiểu điểm số":** giải thích Accuracy, Fluency (WPM, hesitation, filler), Pronunciation (clarity, pitch), Semantic, kèm công thức và nguồn tham khảo.
- Mỗi chỉ số trong Report có nút "?" dẫn đúng mục trong Guide. Component Detail (`mPart`) đã làm được một phần.

### Nhóm việc 2.3: Coach Notes (LLM nhận xét)

- Chỉ gửi **JSON kết quả** cho LLM (số liệu, từ sai, pause, filler). Không gửi audio hay thông tin cá nhân.
- LLM trả JSON có cấu trúc: 3 điểm tốt, 3 điểm cần cải thiện, 1 bài tập gợi ý. Temperature thấp.
- Lưu vào bảng `coach_notes`, xem lại không phải gọi LLM lần nữa.
- LLM lỗi thì dùng nhận xét theo luật (dựa trên `warnings` đã có).

### Nhóm việc 2.4: Feedback

- **Feedback Page:** form báo lỗi và góp ý.
- **Feedback Button** trên mọi trang: mở popup nhỏ, tự điền `screen` (tên theo bảng tên gọi) và `context_id` (session hoặc script đang xem).
- Lưu vào bảng `feedback`; có cách để nhóm xem danh sách góp ý.

### Nhóm việc 2.5: Tối ưu hệ thống

- **Xử lý bất đồng bộ cho Evaluate:** `POST` trả `job_id`, client hỏi lại `GET /api/jobs/{id}`. Giao diện đã có sẵn kịch bản "queue".
- Nạp các model (VAD, sentence-transformers) một lần lúc khởi động.
- Cache: kết quả Template Matcher, Coach Notes.
- Đo và ghi số liệu: thời gian từng bước của Evaluate Pipeline, tỉ lệ khớp template, số lần gọi LLM và STT. Lưu vào một bảng trong PostgreSQL để thống kê, thay cho file log của phiên 1.

### Nhóm việc 2.6: Tập trung hằng số vào một file

**Thời điểm:** làm sau khi các nhánh của phiên 1 (gồm nhánh db-storage) đã merge vào `develop`, thành một issue riêng cho cả nhóm, chốt với Tech Lead trước. Làm sớm hơn sẽ đụng code của mọi nhóm và gây xung đột.

**Mục tiêu:** các giá trị nhóm muốn chỉnh nhanh (ví dụ số phiên giữ đầy đủ đang là 10, muốn thử 5 hoặc 20) nằm ở **một file duy nhất ở thư mục gốc repo**, không phải dò code để sửa rời rạc.

- File đề xuất: `app_constants.toml` ở thư mục gốc. Chia mục theo lĩnh vực (`[storage]`, `[audio]`, `[script]`, `[web]`...), mỗi hằng số có comment giải thích tác dụng và đơn vị.

  ```toml
  [storage]
  # Number of newest sessions kept with full result, audio and charts
  retention_full_sessions = 10
  # Lifetime of signed audio URLs (seconds)
  signed_url_ttl_s = 600

  [audio]
  # Pauses shorter than this are ignored (seconds)
  min_pause_s = 0.35
  ```

- **Cách các loại file đọc:**
  - Python: đọc bằng `tomllib` (có sẵn trong Python 3.12). `Settings` trong `src/app/config.py` lấy giá trị mặc định từ file này; `.env` vẫn ghi đè được (thứ tự ưu tiên: `.env` > file hằng số).
  - JavaScript trên trình duyệt: không đọc file trực tiếp; backend trả các giá trị UI cần qua một endpoint (ví dụ `GET /api/config`) hoặc chèn vào template.
  - Test: vẫn override như hiện tại (`monkeypatch.setattr(settings, ...)`).
- **Thứ được đưa vào:** giá trị muốn chỉnh nhanh, ví dụ số phiên giữ đầy đủ, TTL signed URL, bitrate Opus, `MIN_PAUSE_S`, `max_audio_seconds`, giới hạn phân trang.
- **Thứ không đưa vào:**
  - Bí mật và giá trị theo môi trường (`SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `APP_ENV`): vẫn ở `.env`, vì file hằng số được commit.
  - Hợp đồng đã cố định (`schema_version`, các `check` trong SQL như `duration_min in (5,10,15,20)`): SQL không đọc được file ngoài, đổi phải viết migration mới. Chỉ ghi chú trong file để mọi người biết.
  - Hằng số chỉ dùng nội bộ một hàm: để nguyên trong code, tránh file phình thành nơi chứa mọi thứ.
- Bước đầu: quét toàn repo, liệt kê các hằng số đang rải rác và đề xuất cách chia mục để nhóm duyệt.

### Nhóm việc 2.7: Tài liệu kiến trúc và báo cáo

- Viết `architecture.md`: sơ đồ tổng thể, ERD, sequence diagram cho 3 luồng chính (sinh script, chấm điểm, đăng nhập).
- Ghi lại các quyết định thiết kế (ADR): template trước LLM, server giữ baseline, fallback STT/LLM, kiến trúc 3 tầng.
- Bảng nguồn tham khảo cho các kỹ thuật và API dùng từ bên ngoài.
- Hướng dẫn chạy demo: chạy server trên một máy, mở trình duyệt ngay trên máy đó (`localhost:8000`). Trình duyệt chỉ cho dùng micro trên localhost hoặc HTTPS. Máy demo cần Internet (gọi Supabase, STT, LLM) và project Supabase phải đang chạy, không bị pause.
