# Bảng tên gọi chung (Naming Glossary)

Mục đích: chỉ Tường Vi và AI của Tường Vi gọi đúng một tên cho mỗi trang, popup, phần giao diện và module. Khi báo lỗi, giao việc hay viết PR, hãy dùng tên ở cột **Tên gọi**.

## 1. Màn hình chính

| Tên gọi           | Các phần bên trong |
| ----------------- | ------------------ |
| **Landing**       | **Landing Stage** (khung trên cùng, có **Mic Scene**: hình micro và ánh sáng động). Trong Landing Stage là **Intro** (tiêu đề, nút **Get Started** và **Log in**) hoặc **Auth Panel** (nút Back, 2 tab _Log in_ / _Sign up_, form, kèm **Signup Extra**: tên hiển thị, giới tính, tuổi, giọng; cuối form Sign up là **Signup Consent** (checkbox đồng ý ghi âm, bắt buộc, chưa tick thì nút Create account khoá); dưới ô mật khẩu ở form Log in là **Forgot Password Link**). Auth Panel còn 2 bước thay chỗ form: **Code Step** ("Check your email", nhập mã 6 số, nút **Change Email** "Wrong email? Change it" quay về form đăng ký giữ nguyên các ô; mở từ Log in thì là "Back to Log in") và **Reset Step** ("Reset password": nhập email, rồi mã + mật khẩu mới + nhập lại). Bên dưới: **Sample Card** (đoạn transcript mẫu đã tô màu và 3 số WPM / pause / pitch) và **How It Works** (3 bước đánh số). |
| **Top Bar**       | **Brand** (logo, bấm về Home), **Nav** (Home / Script / Practice / Schedule), **Guest Buttons** (Log in, Sign up khi chưa đăng nhập), **User Button** (avatar + tên, mở **User Menu**: Profile, Settings, Log out) |
| **Home**          | **Home Hero** (lời chào, **Home Summary**, **Home CTA** là nút Practice gợi ý, **Hero Mic** là micro 3D xoay, nút **See More** cuộn xuống). **Today Panel** ("Today's practice", demo: **Streak Chip** số tuần liên tiếp có buổi done, "x/y done", **Today Carousel** gồm các **Practice Card** của mọi buổi hôm nay (giờ, **Card Tag** Length và Category kiểu GitHub (`cardTags`; màu `--tag-length`, `--tag-category`, Any xám), **Script Line** nghiêng (`cardScriptLine`: Free choice script / Saved script: … / AI generated script; ghi chú không còn trên thẻ), "Closes in …" xanh hoặc đỏ / "Starts in …", nút Check in hoặc View result; bấm thẻ mở Day Drawer), tối đa 3 thẻ và một phần thẻ thứ 4, mũi tên `<` `>` hai bên (ẩn khi hết thẻ), mờ hai mép, **Week Dots** Thứ 2–CN, **Motivation Line**). **Home Empty** (dòng báo khi chưa có buổi tập). **Progress** gồm **Latest Panel** (kết quả gần nhất) và 2 biểu đồ **Score Chart**, **Activity Chart**. **Details** gồm 3 biểu đồ **WPM Chart**, **Pitch Chart**, **Clarity Chart**. **History** (bảng các buổi tập, nút **Delete All**). |
| **Script Studio** | **Chat Feed** (bubble trả lời mới nhất của Assistant có **Generate Button**: nút "Generate Script" sinh script, hiện khi đang trao đổi, đổi sang màu nhấn khi trợ lý báo đủ thông tin; chỉ bubble mới nhất có nút, đã có script thì không còn nút nào), **Composer** (**Topic Select**, **Duration Select**, nút **Show my scripts** mở **Saved Scripts**, nút **Attach** đính PDF, **File Chip** hiện tên PDF đã đính, ô nhập, nút **Send** (khi phiên đã có script thì đổi thành **Regenerate** ở cùng chỗ, icon mũi tên vòng kèm chữ trên desktop, chỉ icon ở màn hình hẹp: chữ trong ô nhập là feedback, ô trống thì viết bản mới; có **File Chip** thì gửi file vào chat trước rồi mới sinh lại; New chat thì về lại Send), nút **Composer Fold** thu gọn ô nhập dài), **Script Bubble** (thẻ file bấm vào để xem, các nút Practice (xanh) / Save / Copy / Download), **Script Title** (tên script do AI đặt, hiện trên thẻ file trong **Script Bubble**, ở đầu **Script Reader**, và là tên gợi ý trong **Script Name Dialog**), **Refusal Bubble** (khi yêu cầu bị chặn), **Typing Skeleton** (khung chờ khi đang sinh script) |
| **Practice**      | **Practice Steps** (thanh 3 bước: 1 chọn script, 2 ghi âm, 3 chấm). **Text Picker**, 3 tab: _Mine_ (**Mine List** bên trái là Saved Scripts, nút **Mine Fold** thu gọn danh sách; **Mine View** bên phải là nội dung script đang chọn, có **Edit Tools**), _Sample_ (nút lấy script mẫu), _Own_ (tự viết, có bộ đếm từ và nút Save script). Nút **Make a script** (sang Script Studio) và **Use this script**. **Voice Input**, 2 tab: _Record_ (**Rec Timer**, **Level Meter**, nút Record / Pause / Discard) và _Upload_ (**Drop Zone**). **Speed Slider** (tốc độ tô chữ theo WPM). Nút **Evaluate**. **Script Sheet** (khung chữ để đọc, có tên và thông tin script ở trên). **Schedule Banner** (demo, chỉ hiện khi vào bằng Check in: "Scheduled practice · 10 min (hoặc All day / Any length) · category · ghi chú · Demo only", thêm "AI script (read only)" hoặc "Script: <tên>"). **Source Lock** (`setPracticeSourceLock`: khi check in với Saved script hoặc AI script, khoá tab nguồn và bước 1 trong lượt check-in đó). |
| **Schedule**      | (Demo only, dữ liệu trong localStorage `psa.schedule.v1.<user id>`) **Month Calendar** (nút mũi tên tháng trước / sau, nhãn tháng năm bấm mở **Month Picker** đổi nhanh tháng và năm bằng mũi tên lên / xuống, nút **Back to today** nằm trong Month Picker cạnh nút Go, tuần từ Thứ 2, **Day Cell** có số ngày cố định vị trí, hôm nay tô tròn màu nhấn, nút **Add Button** (+, góc ô, khi hover / focus, chỉ ngày từ hôm nay; ô có `sch-can-add` và lớp nền bên trong zoom 0.92→1) mở thẳng Practice Event Modal; **Month Chip** một dòng (icon trạng thái + giờ hoặc "All day"), số chip theo chiều cao ô (`chipsThatFit`), phần dư "+N more"; lưới vừa màn hình trên desktop), **Week View** (**View Switch** Month / Week: radiogroup có thumb trượt, đổi view bằng crossfade, quy đổi tuần/tháng bằng `weekForMonthView` / `monthForWeekView` (tháng khác → tuần chứa ngày 1; tuần khác → tháng chứa Thứ 5), `otherView`; nhớ trong `psa.schedule.view.v1.<user id>`; **Time Slot** `.sch-slot` mỗi giờ còn mở, hover/focus hiện + giữa ô, giờ bắt đầu `slotStartTime`, bàn phím `slotTarget`; hàng **All-day Row**, lưới 24 h cuộn bên trong, **Week Block** đặt theo giờ, cao theo Length, tối thiểu `WEEK_MIN_BLOCK_MIN`, buổi trùng giờ chia cột `layoutDayBlocks`, **Now Line**), **Legend** và **Reset demo** ở đầu lịch. **Session Colour** (9 màu `SCHEDULE_COLORS` từ token, mặc định lime `--event-lime` #84CC16; kiểu vẽ theo trạng thái `occurrenceStyle`: Active và Upcoming nền đầy đủ, Active thêm ring, Done nền `DONE_FILL_OPACITY` 0.5, Missed chỉ viền đứt `MISSED_BORDER_OPACITY` 0.6). Store `version: 3` (`migrateState`: `migrateV1` v1→v2, `migrateV2` v2→v3 đổi blue thành lime). Tạo buổi tập từ Day Drawer hoặc nút +. Trạng thái buổi tập: _upcoming_, _active_ (cửa sổ check-in `[start, min(start + 6 h, 24:00 của ngày đó))`, `CHECKIN_WINDOW_H`), _done_ (Evaluate xong, status ok, overall có giá trị, và lúc Check in nằm trong cửa sổ), _missed_. |
| **Report**        | **Report Header** (tiêu đề, ngày giờ, nút Practice again / ...). **Report State** (thay toàn bộ Report khi audio không đủ để chấm). **Overview** (điểm overall, **Overview Cards** của 4 thành phần, **Coach Bubble** nhận xét ngắn). **Transcript View** (từng từ được tô màu). **Player** (phát lại ghi âm). **Volume Chart**. Cột phải: **Key Numbers** (các số chính) và **Score Card** (**Score Summary**: điểm overall và 4 thành phần, bấm mở Component Detail). |
| **Profile**       | **Avatar Row** (avatar lớn, nút Change / Remove), **Profile Summary** (bảng thông tin cá nhân), **Baseline Row** (trạng thái baseline, nút **Record again** mở Baseline Recorder, nút **Listen** và trình phát giọng mẫu), nút **Edit info** mở Profile Modal |

**Saved Scripts**: danh sách script người dùng đã lưu (tối đa `max_saved_scripts`), hiện "x / N", mỗi script là một thẻ file giống thẻ trong chat, có icon Edit và Delete. Có ở Practice (tab _Mine_) và Script Studio (Show my scripts, dạng menu thả xuống **Saved Menu**).

**Saved-script duplicate errors**: `script_duplicate_body` khi văn bản đã trùng; `script_duplicate_title` khi tên trùng không phân biệt hoa thường.

## 2. Popup (modal) và lớp phủ

| Tên gọi                | Chức năng |
| ---------------------- | --------- |
| **Profile Modal**      | Điền tên hiển thị, giới tính, tuổi, giọng, chủ đề |
| **Consent Modal**      | Hiện khi bấm một tính năng cần ghi âm (Record, Evaluate, Baseline Gate, Record again, Word Coach) mà tài khoản đang tắt ghi âm. Nút _Allow recording_ (lưu consent xong mới chạy tiếp tính năng) và _Not now_ |
| **Settings Modal**     | Mở từ User Menu. Màn đầu là **Settings List**, chọn một mục thì trượt sang màn con (có nút Back): **Permissions** (bật/tắt ghi âm; tắt thì hiện cảnh báo practice và ghi âm bị khoá), **Audio Settings** (chọn mic, thử mic), **Reading Speed** (khoảng min/max của Speed Slider, bật tự chỉnh tốc độ), **Change Password** (mật khẩu hiện tại + mật khẩu mới; link **Forgot Current Password** "Forgot your current password?" gửi mã tới email và mở form nhập mã ngay trong màn này), **Delete Account** (nhập mật khẩu hiện tại để xác nhận) |
| **Safety Alert**       | Báo nội dung bị cấm |
| **Confirm Dialog**     | Xác nhận xoá hoặc thoát |
| **Script Name Dialog** | Nhập tên khi lưu script ở Practice → tab Own (chat và reader lưu luôn theo tên đang hiện) |
| **Script List Full**   | Báo danh sách script đã lưu đã đầy (chỉ có nút Close) |
| **Practice Event Modal** | (Schedule, demo) Tạo hoặc sửa **practice event**: **Date Picker** và **Time Picker** (popover riêng của app, không dùng input gốc), **All Day Switch** (ẩn Time Picker; cửa sổ check-in cả ngày; nhắc 08:00 `ALL_DAY_REMINDER_HOUR`), **Length** (drop list Any length/5/10/15/20 min, `enhanceSelect`), **Category** (drop list Any category + 6 category của Template Store), **Script Field** (Free choice / Saved script / AI generated; AI cần Length và Category cụ thể), **Colour Picker** (9 ô màu, lime mặc định), ghi chú, **Repeat** (segmented None / Daily / Weekly / Custom, Custom có 7 nút Thứ 2–CN), **Ends** (No end / Until date / After N sessions, N 1–99 tính cả buổi đầu; lịch Until đánh dấu các ngày sẽ có buổi; "{n} sessions, last on …" từ `seriesSummary`). Dòng **Reminder** chỉ đọc: nhắc trước 30 phút (`REMINDER_LEAD_MIN`) hoặc 08:00 với All day. Chế độ sửa: **Schedule Lock** `canEditSchedule` (ngày, giờ, All day, lặp; khoá từ giờ nhắc `reminderAt`, kèm dòng "Date and time are locked once the reminder is sent.") và `canEditDetails` (nội dung khác và Delete; khoá từ giờ bắt đầu); nút **Delete**; event lặp thì áp dụng cho buổi này và các buổi sau, chuỗi "After N" nhận số buổi còn lại (`remainingCount`) |
| **Day Drawer**         | (Schedule, demo) Panel nổi bên phải (không cao hết màn hình) mở khi bấm một ngày: danh sách buổi của ngày, mỗi buổi có trạng thái, nút **Check in** (khi đang mở cửa sổ), **Edit** (khi chưa tới giờ bắt đầu, `canEditDetails`), **View result** (buổi done, mở Report của lần luyện tập đó; không còn thì "Result not available"), **Email preview**. Ngày trống hiện chữ nghiêng mờ. Nút **New practice event** ở cuối panel với mọi ngày từ hôm nay trở đi |
| **Email Preview**      | (Schedule, demo) Mẫu email nhắc tập: To, From "Public Speaking Coach (demo)", Subject, thân email, nút Open practice bị vô hiệu, dòng theo **Reminder State** (`reminderState`: skipped "Too close to start", scheduled "Would be sent at …", sent "Sent at …", sent_then_edited "Reminder already sent at … with the earlier details; changes are not re-sent"). Mỗi buổi tối đa 1 email nhắc. Không gửi email thật |
| **Generating Modal**   | (Schedule, demo) Popup "Preparing your script" khi check in với AI script: tiến độ của job `/api/generate-script`, nút Cancel (huỷ poll, không cache, chưa bắt đầu check-in), Try again khi lỗi. Topic chọn ngẫu nhiên theo Category và Length (`pickTopic`); bản sinh lưu ở **AI Script Cache** `psa.schedule.ai.v1.<user id>` theo key buổi, dọn khi done, khi cửa sổ đóng hoặc Reset demo |
| **Script Reader**      | Xem nội dung script (bấm vào thẻ script trong chat hoặc trong Saved Scripts). Nút Edit sửa tên và nội dung ngay trong popup, nút Save, Close và nút **⋯** mở **Reader Menu** (Save script / Copy / Download / Practice) |
| **Evaluating Overlay** | Màn hình chờ chấm điểm, có nút Cancel |
| **Eval Dock**          | Thẻ nhỏ góc trên bên phải (dưới top bar) khi chấm điểm chạy nền: thanh tiến độ và số %. Bấm vào thì thẻ rộng sang trái, hiện các bước đã/chưa chấm và nút Cancel |
| **Error Dialog**       | Báo lỗi, có nút Retry |
| **Baseline Gate**      | Bắt ghi âm giọng mẫu trước khi dùng app (nút Log out hoặc bắt đầu ghi) |
| **Baseline Recorder**  | Ghi lại giọng mẫu, mở từ Profile (nút Record again) |
| **Component Detail**   | Giải thích chi tiết một thành phần điểm, 4 tab A / F / P / S |
| **App Loader**         | Màn chờ toàn trang "Loading your practice…": sau khi đăng nhập đúng (rõ dần từ Busy Overlay) hoặc khi tải lại trang đang đăng nhập, tới khi Home sẵn sàng |
| **Busy Overlay**       | Lớp chờ khi đang làm một việc (ví dụ lưu, xoá, "Logging in…" lúc kiểm tra mật khẩu), có dòng chữ trạng thái |
| **Toast**              | Thông báo ngắn tự ẩn ở góc màn hình |
| **Tooltip**            | Chú thích nhỏ hiện giá trị khi rê chuột lên biểu đồ |

## 3. Mã lỗi tài khoản

| Mã lỗi                  | Khi nào |
| ----------------------- | ------- |
| `consent_required`      | 422: đăng ký (hoặc form gửi kèm mã) không đồng ý ghi âm. 403: route ghi âm khi tài khoản đang tắt ghi âm |
| `otp_invalid`, `otp_expired` | Mã đăng ký hoặc mã đặt lại mật khẩu sai, hết hạn |
| `weak_password`         | Mật khẩu mới dưới 8 ký tự |
| `rate_limited`          | Quá số lần gửi mã, thử mã, nhập mật khẩu hiện tại |
| `invalid_refresh_token` | Không còn phiên (cookie `psa_refresh` thiếu, hết hạn hoặc đã dùng) |
| `origin_mismatch`       | Request refresh/logout đến từ site khác |
| `wrong_password`        | Sai mật khẩu hiện tại (đổi mật khẩu, xoá tài khoản) |

## 4. Trang và phần sẽ thêm (dự kiến)

| Tên gọi             | Mô tả                                                    |
| ------------------- | -------------------------------------------------------- |
| **Guide**           | Trang hướng dẫn sử dụng và giải thích ý nghĩa các chỉ số |
| **Coach Notes**     | Phần LLM nhận xét và khuyên, nằm trong Report            |
| **Feedback Page**   | Trang để người dùng báo lỗi và góp ý                     |
| **Feedback Button** | Icon nhỏ trên mọi trang để báo lỗi tại chỗ               |

## 5. Backend

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
