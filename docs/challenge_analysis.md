# TASK

## **📌**CHALLENGE 1: XỬ LÝ VĂN BẢN & SINH SCRIPT (Text, PDF, Script)
*Phụ trách: Chí Bảo, Gia Đạt*
  - **Pipeline đọc & hiểu ngữ cảnh:** Làm sao hệ thống có thể trích xuất text sạch từ các định dạng đầu vào khác nhau (file PDF, văn bản nhập trực tiếp)? Cần dùng thư viện/công cụ nào để parse dữ liệu hiệu quả và xử lý khi file bị lỗi/thiếu chữ?
  - **Cơ chế Validate nội dung:** Xây dựng quy tắc (rule) để hệ thống tự động kiểm tra xem nội dung người dùng đưa vào có hợp lệ hay không (đúng chủ đề, đủ thông tin tối thiểu, có nằm trong scope của bài thuyết trình không).
  - **Chiến lược sinh văn bản (Text Generation Strategy):**
      - Nghiên cứu phương án kết hợp giữa **Template có sẵn** (cho các chủ đề phổ biến để tiết kiệm thời gian, giảm chi phí gọi LLM) và **LLM** (để tạo sự linh hoạt, sáng tạo).
      - Đánh giá xem khi nào nên dùng template, khi nào bắt buộc phải gọi LLM và có giải pháp caching nào để tối ưu hiệu suất không?
## **📌CHALLENGE 2: XỬ LÝ ÂM THANH & SO KHỚP ĐÁNH GIÁ (Speech Processing & Matching)**
*Phụ trách: Kim Hoa, Hương Mai*
  - **Tối ưu hóa Speech-to-Text (STT):** Nghiên cứu giải pháp chuyển đổi giọng nói thành văn bản làm sao để hạn chế tối đa tiếng ồn, tạp âm (noise), tăng độ chính xác và khả năng nhận diện các từ khóa chuyên ngành / từ khó bằng tiếng Anh.
  - **Thuật toán so khớp chuỗi (String Matching):** Nghiên cứu cách so sánh bản ghi âm sau khi chuyển thành text với kịch bản gốc (Script) để tìm ra các lỗi đọc sai, thiếu từ, thừa từ (Ví dụ: Dùng Levenshtein Distance, Fuzzy Matching hay Vector Embedding).
  - **Phân tích nhịp điệu & khoảng dừng (Pacing & Tempo):** Tìm hiểu cách đo lường tốc độ nói (từ/phút), phát hiện các khoảng dừng (silence/pauses) bất thường hoặc nhịp điệu ngắt nghỉ của người dùng để làm cơ sở đánh giá độ trôi chảy (fluency).
## **📌CHALLENGE 3: KIẾN TRÚC DỮ LIỆU, LƯU TRỮ & TIÊU CHÍ ĐÁNH GIÁ (Data, Storage & Evaluation Logic)**
*Phụ trách: Tường Vi, Quốc Tuấn*
  - **Xây dựng tiêu chí đánh giá (Scoring Criteria):** Xác định rõ hệ thống dựa trên những chỉ số nào để chấm điểm cho 1 phiên luyện tập, và dựa trên lịch sử các lần tập trước ra sao để thấy được sự tiến bộ của người dùng. Dữ liệu đầu vào cho AI chấm điểm gồm những gì?
  - **Định nghĩa mô hình dữ liệu (Database Schema):** Cụ thể hóa các thực thể cần lưu trữ xuống database:
      - *Profile lưu những gì?* (Thông tin cá nhân, mục tiêu giọng đọc, cài đặt cá nhân...).
      - *History lưu những gì và lấy bao nhiêu?* (Cần phân trang hay lưu toàn bộ file audio, audio lưu trên cloud hay local, dung lượng dự kiến ra sao...).
  - **Lựa chọn công nghệ lưu trữ:** Đề xuất CSDL phù hợp (Relational DB như PostgreSQL/MySQL), ước tính độ lớn dữ liệu tăng trưởng theo thời gian và xác định những dữ liệu hệ thống cần chuẩn bị sẵn (Master data, template mẫu, từ vựng...).
## **PHẦN TRÌNH BÀY:**
  - Mô tả lại chi tiết tất cả các bài toán của phần được giao.
  - Đưa ra giải pháp, giải pháp đó giải quyết được triệt để không hay khía cạnh nào đó?
  - Hạn chế của giải pháp, tính khả thi và chi phí?


# CHALLENGE 1

