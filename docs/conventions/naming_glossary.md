# Bảng tên gọi chung (Naming Glossary)

Mục đích: chỉ Tường Vi và AI của Tường Vi gọi đúng một tên cho mỗi trang, popup, phần giao diện và module. Khi báo lỗi, giao việc hay viết PR, hãy dùng tên ở cột **Tên gọi**.

## 1. Màn hình chính

| Tên gọi           | Các phần bên trong                                                                                                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Landing**       | **Stage** (ảnh micro + **Intro**), **Auth Panel** (kèm **Signup Extra**), **Sample Report**, **How It Works**                                                                       |
| **Top Bar**       | **Brand**, **Nav** (Home / Script / Practice), **User Button** (avatar + tên), **User Menu** (Profile, Settings, Log out)                                                           |
| **Home**          | **Hero** (màn đầu: **Greeting**, **Hero Summary**, **Hero CTA**, **Scroll Hint**), bên dưới: **Progress** (**Latest Panel** + 2 biểu đồ), **Detail Charts**, **History** |
| **Script Studio** | **Chat Feed** (**User Bubble**, **AI Bubble**, **Script Bubble** dạng **File Card**, **Refusal Bubble**), **Composer**                                                              |
| **Practice**      | **Stepper** (3 bước), **Text Picker** (_Mine_ / _Sample_ / _Own_), **Script Sheet** (script đang đọc), **Voice Input** (_Record_ / _Upload_), **Speed Slider**, **Evaluate Button** |
| **Report**        | **Report Header**, **Overview Card**, **Transcript View**, **Player**, **Report Charts**, **Score Card** (điểm overall + 4 **Score Section**)                                       |
| **Profile**       | **Profile Card** ở giữa trang: **Avatar**, **Profile Summary** (có dòng Baseline voice), nút Edit details / Record again / Listen to my baseline |

### 1.1 Chi tiết từng màn hình

Cột **Trong code** là id hoặc class để tìm nhanh trong `src/web/`.

