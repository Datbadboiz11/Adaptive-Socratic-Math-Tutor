"""Describe observable error traces, never infer a learner's latent misconception.

The original assessment stays immutable. A later correction rejects only the
claim that the *latest submission* still has that trace, not the earlier finding.
"""
from collections import defaultdict


def diagnoses(turns, opportunities):
    by_id = {op['opportunity_id']: op for op in opportunities}
    groups = defaultdict(list)
    for turn in turns:
        a = turn['assessment']
        if (turn['action'] == 'submit' and a['assessment_status'] == 'verified_incorrect'
                and a.get('misconception_candidate') and a.get('error_family') and a.get('evidence')
                and a.get('diagnosis_status') in ('suspected', 'supported')):
            groups[(a['error_family'], a['misconception_candidate'])].append(turn)

    def evidence(turn):
        a = turn['assessment']
        return dict(turn_id=turn['turn_id'], assessment_status=a['assessment_status'],
                    first_error_step=a.get('first_error_step'), facts=a.get('evidence', []))

    result = []
    for (family, candidate), matches in groups.items():
        # Count independent problem families, not retries on one assisted task.
        families = set()
        for turn in matches:
            op = by_id[turn['opportunity_id']]
            previous = turns[:turns.index(turn)]
            prior_work = [t for t in previous if t['opportunity_id'] == turn['opportunity_id']]
            if op['relation'] in ('initial', 'cross_family') and not any(
                    t['action'] == 'submit' or t.get('response', {}).get('counts_as_assistance', False)
                    for t in prior_work):
                families.add(op['family_id'])
        repeated = len(families) >= 2
        result.append(dict(error_family=family, hypothesis='Dấu vết bài làm khớp mẫu: ' + candidate,
            status='supported' if repeated else 'suspected', scope='observed_error_trace',
            explanation=('Dấu vết lỗi này xuất hiện ở ít nhất hai họ bài độc lập.' if repeated else
                         'Một lượt sai khớp mẫu lỗi đã biên soạn; chưa đủ bằng chứng để kết luận lỗi lặp lại.'),
            evidence=[evidence(t) for t in matches],
            review_action='Đối chiếu bước sai với phép biến đổi hợp lệ, rồi thử một bài thuộc họ khác.'))
        # Preserve the original suspected finding and attach a separate, narrow
        # counterclaim only when a verified correction followed it on that task.
        corrected = []
        for opportunity_id in dict.fromkeys(t['opportunity_id'] for t in matches):
            own = [t for t in turns if t['opportunity_id'] == opportunity_id and t['action'] == 'submit']
            if (own and own[-1]['assessment']['assessment_status'] == 'verified_correct'
                    and own[-1]['assessment'].get('evidence')):
                corrected.append(own[-1])
        if corrected:
            corrected_ids = {t['opportunity_id'] for t in corrected}
            result.append(dict(error_family=family,
                hypothesis='Bài làm mới nhất vẫn chứa dấu vết lỗi: ' + candidate,
                status='rejected', scope='latest_submission',
                explanation='Lượt sửa đã được xác minh đúng. Chỉ bác bỏ nhận định về bài làm mới nhất; không kết luận học sinh đã hết nhầm lẫn.',
                evidence=[evidence(t) for t in matches if t['opportunity_id'] in corrected_ids]
                         + [evidence(t) for t in corrected],
                review_action='Thử thêm một bài độc lập để kiểm tra khả năng vận dụng.'))
    return result


def parameter_source(version, parameters):
    if version == parameters['parameter_version']:
        return parameters['source']
    return 'Chưa có nguồn tham số lưu trữ cho phiên bản ' + str(version)