# **BÁO CÁO KỸ THUẬT CHALLENGE 1: PIPELINE XỬ LÝ NGỮ CẢNH, KIỂM DUYỆT AN TOÀN & SINH KỊCH BẢN THUYẾT TRÌNH**
## **PHẦN I. PIPELINE ĐỌC & HIỂU NGỮ CẢNH (DOCUMENT INGESTION & PARSING)**
### **1. Mô tả bài toán & Khó khăn kỹ thuật**
  - **Nhiễu định dạng và lỗi mã hóa từ văn bản nhập trực tiếp (Raw Text Input):** Dữ liệu copy-paste từ web/Word/PDF thường dính ký tự điều khiển ẩn (\u200b, \xa0), lỗi lệch bảng mã UTF-8/Windows-1252 (mojibake như â€™, â€"), hoặc ngắt dòng cứng (hard line-breaks) sau mỗi 10–12 từ làm đứt mạch câu.
  - **Phá vỡ mạch đọc do bố cục PDF phức tạp:**
  - *Multi-column PDF:* Tài liệu học thuật chia 2 cột khiến các thư viện đọc cơ bản quét ngang ghép nhầm dòng của cột 1 vào cột 2.
  - *Slide Text-box & Header/Footer:* File xuất từ PowerPoint/Canva chứa nhiều text-box rời rạc kèm Header, Footer, số trang (Page 1 of 10), Watermark lặp lại chèn vào giữa câu văn khi nối trang.
  - *Bảng số liệu (Tables):* Trích xuất thô làm bung các ô thành dòng rời rạc, mất liên kết giữa tiêu đề cột và số liệu.
  - **File PDF thiếu lớp văn bản (Scanned & Hybrid PDF):** File scan toàn phần trả về chuỗi rỗng, hoặc file PDF lai (ví dụ 8 trang chữ + 2 trang ảnh chụp sơ đồ/bảng biểu) làm mất thông tin âm thầm ở các trang ảnh nếu không kiểm tra từng trang.
  - **Lỗi Font / Hỏng bảng ánh xạ ký tự (Corrupted CMap / CID Font):** Thiếu bảng /ToUnicode khiến text trích xuất biến thành ký tự \ufffd hoặc chuỗi mã định danh (cid:114) (cid:85) không thể đọc hiểu.
  - **Lỗi đứt từ gạch ngang và dính chữ đặc thù trong tiếng Anh:** Văn bản căn đều 2 lề (Justified) ngắt từ bằng dấu gạch ngang cuối dòng (pronun-\nciation, artifi-\ncial) hoặc dùng tọa độ dịch chuyển thay vì khoảng trắng gây dính chữ (Publicspeakingassistant), làm sai lệch trực tiếp kịch bản chấm phát âm ở Pipeline 2.
  - **Mất cấu trúc phân cấp & File hỏng vật lý:** Cào phẳng văn bản làm mất phân tầng Title -> Heading 1 -> Heading 2 -> Body. Ngoài ra, hệ thống phải chặn sớm file 0 byte, file giả mạo đuôi .pdf, file bị cắt cụt byte hoặc khóa mật khẩu để tránh crash.
### **2. Giải pháp kiến trúc: Pipeline 4 chốt chặn & Phân tầng công cụ**
Hệ thống kết hợp các thư viện mã nguồn mở tốc độ cao và Vision API theo 4 giai đoạn:
1.  **Chốt 1 – File Sanity Gate (Kiểm tra toàn vẹn):** Kiểm tra chữ ký 5 byte đầu (%PDF-), dung lượng (1KB – 25MB), trạng thái mật khẩu (doc.is_encrypted) và số trang (doc.page_count > 0). Từ chối sớm (Early Exit) nếu vi phạm.
2.  **Chốt 2 – Chẩn đoán từng trang & Định tuyến tự động (Page-Level Routing):** Cắt bỏ 7% đỉnh và 7% đáy trang để lọc Header/Footer, sau đó đo số ký tự thực (*C_char*) và tỷ lệ ký tự lỗi (*R_garbled*) trên từng trang:
  - *Nhánh A – Trang PDF chuẩn (85% trường hợp, C_char ≥ 50 và R_garbled < 8%):* Dùng PyMuPDF4LLM (lõi C/C++, tốc độ ~0.05s/trang) để rút văn bản Markdown giữ nguyên thứ tự cột và thẻ # Heading, kết hợp pdfplumber tái tạo bảng số liệu thành Markdown Table.
  - *Nhánh B – Cứu hộ trang Scan / Lỗi Font CID (15% trường hợp, C_char < 50 có chứa ảnh hoặc R_garbled ≥ 8%):* Hủy lớp text lỗi, render riêng trang đó ra ảnh 200 DPI và đẩy qua RapidOCR (ONNX) trên CPU hoặc Gemini 2.5 Flash Vision để rút chữ.
1.  **Chốt 3 – Làm sạch & Phục hồi từ vựng tiếng Anh (Text Sanitization):** Dùng ftfy.fix_text() và unicodedata (NFC) sửa lỗi bảng mã mojibake; dùng Regex ([a-zA-Z]{2,})-\s*\n\s*([a-z]{2,}) nối từ tiếng Anh bị gạch ngang cuối dòng; dùng wordninja tách các từ dính liền. Nếu tổng số từ sau xử lý < 30 từ thì trả về Context valid? = No.
2.  **Chốt 4 – Đóng gói cây ngữ cảnh (JSON Context Packaging):** Xuất cấu trúc JSON gồm văn bản Markdown phân cấp, danh sách headings (làm khung dàn ý) và key_terms (từ vựng trọng tâm) để chuyển thẳng sang bước **Validate**.
[image]
### **3. Bảng đánh giá mức độ giải quyết & So sánh chi phí đọc file**
|  |  |  |
| :- | :- | :- |
| **Tiêu chí đánh giá** | **Phương án 1: 100% Local Open-Source (PyMuPDF4LLM + RapidOCR CPU)** | **Phương án 2: Hybrid Cloud Vision (PyMuPDF4LLM + Gemini 2.5 Flash)** |
| **Chi phí xử lý trang PDF chuẩn (85%)** | $0 (Miễn phí hoàn toàn) | $0 (Miễn phí hoàn toàn) |
| **Chi phí xử lý trang lỗi / Scan (15%)** | $0 (Chạy RapidOCR trực tiếp trên CPU) | ~$0.00003 / trang lỗi (~750 VNĐ cho 1.000 trang lỗi) |
| **Tài nguyên phần cứng (RAM)** | 300MB – 450MB RAM (nạp model ONNX trên CPU) | Dưới 100MB RAM (xử lý ảnh nặng đẩy lên Cloud API) |
| **Tốc độ trung bình (File 10 trang, 2 trang lỗi)** | ~1.8 giây / file | ~1.2 giây / file |
| **Khả năng đọc Slide đồ họa & Biểu đồ** | Trung bình (chỉ lấy được chữ rời rạc trên biểu đồ) | Rất cao (hiểu được chiều mũi tên Mindmap và xu hướng biểu đồ) |

-----
## **PHẦN II. CƠ CHẾ KIỂM DUYỆT AN TOÀN & TÍNH HỢP LỆ (MULTI-LAYER VALIDATION)**
Sau khi nhận được JSON ngữ cảnh sạch từ Phần I, dữ liệu phải đi qua hệ thống kiểm duyệt 2 tầng trên hạ tầng GroqCloud để chống tấn công hệ thống và lọc nội dung vi phạm chính sách.
### **1. Bài toán & Thách thức kỹ thuật (Dựa trên thông số Rate Limit thực tế)**
|  |  |  |  |  |  |  |
| :- | :- | :- | :- | :- | :- | :- |
| **Tầng kiểm duyệt** | **Model sử dụng (GroqCloud)** | **RPM (Req/phút)** | **RPD (Req/ngày)** | **TPM (Token/phút)** | **TPD (Token/ngày)** | **Đánh giá điểm nghẽn (Bottleneck)** |
| **Tầng 1: Chống Prompt Injection** | meta-llama/llama-prompt-guard-2-86m    meta-llama/llama-prompt-guard-2-22m | 30 | 14.4K | 15K | 500K | **Rất thoải mái.** Tổng cộng 2 model đạt **60 RPM** và **28.8K RPD**, dư sức đáp ứng lưu lượng lớn. |
| **Tầng 2: Kiểm duyệt nội dung (Content Safeguard)** | openai/gpt-oss-safeguard-20b | **3** | 1K | **2K** | 200K | **Điểm nghẽn nghiêm trọng.** Chỉ cho phép **3 req/phút** và **2.000 token/p** |

  - **Khó khăn thực tế ở Tầng 1 (Prompt Guard):** Dù người dùng chỉ tải lên file PDF/Text làm ngữ cảnh, kẻ gian vẫn có thể cài cắm lệnh độc hại ẩn bên trong tài liệu (**Indirect Prompt Injection**). Với giới hạn 30 RPM/model, nếu nhiều người dùng bấm cùng lúc trong một giây có thể chạm ngưỡng RPM cục bộ.
  - **Khó khăn chí mạng ở Tầng 2 (Content Safeguard):**
  - Model openai/gpt-oss-safeguard-20b bị giới hạn cực gắt ở mức **3 RPM** (trung bình 20 giây mới được gọi 1 lần) và **2K TPM**.
  - Qua thực nghiệm test thực tế, 1 request kiểm duyệt tiêu tốn khoảng **450 tokens**. Như vậy, nếu gọi liên tiếp 4–5 requests trong 1 phút (450 × 5 = 2.250 tokens), hệ thống sẽ lập tức văng lỗi 429 Too Many Requests do chạm cả trần **3 RPM** lẫn trần **2.000 TPM**. Hơn nữa, nếu người dùng tải lên một file PDF dài 10 trang (~4.000 tokens) và đẩy nguyên văn vào gpt-oss-safeguard-20b, ngay lập tức request đầu tiên đã vượt trần 2K TPM và thất bại hoàn toàn.
### **2. Giải pháp kỹ thuật cho bài toán Validate**
#### **A. Giải pháp cho Tầng 1 – Prompt Guard (Load Balancing & UX Delay)**
  - **Load Balancing & Fallback giữa 2 model:** Thiết kế bộ cân bằng tải (Round-Robin hoặc Failover) giữa llama-prompt-guard-2-86m (ưu tiên chạy chính vì độ chính xác cao hơn) và llama-prompt-guard-2-22m (chạy dự phòng khi model 86m chạm 30 RPM), nâng tổng công suất lên **60 requests/phút** và **28.800 requests/ngày**.
  - **Thiết kế UX "Thinking & Evaluating State" (Hàng đợi thông minh):** Trên giao diện Web App, khi người dùng bấm nút gửi ngữ cảnh, hệ thống hiển thị trạng thái *"Trợ lý đang đọc và phân tích độ an toàn của tài liệu..."* kết hợp **Request Queue (Hàng đợi) có nhịp delay 1.5 – 2 giây** ở Backend. Khoảng delay nhỏ này hoàn toàn tự nhiên với trải nghiệm người dùng nhưng giúp dàn đều các request, đảm bảo không bao giờ vượt quá ngưỡng 30–60 RPM.
  - **Cơ chế Caching SHA-256 cho Prompt Guard:** Tạo mã băm SHA-256 cho chuỗi prompt đầu vào. Nếu phát hiện prompt trùng lặp đã được kiểm duyệt trước đó, hệ thống lập tức trả về kết quả từ Cache (0ms, 0 API call), giúp giảm tải triệt để cho API và tối ưu tối đa độ trễ phản hồi.
#### **B. Giải pháp thiết kế "Local Safeguard Pipeline" & "Constraint by Design" (Khắc phục triệt để giới hạn API)**
Để giải quyết bài toán 1 request tốn 450 tokens trên nền giới hạn 3 RPM và 2K TPM của gpt-oss-safeguard-20b, hệ thống áp dụng **Chiến lược Lọc Đa Tầng & Nén Ngữ Cảnh**:
1.  **Chốt chặn cơ học siêu tốc (Local Regex & Profanity Check):** Ngay khi nhận văn bản đầu vào, hệ thống chạy bộ lọc từ khóa (Blacklist) và thư viện profanity-check trực tiếp trên server Python. Lớp "bảo vệ vòng ngoài" này chặn đứng tức thời (0.001s) các nội dung thô tục, chửi thề lộ liễu, giúp máy chủ không phải lãng phí tài nguyên RAM/CPU để chạy AI cho những vi phạm cơ bản. 
2.  **AI Thẩm phán cục bộ (Local Llama-Guard-3-1B qua Ollama):** Thay thế hoàn toàn API đám mây, hệ thống triển khai mô hình siêu nhẹ Llama-Guard-3 (phiên bản 1 tỷ tham số) chạy ngầm qua công cụ Ollama ngay trên máy chủ cục bộ. Mô hình này làm nhiệm vụ quét sâu văn bản để phân loại các rủi ro phức tạp (Bạo lực, Tình dục, Thù ghét...) theo tiêu chuẩn an toàn MLCommons. Việc chạy cục bộ giúp phá vỡ hoàn toàn giới hạn 3 request/phút, cho phép hệ thống tự do xử lý lưu lượng lớn mà dữ liệu PDF của người dùng không hề bị đẩy ra ngoài internet. 
3.  **Kiểm soát chủ đề hợp lệ bằng "Constraint by Design" (Ràng buộc qua Giao diện):** Để ngăn chặn rủi ro người dùng tải lên tài liệu không phù hợp mục đích ứng dụng (Out-of-scope, ví dụ: bắt AI viết công thức nấu ăn), thay vì dùng một LLM khác để đọc và đánh giá tốn kém, hệ thống thiết kế UI ép buộc người dùng phải chọn Topic từ một danh sách thả xuống (Dropdown) cố định gồm các chủ đề hợp lệ. Khách hàng bắt buộc đi theo luồng dữ liệu đã định sẵn, loại bỏ hoàn toàn các yêu cầu lạc đề trước khi bước vào khâu sinh kịch bản. 
4.  **Cơ chế Caching kết quả (SHA-256 Content Hashing):** Dùng hàm băm (hash) mã hóa nội dung đầu vào. Nếu người dùng ấn tạo lại kịch bản trên cùng một tài liệu PDF/Text đã được quét và đánh dấu SAFE trước đó, hệ thống sẽ lấy ngay kết quả hợp lệ từ Cache (0ms). Bước này giúp tối ưu hóa tuyệt đối sức mạnh tính toán của CPU/GPU nội bộ, không bắt Llama Guard phải đọc lại một tài liệu hai lần. 
-----
## **PHẦN III. CHIẾN LƯỢC SINH KỊCH BẢN THUYẾT TRÌNH (HYBRID SCRIPT GENERATION)**
Sau khi vượt qua bước Validate, hệ thống tiến hành sinh kịch bản thuyết trình tiếng Anh (Plain Text / Structured Markdown) thông qua bộ định tuyến thông minh (**Hybrid Generation Router**) dựa trên chủ đề (Topic) và độ dài bài nói.
### **1. Mô tả bài toán & Phân tích tài nguyên Token**
  - **Yêu cầu đầu ra:** Một bài thuyết trình tiếng Anh kéo dài khoảng **5 phút** (tốc độ nói chuẩn ~130–150 từ/phút) tương đương 650–750 từ tiếng Anh (~1.000 tokens đầu ra). Cộng thêm ngữ cảnh đầu vào (Context) và System Prompt (~800–1.000 tokens), **mỗi lần sinh kịch bản 5 phút tiêu tốn khoảng ~2.000 tokens**.
  - **Đánh giá hạn mức từ GroqCloud:** Các model sinh văn bản chủ lực gồm openai/gpt-oss-120b, openai/gpt-oss-20b, và qwen/qwen3.8-27b đều có hạn mức: **30 RPM**, **1K RPD**, **8K TPM** và **200K TPD**.
  - **Điểm nghẽn:** Với mức tiêu thụ ~2.000 tokens cho một bài nói 5 phút, **1 model đơn lẻ (8K TPM) chỉ có thể xử lý tối đa 4 bài nói 5 phút trong 1 phút**, và tối đa khoảng 100 bài nói/ngày (200K TPD). Nếu mọi yêu cầu đều gọi thẳng vào 1 LLM duy nhất, hệ thống sẽ nhanh chóng cạn kiệt hạn mức TPM khi có nhiều người dùng cùng lúc.
### **2. Giải pháp kiến trúc: Chiến lược Sinh Kịch Bản Lai (Hybrid Strategy)**
Hệ thống chia thành **2 nhánh xử lý** dựa trên việc kiểm tra chủ đề đầu vào đối chiếu với Kho lưu trữ mẫu (Template Repository):
#### **Nhánh 1: Chủ đề ĐÃ CÓ SẴN trong Kho lưu trữ (Template-Based + Dynamic NLP/Micro-LLM)**
Dành cho các chủ đề thuyết trình phổ biến đã được thiết kế sẵn khung sườn (ví dụ: *Pitching sản phẩm, Báo cáo học thuật, Giới thiệu bản thân, Thuyết trình giải pháp công nghệ...*).
  - **Bước 1 – Khớp khung Template (Modular Template Matching):** Lấy bộ khung kịch bản tương ứng (gồm các khối *Opening Hook*, *Body Transitions*, *Call-to-Action Closing*) chứa các biến khuyết ({{ topic }}, {{ main_arguments }}, {{ key_statistics }}, {{ conclusion_takeaway }}).
  - **Bước 2 – Nội suy dữ liệu bằng NLP (NLP Interpolation - 0 Token):** Sử dụng trực tiếp cây JSON từ Phần I (headings, các câu chủ đề chứa từ khóa key_terms, bảng số liệu) kết hợp thuật toán NLP truyền thống (TF-IDF / TextRank / Regex) để điền tự động vào các placeholder trong Template.
  - **Bước 3 – Bổ sung kiến thức thiếu & Cắt tỉa động (Micro-LLM Call & Dynamic Pruning):**
  - Nếu hệ thống phát hiện một số placeholder trong template chưa đủ thông tin từ file PDF của người dùng, hoặc câu văn ghép vào bị gượng gạo, hệ thống chỉ thực hiện một **Micro-LLM Call** (gọi API chỉ để viết nối hoặc bổ sung đúng đoạn bị thiếu đó, tốn ~200–300 tokens thay vì 2.000 tokens).
  - Tự động cắt tỉa (prune) các khối template dư thừa để khớp chính xác với thời lượng phút mà người dùng yêu cầu.
#### **Nhánh 2: Chủ đề có trong Kho lưu trữ NHƯNG KHÔNG CÓ TEMPLATE (Multi-Model Fallback Chain)**
Khi người dùng đưa vào một tài liệu hoặc chủ đề hoàn toàn mới, hệ thống kích hoạt chuỗi **Fallback 3 tầng mô hình lớn** (với cấu hình temperature = 0.7, top_p = 0.9 để văn phong tự nhiên, truyền cảm):
|  |  |  |  |
| :- | :- | :- | :- |
| **Thứ tự ưu tiên** | **Model ID (GroqCloud)** | **Vai trò trong chuỗi Fallback** | **Năng lực đáp ứng (TPM / TPD)** |
| **Priority 1 (Chính)** | openai/gpt-oss-120b | Model 120 tỷ tham số lớn nhất, chịu trách nhiệm sinh các kịch bản đòi hỏi lập luận sâu, từ vựng học thuật cao cấp và cấu trúc chặt chẽ. | 30 RPM / 8K TPM / 200K TPD |
| **Priority 2 (Dự phòng 1)** | qwen/qwen3.8-27b | Tự động kích hoạt ngay khi gpt-oss-120b báo lỗi 429 (vượt 8K TPM khi có >4 bài 5 phút/phút). Dòng Qwen 3.8 27B cực mạnh về xử lý đa ngôn ngữ và bám sát ngữ cảnh tài liệu. | 30 RPM / 8K TPM / 200K TPD |
| **Priority 3 (Dự phòng 2)** | openai/gpt-oss-20b | Chốt chặn cuối cùng có tốc độ phản hồi cực nhanh, đảm bảo dịch vụ luôn hoạt động 100% không bị gián đoạn. | 30 RPM / 8K TPM / 200K TPD |

**Hiệu quả cộng gộp:** Nhờ cơ chế Fallback 3 model này, tổng hạn mức sinh kịch bản của toàn hệ thống được nâng lên gấp 3 lần: **90 RPM**, **24.000 Tokens/phút** (xử lý được 12 kịch bản 5 phút cùng lúc mỗi phút) và **600.000 Tokens/ngày** (~300 kịch bản dài/ngày), hoàn toàn miễn phí và dư dả cho quy mô vận hành của ứng dụng.
-----
## **PHẦN IV. ĐÁNH GIÁ TỔNG THỂ: HẠN CHẾ, TÍNH KHẢ THI & TỐI ƯU BẢO TRÌ (OOP DESIGN)**
### **1. Hạn chế còn tồn đọng và cách khắc phục**
  - **Độ trễ khi gặp file PDF Scan kết hợp hàng đợi Validate:** Nếu người dùng tải lên file PDF scan 10 trang (mất 7–12 giây chạy OCR trên CPU) cộng thêm thời gian chờ của gpt-oss-safeguard-20b khi quá tải (3 RPM), tổng thời gian phản hồi có thể lên tới 15 giây. *Khắc phục:* Bật phương án Hybrid Cloud (Gemini 2.5 Flash Vision) cho các trang scan để kéo thời gian đọc file xuống ~1.2 giây và dùng gpt-oss-20b làm fallback kiểm duyệt tức thời.
  - **Giới hạn của NLP Interpolation trên Template:** Khi điền tự động bằng NLP vào template có sẵn, các câu chuyển ý có thể kém mượt mà hơn so với bài viết 100% bằng LLM. *Khắc phục:* Áp dụng bước *Dynamic Pruning & Smoothing* nhẹ bằng gpt-oss-20b ở cuối bước ghép template.
### **2. Định hướng thiết kế Class Diagram (Đáp ứng yêu cầu dễ nâng cấp, bảo trì của Giảng viên)**
Để dễ dàng nâng cấp, thay đổi model hoặc thêm định dạng file mới trong tương lai mà không phải sửa code cốt lõi (tuân thủ nguyên lý **Open-Closed Principle** và sử dụng **Abstract Class**), hệ thống Challenge 1 được thiết kế thành 3 lớp trừu tượng chính:
1.  **BaseDocumentParser (Abstract Class):** Định nghĩa phương thức trừu tượng extract_context(input_data) -> ContextTree. Các lớp con kế thừa gồm DigitalPDFParser, OCRHybridPDFParser, và RawTextParser. Tương lai muốn thêm hỗ trợ file .docx hay .pptx chỉ cần viết thêm class con mới.
2.  **BaseContentValidator (Abstract Class):** Định nghĩa phương thức validate(context: ContextTree) -> ValidationResult (Áp dụng *Chain of Responsibility Pattern*). Các lớp con gồm RegexKeywordValidator → LlamaPromptGuardValidator → SafeguardContentValidator.
3.  **BaseScriptGenerator (Abstract Class):** Định nghĩa phương thức generate_script(context: ContextTree, config: SpeechConfig) -> Script. Hai lớp con thực thi gồm TemplateNLPGenerator (xử lý nhánh chủ đề có sẵn) và FallbackLLMGenerator (quản lý danh sách ưu tiên gpt-oss-120b → qwen3.8-27b → gpt-oss-20b).


# CHALLENGE 2

# **BÁO CÁO KỸ THUẬT CHALLENGE 2: XỬ LÝ ÂM THANH, SO KHỚP CHUỖI VÀ ĐÁNH GIÁ NHỊP ĐIỆU**
## **PHẦN I. TỐI ƯU HÓA SPEECH-TO-TEXT (STT) VÀ KIẾN TRÚC FALLBACK ROUTER**
### **1. Mô tả bài toán & Khó khăn kỹ thuật**
Bài toán cốt lõi là xử lý file ghi âm dài (5 - 7 phút) có dung lượng lớn (Asynchronous) để bóc tách văn bản thô. Hệ thống phải đối mặt với các khó khăn:
  - **Tràn bộ nhớ (Out of memory):** Nạp toàn bộ file lớn để xử lý có thể gây sập module.
  - **Lỗi Timeout:** Xử lý đoạn âm thanh dài qua API HTTP mất nhiều thời gian, kết nối có thể bị đóng lại trước khi module trả về kết quả.
  - **Hallucination (Ảo giác):** Âm thanh quá dài khiến các mô hình AI bị nhầm lẫn, lặp câu hoặc tự bịa ra văn bản ở các khoảng lặng.
  - **Tách bóc siêu văn bản:** Yêu cầu kết quả đầu ra phải có dấu câu chính xác để phục vụ hậu xử lý.
  - **Trải nghiệm người dùng:** Hệ thống cần cơ chế xử lý bất đồng bộ, không được đóng băng giao diện trong lúc chờ.
### **2. Kỹ thuật Tiền xử lý & Khử nhiễu (Pre-processing)**
Để tối ưu tốc độ và giảm thiểu lỗi cho mô hình STT, mọi file ghi âm đầu vào đều đi qua bộ công cụ chuẩn công nghiệp (FFmpeg):
  - **Hạ tần số lấy mẫu (Downsampling):** Hạ tần số thu âm từ 44.1kHz xuống 16kHz (dải âm giọng nói người), giúp giảm ngay 60% dung lượng.
  - **Gộp kênh âm thanh (Stereo to Mono):** Chuyển từ 2 kênh sang 1 kênh, chia đôi dung lượng file mà không làm mất dữ liệu từ vựng.
  - **Đổi định dạng (Lossless sang Lossy):** Chuyển từ .WAV sang định dạng nén (.MP3, .OGG).
  - **Khử nhiễu chủ động (DSP):** Triệt tiêu tiếng xì xào môi trường, làm nổi bật giọng người.
  - **Tự động cân bằng âm lượng (AGC):** Cân bằng âm thanh tạo luồng tín hiệu ổn định trước khi đưa vào mô hình AI.
### **3. Giải pháp Kiến trúc: Định tuyến STT Đa Tầng (Hybrid STT Fallback Router)**
Hệ thống loại bỏ thiết kế gọi API đồng bộ thông thường. Thay vào đó, áp dụng cơ chế **One-Shot API Call** (Một request trả về cả Text có dấu câu và Word-level Timestamps) kết hợp định tuyến 3 ưu tiên (Fallback Router) để đảm bảo 100% High Availability (độ sẵn sàng cao):
|  |  |  |  |
| :- | :- | :- | :- |
| **Thứ tự Ưu tiên** | **Mô hình / API sử dụng** | **Thông số Giới hạn & Điểm mạnh** | **Vai trò trong luồng Fallback** |
| **Priority 1**    **(Chính)** | **GroqCloud API**    (Mô hình whisper-large-v3) | \- 20 RPM, 2K RPD    \- Upload Max: 100MB    \- Chi phí: $0 (Miễn phí) | Chịu tải chính cho hệ thống nhờ tốc độ xử lý siêu tốc (chip LPU). Hầu hết các file luyện tập sau khi nén (khoảng 3-5MB) đều lọt qua mốc 100MB. Nếu vượt quá 20 request/phút, kích hoạt Priority 2. |
| **Priority 2**    **(Dự phòng Cloud)** | **Deepgram (Nova 3)** hoặc **Gladia (Solaria 3)** | \- Upload Max: 1GB - 2GB    \- Chi phí dự kiến: ~$0.0043/phút (Sử dụng quỹ Credit miễn phí của Developer) | Tự động kích hoạt khi GroqCloud chạm Rate Limit (lỗi 429) hoặc khi file gốc vượt quá 100MB. Đảm bảo dịch vụ không bị gián đoạn và trả về dấu câu xuất sắc phục vụ so khớp. |
| **Priority 3**    **(Cục bộ - Local)** | **Faster-Whisper**    (Mã nguồn mở) | \- Chạy nội bộ trên Server CPU/GPU    \- Không tốn phí, Không bị Rate Limit | Chốt chặn cuối cùng. Nằm ở trạng thái ngủ (Idle) và chỉ được đánh thức khi server mất mạng, đứt cáp quang, hoặc toàn bộ quỹ Credit API đám mây đã cạn kiệt. |

-----
## **PHẦN II. THUẬT TOÁN SO KHỚP CHUỖI (STRING MATCHING)**
### **1. Mô tả bài toán**
Hệ thống đối chiếu giữa kịch bản tiếng Anh gốc (Reference Script) và văn bản từ STT (Hypothesis Transcript) để nhận diện các lỗi:
  - **Lỗi đọc sai / phát âm nhầm từ (Substitution):** Ví dụ: kịch bản là "think" nhưng phát âm sai thành "sink".
  - **Lỗi bỏ sót từ (Deletion / Omission):** Đọc lướt làm mất mạo từ (a, an, the), giới từ, hoặc cả cụm từ.
  - **Lỗi thừa từ & Từ đệm (Insertion & Filler Words):** Bị vấp, lặp từ hoặc chêm từ đệm ("um", "uh", "er").
  - **Từ đồng âm & Viết tắt (Homophones & Contractions):** Script ghi "do not" nhưng đọc nối "don't". Hoặc từ đồng âm ("their" và "there") khiến thuật toán so sánh mặt chữ đếm lỗi sai oan.
  - **Diễn đạt tương đương (Paraphrasing):** Thuyết trình tự nhiên theo ý hiểu thay vì đọc vẹt.
### **2. Giải pháp kỹ thuật đa tầng (Chạy 100% Cục bộ)**
1.  **Chuẩn hóa văn bản tiếng Anh (English Text Normalization):**
  - Đưa toàn bộ về chữ thường, tách và lưu vị trí dấu câu.
  - Dùng thư viện contractions bung từ viết tắt ("don't" -> "do not") và num2words chuyển số thành chữ.
1.  **Gióng hàng chuỗi mức độ từ (Word-level Levenshtein Alignment):**
  - Dùng thư viện jiwer (quy hoạch động) gióng hàng từng từ và tính tỷ lệ lỗi WER.
  - Gắn nhãn cơ bản tại mỗi vị trí: Equal (Khớp), Replace (Sai từ), Delete (Thiếu), Insert (Thừa).
1.  **So khớp mờ kết hợp Mã hóa Âm vị (Fuzzy & Phonetic Matching) - ĐIỂM SÁNG:**
  - Các từ bị đánh nhãn Replace sẽ được dịch sang chuỗi âm vị (ARPAbet phonemes) thông qua **Từ điển phát âm CMU**.
  - *Xử lý từ đồng âm:* Nếu 2 từ khác mặt chữ nhưng trùng âm vị ("their" và "there" đều là DH EH1 R) -> Đổi nhãn thành Đọc đúng (Equal), chống chấm sai oan.
  - *Phân loại lỗi phát âm:* Nếu độ tương đồng âm vị đạt 65% - 90% (như "think" và "sink") -> Gắn nhãn vàng "Cảnh báo phát âm gần giống" (Near-miss Pronunciation) thay vì báo sai hoàn toàn.
1.  **Đánh giá tương đồng ngữ nghĩa bằng Vector Embedding:**
  - Dùng mô hình all-MiniLM-L6-v2 mã hóa từng câu. Nếu điểm Cosine Similarity > 0.82, công nhận người dùng đã truyền đạt đúng ý câu đó.
### **3. Đánh giá tính khả thi & Hạn chế**
  - **Đánh giá:** Giải quyết triệt để 95% - 98% lỗi phân biệt phát âm và xử lý hoàn hảo từ đồng âm/viết tắt. Khả năng triển khai cực kỳ khả thi (10/10) bằng hệ sinh thái mã nguồn mở Python, tốc độ ánh sáng (mili-giây) và **chi phí 0 VNĐ**.
  - **Hạn chế:** Mô hình STT (Whisper) hay tự động bỏ qua từ đệm "um", "uh", nên phải cấy initial_prompt lúc gọi STT để ép mô hình không sửa lỗi này. Chưa chấm được lỗi phát âm chi tiết tới từng âm tố (Phoneme-level GOP).
-----
## **PHẦN III. PHÂN TÍCH NHỊP ĐIỆU & KHOẢNG DỪNG (PACING & TEMPO POST-PROCESSING)**
### **1. Mô tả bài toán**
Hệ thống cần chấm điểm trôi chảy (Fluency) và tính ổn định nhịp điệu (Tempo Stability) của người nói:
  - Đo lường **Speech Rate (WPM)**: Phát hiện việc đọc lướt học vẹt (> 175 WPM) hoặc vừa nói vừa dịch trong đầu (< 110 WPM).
  - **Phát hiện khoảng dừng (Pause Detection & Classification):** Phân biệt đâu là Khoảng ngừng nghệ thuật/Lấy hơi (Rhetorical/Breath Pause - ngay tại dấu câu) và đâu là Khoảng ngừng ngập ngừng do bí từ (Hesitation Pause - giữa câu văn, > 1.2s).
  - **Độ ổn định:** Phát hiện lối đọc giật cục, rời rạc từng chữ (Word-by-word choppy speech).
### **2. Giải pháp Kiến trúc: Gộp chung Request STT (0 Request phụ trội) & VAD Cục bộ**
Để ngăn chặn việc lãng phí tài nguyên mạng, hệ thống **KHÔNG** gọi mô hình Whisper Turbo chỉ để phân tích nhịp điệu. Toàn bộ khâu tính toán được đẩy về một Mô-đun Hậu kỳ (Post-processing Analytics Module) xử lý hai luồng dữ liệu độc lập:
  - **Luồng 1 - Kế thừa Timestamps (Từ Bài toán 1):** Hệ thống lấy luôn mảng Word-level Timestamps (start, end của từng từ) có sẵn từ kết quả JSON trả về của luồng STT chính (whisper-large-v3 hoặc API Thương mại). Việc này không tốn thêm 1 RPM nào.
  - **Luồng 2 - Xác thực Sóng âm bằng VAD (Local):** Sử dụng thư viện Silero VAD quét trực tiếp sóng âm trên máy chủ cục bộ (tốc độ thực thi siêu tốc trên CPU). Thuật toán này phân tích biên độ để dò ra những đoạn im lặng thật sự, bù trừ cho điểm yếu nhận diện sai tiếng ồn nền của các mô hình STT.
### **3. Triển khai Toán học Tính toán Chỉ số**
Sử dụng 2 luồng dữ liệu trên, mô-đun Hậu kỳ tiến hành chạy các phép toán Logic (Deterministic Rules):
  - Tính toán các chỉ số: **WPM** (Tốc độ tổng thể), **AR** (Tốc độ nhả chữ thực tế), **PTR** (Tỷ lệ thời gian thực nói), và **MLR** (Chiều dài trung bình một lượt nói liền mạch). Tính Dynamic WPM trên cửa sổ trượt 15 giây để vẽ đồ thị biến thiên tốc độ.
  - **Phân loại Khoảng dừng (Context-Aware):** Đối chiếu mốc thời gian khoảng lặng với vị trí dấu câu trong Script gốc:
  - Dừng 0.3s ≤ \Delta t ≤ 0.8s tại dấu phẩy / 0.5s ≤ \Delta t ≤ 1.5s tại dấu chấm -> *Ngắt nghỉ chuẩn xác (Effective Pause)*.
  - Dừng \Delta t > 1.2s giữa câu -> *Cảnh báo Ngập ngừng / Quên từ (Unnatural Hesitation)*.
  - \Delta t < 0.15s lướt qua dấu chấm -> *Cảnh báo Không ngắt câu (Rushing)*.
**Đánh giá:** Kiến trúc Hậu kỳ này giúp giải quyết 95% bài toán phân tích nhịp điệu với **chi phí mở rộng = 0** và hoàn toàn không làm gia tăng độ tải của mạng API. Hạn chế duy nhất là chưa đánh giá được trọng âm từ (Word Stress) hay ngữ điệu (Intonation/Monotone).
  - **Chi tiết Công cụ & Công thức Phân tích Nhịp điệu & Cao độ (Pitch):**
  - **Silero VAD & Librosa:** Silero VAD đảm nhận tách voice/unvoiced với độ chính xác cao ở mức milisecond. Librosa được dùng để trích xuất đường cong cao độ (F0 Contour - Fundamental Frequency) qua thuật toán PYIN, giúp theo dõi biến thiên ngữ điệu (Intonation range) và phát hiện giọng đọc đều đều (Monotone).
  - **Azure Pronunciation Assessment (Phân tích nâng cao):** Được tích hợp như một lớp tham chiếu chuyên sâu để đánh giá điểm phát âm (Accuracy), độ trôi chảy (Fluency), và độ hoàn thiện (Completeness) ở cấp độ âm tiết (Phoneme-level).
  - **Công thức tính toán các chỉ số cốt lõi:**
  - • **WPM (Words Per Minute):** Tổng số từ / Tổng thời gian ghi âm (phút).
  - • **AR (Articulation Rate):** Tổng số từ / (Tổng thời gian ghi âm - Tổng thời gian ngắt nghỉ) (phút).
  - • **PTR (Phonated Time Ratio):** (Thời gian phát âm thực tế / Tổng thời gian) × 100%.
  - • **MLR (Mean Length of Run):** Trung bình số từ nói được trong một chuỗi phát âm liên tục giữa hai khoảng dừng.
  - • **Biến thiên Cao độ F0 (Pitch Variation):** Độ lệch chuẩn của dải tần số F0 (Standard Deviation of F0 in Hz/Cents) để đánh giá độ phong phú của ngữ điệu.
-----
## **PHẦN IV. XÂY DỰNG TIÊU CHÍ ĐÁNH GIÁ (SCORING CRITERIA) VÀ CẤU TRÚC DỮ LIỆU**
### **1. Hệ thống Tiêu chí Đánh giá & Trọng số (Scoring Rubric)**
Điểm tổng hợp (Overall Score) được cấu thành từ 4 thành phần chính với trọng số tối ưu cho bài toán thuyết trình/luyện nói:
  - **Độ chính xác nội dung (Accuracy & Completeness - 40%):** Dựa trên chỉ số WER, tỉ lệ đọc đúng từ keyframes, không bỏ sót/thêm từ quá mức.
  - **Độ trôi chảy & Nhịp điệu (Fluency & Pacing - 30%):** Đánh giá dựa trên WPM chuẩn (130-160 WPM), tỉ lệ PTR, và phân bổ khoảng dừng hợp lý (giảm thiểu hesitation pauses).
  - **Phát âm & Âm điệu (Pronunciation & Intonation - 20%):** Tỉ lệ Near-miss pronunciation, độ rõ ràng âm tiết, và biến thiên dải cao độ F0.
  - **Tương đồng Ngữ nghĩa (Semantic Fidelity - 10%):** Điểm Cosine Similarity từ Sentence Embedding đảm bảo giữ vững ý nghĩa truyền đạt dù có diễn đạt lại.
### **2. Cấu trúc Dữ liệu Đầu ra (JSON Output Schema)**
Kết quả phân tích toàn diện được tổng hợp dưới dạng cấu trúc JSON chuẩn hóa:
``` JSON
{
  "overall_score": 88.5,
  "metrics": {
    "accuracy_score": 90.0,
    "fluency_score": 85.0,
    "pronunciation_score": 87.5,
    "semantic_score": 92.0
  },
  "pacing_analysis": {
    "wpm": 142.5,
    "articulation_rate": 158.0,
    "phonated_time_ratio": 0.82,
    "mean_length_run": 8.4,
    "f0_std_dev_hz": 24.6,
    "pauses": {
      "effective_pauses": 12,
      "hesitation_pauses": 2
    }
  },
  "alignment_details": [
    {
      "ref_word": "think",
      "hyp_word": "sink",
      "status": "near_miss",
      "phonetic_similarity": 0.78
    }
  ]
}
```


# CHALLENGE 3

# **BÁO CÁO KỸ THUẬT CHALLENGE 3: KIẾN TRÚC DỮ LIỆU, LƯU TRỮ & TIÊU CHÍ ĐÁNH GIÁ**
# **1. Xây dựng tiêu chí đánh giá**
Các tiêu chí đánh giá kết quả của 1 phiên luyện tập
*Lưu ý: base line là thông tin lấy từ việc phân tích file ghi âm đầu vào giọng thường của người dùng*
|  |  |  |  |  |
| :- | :- | :- | :- | :- |
| **Tiêu chí** | **Thông số/chỉ số để đánh giá** | **Cụ thể** | **Tương đối so với baseline** | **Công cụ** |
| **Độ rõ chữ/phát âm** | Tỷ lệ âm tiết đúng, CER/WER sau khi chuẩn hóa hai phía, danh sách từ điểm accuracy thấp, bỏ/thêm/thay từ | Chỉ kết luận "phát âm chưa rõ" khi cả STT sai lẫn accuracy thấp | Không (lấy từ dữ liệu model train) |  |
| **Tốc độ** | WPM và articulation rate | 130–160 WPM cho người học, cảnh báo dưới 110 hoặc trên 175. | 50 / 50 | WhisperX (mốc thời gian từ, ~±50 ms) và Azure PA (offset/duration) |
| **Ngắt nghỉ** | Số lần ngắt, độ dài ngắt trung vị theo loại dấu câu, tỷ lệ thời gian ngắt, vị trí ngắt (tại dấu câu, ranh giới cụm, hoặc giữa cụm = sai) | Một lần ngắt là ≥250–300 ms (tiếng Anh). Ngắt giữa cụm quá 500 ms thì cảnh báo. Dấu chấm khoảng 2–3,5× và dấu phẩy khoảng 1–2× khoảng nghỉ trung vị của chính người nói | Có | Silero VAD (khoảng lặng ≥250 ms) + mốc thời gian từ WhisperX/Azure |
| **Cao độ/ngữ điệu** | F0 đổi sang semitone: ST = 12·log2(F0/F0_ref), khoảng P10–P90, độ dốc cụm, mức nền cụm, hạ cuối câu, lên giọng cuối câu hỏi. | Dưới ~4 st là đều đều, 6–10 st là tốt. Hạ cuối câu trần thuật ≥3 st. | Có | Parselmouth (Praat) |
| **Nhấn mạnh** | Δst đỉnh F0, độ dài âm tiết nhấn (z-score) |  | Có | Parselmouth (Δst đỉnh F0, độ dài và cường độ âm tiết) + mốc thời gian |
| **Độ to** | Cường độ dB so với nền của chính người nói, z-score |  | Có | Parselmouth (cường độ dB) |
| **Từ đệm/Ngập ngừng** | Số đoạn VAD có tiếng nhưng không khớp từ nào, lặp từ. | Dưới ~4% số từ (hoặc dưới ~3 lần/phút) | Không | Silero VAD (đoạn có tiếng nhưng không khớp từ nào) + F0 từ Parselmouth |

## **Dựa trên lịch sử tập để đánh giá mức tiến bộ**
  - Kết quả của 1 lần tập luyện được quy đổi ra thang 10 tùy theo tiêu chí có được đánh giá dựa trên tương đối của baseline (ghi âm đầu vào giọng thường của người dùng) hay không, rồi cộng chia trung bình để ra điểm số của 1 phiên.
  - Tiến bộ nếu điểm của các phiên luyện tập tăng dần.
## **Dữ liệu đầu vào từ người dùng cho AI**
  - Giới tính
  - Accent mục tiêu
  - 1 đoạn ghi âm giọng bình thường ~ 30 giây
# **2. Định nghĩa mô hình dữ liệu**
  - **Profile lưu:** Thông tin cá nhân, accent mục tiêu.
  - **History lưu:**
      - Cuộc trò chuyện của 20 phiên luyện tập gần nhất cùng kết quả phiên luyện tập (bao gồm điểm trung bình và điểm theo từng tiêu chí).
      - File ghi âm của 20 phiên luyện tập gần nhất (mp3).
# **3. Lựa chọn công nghệ lưu trữ**
**Cơ sở dữ liệu đề xuất:** PostgreSQL thông qua dịch vụ quản lý Supabase, sử dụng bảng cơ sở dữ liệu để lưu trữ những file text và những URL dẫn đến những file audio trong Storage Bucket được liên kết. Ở mức miễn phí, Supabase cung cấp 500MB cho cơ sở dữ liệu.
**Một số loại dữ liệu cần có sẵn:**
  - **Bài tập & Kịch bản mẫu:** Các chủ đề luyện tập định sẵn theo mục tiêu (ví dụ: Elevator Pitch, Phỏng vấn xin việc, Bài phát biểu ngắn).
  - **Từ điển từ đệm (Filler Word Dictionaries):** Danh sách các từ thừa/từ đệm được phân loại theo từng ngôn ngữ ("um", "uh", "like") để thuật toán đối soát nhanh.
  - **Thang đo tiêu chuẩn (Scoring Rubrics):** Bảng thông số benchmark về tốc độ nói chuẩn (120–150 WPM), ngưỡng khoảng lặng bất thường (> 2 giây), và tiêu chí chấm điểm cấu trúc bài nói.
**Ước tính độ lớn dữ liệu:**
|  |  |  |  |
| :- | :- | :- | :- |
| **Độ dài phiên (min)** | **Audio WebM/Opus** | **MP3** | **CSDL (text)** |
| 1 | \~0.25 – 0.35 MB | \~0.9 – 1.0 MB | \~8 – 10 KB |
| 2 | \~0.50 – 0.70 MB | \~1.8 – 2.0 MB | \~13 – 15 KB |
| 3 | \~0.75 – 1.10 MB | \~2.7 – 3.0 MB | \~18 – 22 KB |

Để tiết kiệm không gian trong việc lưu trữ dữ liệu, ta nên nén âm thanh ngay tại trình duyệt, cấu hình MediaRecorder API trên trình duyệt ghi âm ở định dạng audio/webm;codecs=opus với audioBitsPerSecond: 32000 (32 kbps), giúp giảm dung lượng file audio xuống hơn 60% so với mặc định mà vẫn giữ nguyên chất lượng giọng nói đủ cho AI phân tích rõ ràng.
# **4. Độ rõ chữ, phát âm extra**
## **Cách làm theo tài liệu**
1.  Chạy STT (WhisperX hoặc Whisper large-v3) trên audio.
2.  **Chuẩn hóa cả hai phía:** Chữ thường, bỏ dấu câu, đọc số thành chữ, Unicode NFC. Doc2 cảnh báo nếu không chuẩn hóa thì sẽ "bắt lỗi" oan rất nhiều. Ví dụ PhoWhisper-small có WER 33,90% trên văn bản gốc nhưng chỉ 8,97% sau chuẩn hóa.
3.  Căn hai chuỗi bằng Levenshtein để đánh dấu **đúng, thay thế, bỏ sót, đọc thêm**.
4.  Chỉ số: Tỷ lệ từ đúng, WER/CER theo câu, danh sách từ sai.
**Ưu điểm:** Rẻ (WhisperX tự host gần như miễn phí), không phụ thuộc cloud, và cho ra mốc thời gian từ.
## **Giới hạn**
  - **Đo "độ dễ nhận dạng", không phải phát âm.** STT sai không đồng nghĩa người dùng phát âm sai. Lỗi có thể do tiếng ồn, mic hoặc giọng địa phương.
      - Chỉ nên kết luận "phát âm chưa rõ" khi **cả STT sai lẫn điểm accuracy thấp**.
      - Nếu chỉ dùng STT, hãy gọi chỉ số này là "độ dễ nhận dạng".
  - **Không chỉ ra được âm nào sai.** Chỉ biết từ nào bị nhận sai. Lỗi người Việt hay mắc như âm cuối, cụm phụ âm, /θ ð/ và trọng âm nằm ở cấp âm vị, STT thuần không bắt được.
  - **Whisper có xu hướng "sửa" cho đúng ngữ cảnh.** Whisper chép "ý định" thay vì chép nguyên văn: Nó lược bỏ um/uh và có thể sửa lặp từ.
      - Hệ quả: Đếm filler bị thiếu, và từ đọc sai nhẹ vẫn có thể được chép thành từ đúng, nên điểm bị cao ảo.
      - Cách giảm thiểu (suy luận của tôi): **Không** đưa văn bản mẫu vào prompt của Whisper. Nếu làm vậy nó sẽ bias về phía văn bản và che lỗi thật.
  - **Thiên lệch theo giọng.** WER vọt từ vài % lên hơn 50% khi điều kiện thu âm xấu. Với giọng Anh-Anh và Anh-Mỹ, độ chính xác cũng có thể khác nhau (suy luận, chưa có số liệu trong tài liệu).
## **Khuyến nghị cho nhóm**
  - Dùng STT + so văn bản làm **lớp 1**, tính cho tiêu chí "đúng từ, bỏ, thêm, lặp". Đây chính là chỉ số completeness và miscue.
  - Thêm **Azure PA** (accuracy theo từ và âm vị) làm **lớp 2** để có điểm phát âm thật. Azure cũng cho cờ Mispronunciation và cấp âm vị.
  - Quy tắc kết hợp: Kết luận phát âm chưa rõ khi cả hai lớp cùng báo; nếu chỉ một lớp báo thì gắn nhãn "cần kiểm tra".
  - Nếu muốn **bỏ Azure** để tiết kiệm hoặc tránh phụ thuộc cloud, STT thuần vẫn cho được tiêu chí này ở mức "dễ nhận dạng". Khi đó mất phần báo lỗi âm vị và chấm prosody, nên cần nói rõ trong UI. Doc3 xếp GOP tự xây vào loại nghiên cứu phụ, vì một repo thử trên wav2vec2 chỉ đạt Pearson r = 0,431 với điểm người chấm.