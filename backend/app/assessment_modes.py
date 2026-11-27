"""Hằng số chế độ chấm của Member 2, tách riêng để validator không phải nạp ``member2_runtime``.

Worker validator (``app.math_worker``) chạy trong tiến trình con có giới hạn thời gian. Nạp
``member2_runtime`` kéo theo psycopg, curriculum và content_authoring (hơn 1 giây), làm mọi lần chấm
bị hết giờ trên máy chậm. ``member2_runtime`` vẫn xuất lại hai tên này như cũ.
"""

ASSESSMENT_MODE = 'member2-final-answer-1.0.0'
TASK_KINDS = frozenset({
    'numeric', 'evaluate', 'polynomial', 'quadratic_vertex', 'fraction_compare', 'number_conversion',
    'factored_polynomial', 'rational_operation', 'word_equation', 'quadratic_roots', 'linear_elimination',
    'function_domain', 'quadratic_axis', 'exponent_numeric',
    # Chấm đáp án cuối x = số (E01); bước giải vẫn do validator theo bước của Member 1 chấm.
    'linear_equation',
    # Member 3 (app.member3_math)
    'linear_inequality', 'log_value', 'exp_log_equation', 'vieta', 'quadratic_monotonic', 'slope_intercept',
    'special_factoring', 'product_equation',
})