| Màn hình      | Tên gọi                         | Trong code                                                                                         | Mô tả                                                                                                                                                                    |
| ------------- | ------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Landing       | **Stage**                       | `.l-stage`                                                                                         | Ảnh nền micro và đèn sân khấu, chứa Intro và Auth Panel                                                                                                                  |
| Landing       | **Intro**                       | `.l-intro`                                                                                         | Câu giới thiệu và nút Create account / Log in                                                                                                                            |
| Landing       | **Auth Panel**                  | `.l-auth`, `#authForm`                                                                             | Form đăng nhập/đăng ký, 2 tab **Log in Tab** (`#authLoginTab`) và **Sign up Tab** (`#authSignupTab`)                                                                     |
| Landing       | **Signup Extra**                | `#signupExtra`                                                                                     | Tên, giọng, chủ đề (bắt buộc); tuổi, giới tính (không bắt buộc)                                                                                                         |
| Landing       | **OTP Step**                    | `#otpStep` (`#otpCode`, `#otpVerify`, `#otpResend`, `#otpBack`, `#otpHint`, `#otpError`) | Bước "Check your email" trong Auth Panel sau Sign up hoặc khi Log in với email chưa xác thực: nhập mã, gửi lại mã có đếm ngược, đổi email (ADR-010) |
| Landing       | **Sample Report**               | `figure.sample`                                                                                    | Thẻ báo cáo mẫu bên dưới Stage                                                                                                                                           |
| Landing       | **How It Works**                | `.how`                                                                                             | Các bước giới thiệu cách dùng                                                                                                                                            |
| Top Bar       | **User Button**                 | `#userBtn` (trong `#userMenuButton`)                                                               | Avatar + tên. Click: sang Profile. Rê chuột: mở User Menu                                                                                                                |
| Top Bar       | **User Menu**                   | `#userMenu`                                                                                        | Dropdown Profile / Settings / Log out                                                                                                                                    |
| Home          | **Hero**                        | `#homeHero`                                                                                        | Màn đầu cao bằng màn hình, nền tối có trang trí (đèn, vầng sáng, sóng âm `.hero-deco`), không có số liệu                                                                 |
| Home          | **Greeting**                    | `#homeH`                                                                                           | Chào theo giờ trong ngày và `display_name` (Good morning / afternoon / evening)                                                                                          |
| Home          | **Hero Summary**                | `#homeSummary`                                                                                     | Một dòng: số buổi tuần này và điểm gần nhất; người mới: lời mời luyện buổi đầu                                                                                            |
| Home          | **Hero CTA**                    | `#homeCta`                                                                                         | Nút chính (buổi đầu, hoặc luyện phần yếu nhất của buổi gần nhất) và nút phụ Create a script                                                                              |
| Home          | **Scroll Hint**                 | `#homeMore`                                                                                        | Chữ nhỏ + mũi tên mờ ở đáy Hero, bấm để cuộn xuống                                                                                                                        |
| Home          | **Later Note**                  | `#homeEmpty`                                                                                       | Người mới: một dòng báo biểu đồ và lịch sử sẽ hiện sau buổi tập đầu                                                                                                      |
| Home          | **Progress**                    | `.home-progress`                                                                                   | Latest Panel (`#latestPanel`) + Score over time (`#chScore`) + Practice minutes (`#chActivity`)                                                                         |
| Home          | **Detail Charts**               | `#chWpm`, `#chPitch`, `#chClarity`                                                                 | Pace, Pitch range, Clarity                                                                                                                                               |
| Home          | **History**                     | `#histSection`, `#historyBody`                                                                     | Bảng các buổi tập, nút xoá từng buổi và **Delete All** (`#delAll`)                                                                                                       |
| Script Studio | **Chat Feed**                   | `#chatFeed`                                                                                        | Luồng tin nhắn trên nền tối                                                                                                                                              |
| Script Studio | **User Bubble** / **AI Bubble** | `.bubble.me` / `.bubble.ai`                                                                        | Khung tin nhắn màu kem của người dùng / của bot                                                                                                                          |
| Script Studio | **File Card**                   | `.fcard`                                                                                           | Script trả về hiển thị như một file, có nút View now                                                                                                                     |
| Script Studio | **Composer**                    | `.composer` (`#composerTopic`, `#chatTpl`, `#composerDuration`, `#composerInput`, `#attachBtn`, `#composerSend`) | Chọn topic, template, thời lượng; ô nhập; đính PDF; nút gửi                                                                                |
| Practice      | **Stepper**                     | `#steps`                                                                                           | 3 bước: chọn text, ghi âm, gửi chấm                                                                                                                                      |
| Practice      | **Text Picker**                 | `#pStep1`; tab `#pickerMineTab`, `#pickerSampleTab`, `#pickerOwnTab`                               | Chọn script; _Own_ tối đa 1500 từ                                                                                                                                        |
| Practice      | **Script Sheet**                | `#sheet` (trong `.prtext`)                                                                         | Script đang đọc; câu tới lượt được in đậm (**Follow Highlight**)                                                                                                         |
| Practice      | **Voice Input**                 | `#pStep2`; tab `#voiceRecordTab`, `#voiceUploadTab`                                                | Ghi âm (**Recorder**: `#recTimer`, `#recLvl`, `#recBtn`) hoặc tải file (**Drop Zone**: `#dropBtn`)                                                                       |
| Practice      | **Speed Slider**                | `#prSpeed`, `#followWpm`                                                                           | Tốc độ chạy của Follow Highlight (không ảnh hưởng điểm)                                                                                                                  |
| Practice      | **Evaluate Button**             | `#evalBtn`                                                                                         | Gửi bài nói để chấm                                                                                                                                                      |
| Report        | **Report Header**               | `#repH`, `#repMeta`, `#repAgain`                                                                   | Tiêu đề, tên bài, nút Practise again / View history                                                                                                                      |
| Report        | **Report State**                | `#repState`                                                                                        | Thông báo khi buổi chấm lỗi hoặc thiếu dữ liệu                                                                                                                           |
| Report        | **Overview Card**               | `#repOverview`                                                                                     | Thẻ xanh: nhận xét tổng quát và một hàng ô chỉ số                                                                                                                        |
| Report        | **AI Coach Note**              | `#repCoachNote`, `.cn-`                                                                            | Nhận xét AI dựa trên điểm đã tính (`#repCoachNote`, class `.cn-`); chỉ diễn giải, không chấm điểm |
| Report        | **Transcript View**             | `#transcriptView`                                                                                  | Từng từ được tô màu: **Wrong Word** (`.w-wrong`), **Near Miss** (`.w-near`), **Missing Word** (`.w-missing`), **Pause Chip** (`.pausechip`), **Filler Chip** (`.fillerchip`) |
| Report        | **Word Coach**                  | `#wordCoach`, `word_coach.js`, `.wc-`                                                              | Panel nổi cạnh từ lỗi: nghe mẫu, nghe lại, thu lại                                                                                                                       |
| Report        | **Sentence Coach**              | `.wc-sent-btn`                                                                                     | Nút cuối câu có tỉ lệ lỗi ≥ ngưỡng, mở cùng panel cho cả câu                                                                                                             |
| Report        | **Hover Note**                  | `#tip`                                                                                             | Ô chú thích hiện khi rê chuột/focus vào từ được tô hoặc điểm trên biểu đồ                                                                                                |
| Report        | **Player**                      | `#player` (`#playBtn`, `#seek`, `#playTime`)                                                       | Phát lại ghi âm; bấm vào một từ để nhảy tới đúng chỗ                                                                                                                     |
| Report        | **Report Charts**               | `#chPace`, `#chPause`, `#chRepPitch`, `#chVol`                                                     | Pace over time, Pauses, Pitch vs baseline, Voice loudness                                                                                                                |
| Report        | **Score Card**                  | `#repScoreCard`                                                                                    | Điểm overall và 4 **Score Section** (`.partbtn`): Accuracy, Fluency, Pronunciation, Semantic; bấm mở Component Detail                                                    |
| Profile       | **Avatar**                      | `#avBig`, `#avChange`, `#avRemove`                                                                 | Ảnh đại diện                                                                                                                                                             |
| Profile       | **Profile Summary**             | `#pfSummary` (trong `.profile-card`)                                                               | Bảng tên, giới tính, tuổi, giọng, chủ đề, Baseline voice (ngày ghi)                                                                                                     |
| Profile       | **Profile Actions**             | `#editInfo`, `#profileBaselineAgain`, `#profileBaselineListen`                                     | Edit details mở Profile Modal; Record again mở Baseline Recorder; nghe lại baseline đã lưu                                                                             |

