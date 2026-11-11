# Fixture hợp đồng EvaluationResultV2

**DỮ LIỆU TỔNG HỢP, KHÔNG PHẢI KẾT QUẢ ĐO.** Không có audio thật, không có số đo.

Nguồn: fixture `run` trong `tests/audio_processing/test_pipeline_evaluate.py` với STT, VAD,
F0 và độ to giả. Các file là `EvaluationResultV2.model_dump(mode="json")` (ADR-004).

| File | Ca |
|---|---|
| `evaluation_ok.json` | Ca ok mặc định của `run` (đọc đúng kịch bản, không lỗi) |
| `evaluation_ok_mixed.json` | Ca ok có `sub`, `del`, `ins`, `near_miss`, một filler STT, pause `hesitation` và `forgot_word`, contour/loudness có cả số lẫn `null` |
| `evaluation_insufficient.json` | `insufficient_audio`, `reason = low_voiced_ratio` |

Sinh lại (sau khi đổi hợp đồng, rồi xem diff):

```
UPDATE_FIXTURES=1 uv run pytest -q tests/audio_processing/test_contract_fixture.py
```

Test JS (`mapResult`, giai đoạn E4) đọc các file này làm đầu vào.