## 2. Popup (modal)

| Tên gọi                | Trong code           | Chức năng                                                                                                                       |
| ---------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Profile Modal**      | `#profileModal`      | Sửa tên, giới tính, tuổi, giọng, chủ đề                                                                                         |
| **Consent Modal**      | `#consentModal`      | Đồng ý ghi âm và lưu dữ liệu                                                                                                    |
| **Settings Modal**     | `#settingsModal`     | Danh sách 5 mục; chọn mục thì trượt sang trong cùng khung: **Permissions**, **Audio**, **Reading Speed** (`#settingsSpeed`: khoảng tốc độ, Auto speed), **Change Password**, **Delete Account** |
| **Safety Alert**       | `#safetyAlert`       | Báo nội dung bị cấm                                                                                                             |
| **Confirm Dialog**     | `#confirmDialog`     | Xác nhận xoá hoặc thoát                                                                                                         |
| **Evaluating Overlay** | `#evaluatingOverlay` | Màn hình chờ chấm điểm: phần trăm và 9 bước, class `.ev-*` |
| **Error Dialog**       | `#errorDialog`       | Báo lỗi                                                                                                                         |
| **Baseline Gate**      | `#baselineGate`      | Ghi âm 30 giây giọng mẫu (mở sau khi đăng nhập nếu chưa có baseline)                                                            |
| **Baseline Recorder**  | `#baselineRecorder`  | Ghi lại baseline từ Profile (Record again); không hỏi lại quyền ghi âm, không đóng được khi đang ghi hoặc đang gửi               |
| **Component Detail**   | `#componentDetail`   | Giải thích chi tiết một Score Section                                                                                           |
| **Script Reader**      | `#scriptReader`      | Đọc toàn bộ script vừa tạo ở Script Studio                                                                                      |
| **Toast**              | `#toast`             | Thông báo ngắn (thành công / lỗi)                                                                                               |

Password Modal, Audio Settings và Permissions cũ đã gộp vào Settings Modal.

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
| **Coach Note Service** | `POST /api/sessions/{id}/coach-note`, `src/audio_processing/coach_note.py` |
| **Retry Endpoint**    | `/api/practice/retry`: nhận diện lại từ hoặc câu, không lưu phiên |
| **Evaluate Job** | `POST /api/evaluate`, `GET/DELETE /api/evaluate/{job_id}`, `src/audio_processing/evaluate_jobs.py` |
| **Evaluate Pipeline** | Chấm điểm một bài nói: probe → decode → VAD → STT → align → scoring                     |
| **Baseline Pipeline** | Phân tích giọng mẫu: probe → decode → VAD → pause profile + F0                          |
| **Script Pipeline**   | Sinh script: parser → sanitizer → generator. Sắp thêm **Template Matcher** và **Guard** |
| **Template Matcher**  | Dò kho template, chọn bài phù hợp trước khi phải gọi LLM (sắp làm)                      |
| **Guard**             | Chặn prompt injection và nội dung độc hại (sắp làm)                                     |
| **Template Corpus**   | Kho bài mẫu: 6 chủ đề, mỗi chủ đề khoảng 100 bài                                        |
| **Email OTP**         | Xác thực email khi đăng ký: `POST /api/auth/verify-otp`, `POST /api/auth/resend-otp`, tham số `[auth]` trong `app_constants.toml` (ADR-010) |
