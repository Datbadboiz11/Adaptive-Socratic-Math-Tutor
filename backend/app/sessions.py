"""Durable internal-demo sessions; tutoring pipeline intentionally unavailable."""
import hashlib
import json
import logging
import secrets
import os
from datetime import datetime, timedelta, timezone
from itertools import groupby
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from app.db import connect, demo_enabled
from app.manage import digest
from app.contracts import CreateSession, TurnRequest, Assessment
from app.member2_problem_contract import demo_validator_task
from app.member2_runtime import approved_demo_problem, demo_topic_ids
from app.session_contracts import DemoLogin, Mutation, SaveDraft, SessionView, TurnResult, Report, ApiErrorBody, TopicView, TeachingTurnRequest

router = APIRouter(prefix='/api/v1', responses={status: {'model': ApiErrorBody} for status in (401, 403, 404, 409, 422, 503)})
log = logging.getLogger('mo.sessions')


def tutor_enabled():
    return os.getenv('TUTOR_ENABLED','false').lower() == 'true'


class ApiError(Exception):
    def __init__(self, status, code, message, retryable=False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def require_demo():
    if not demo_enabled():
        raise ApiError(403, 'demo_disabled', 'Chức năng thử nội bộ đang tắt. Chưa có xác thực sản phẩm.')


def principal(authorization: str | None = Header(default=None)):
    require_demo()
    if not authorization or not authorization.startswith('Bearer '):
        raise ApiError(401, 'unauthorized', 'Hãy chọn hồ sơ demo để bắt đầu.')
    token = authorization[7:]
    if len(token) > 200:
        raise ApiError(401, 'unauthorized', 'Phiên demo không hợp lệ.')
    with connect() as connection:
        row = connection.execute('SELECT student_id FROM demo_tokens WHERE token_hash=%s AND expires_at>now()',
                                 (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:
        raise ApiError(401, 'unauthorized', 'Phiên demo hết hạn. Hãy chọn lại hồ sơ.')
    return row['student_id']


@router.get('/demo/profiles')
def profiles():
    require_demo()
    with connect() as connection:
        return connection.execute('SELECT student_id,display_name FROM profiles ORDER BY student_id').fetchall()


@router.post('/demo/login')
def login(body: DemoLogin):
    require_demo()
    token = secrets.token_urlsafe(32)
    with connect() as connection:
        profile = connection.execute('SELECT student_id,display_name FROM profiles WHERE student_id=%s', (body.demo_profile_id,)).fetchone()
        if not profile:
            raise ApiError(404, 'not_found', 'Không tìm thấy hồ sơ demo.')
        connection.execute('DELETE FROM demo_tokens WHERE expires_at<now()')
        connection.execute('INSERT INTO demo_tokens VALUES (%s,%s,%s)',
                           (hashlib.sha256(token.encode()).hexdigest(), body.demo_profile_id, datetime.now(timezone.utc)+timedelta(hours=24)))
    return {'access_token': token, 'profile': profile, 'mode': 'internal_demo'}


@router.get('/me')
def me(student=Depends(principal)):
    with connect() as connection:
        return connection.execute('SELECT student_id,display_name FROM profiles WHERE student_id=%s', (student,)).fetchone()


def problem_validator_task(row):
    if row['topic_id'] in demo_topic_ids():
        problem = approved_demo_problem(row)
        return problem.public['task']['kind'] if problem else None
    return demo_validator_task(row['topic_id'], row['public_payload'], row['primary_skill_id'])


def topic_validator_tasks(topic_id, problems, enabled):
    if not enabled or (topic_id in demo_topic_ids() and len(problems) != 6):
        return []
    kinds = {problem_validator_task(problem) for problem in problems}
    return sorted(kinds) if None not in kinds else []


@router.get('/topics', response_model=list[TopicView])
def topics(student=Depends(principal)):
    with connect() as connection:
        rows = connection.execute('''SELECT t.topic_id,t.title,p.problem_id,p.content_version,p.primary_skill_id,
                p.public_payload,p.review_status,p.content_hash
            FROM topics t LEFT JOIN (
                SELECT DISTINCT ON (topic_id,problem_id) topic_id,problem_id,content_version,primary_skill_id,
                    public_payload,review_status,content_hash
                FROM problems ORDER BY topic_id,problem_id,content_version DESC
            ) p USING(topic_id) ORDER BY t.topic_id''').fetchall()
    enabled = tutor_enabled()
    results = []
    for (topic_id, title), group in groupby(rows, key=lambda row: (row['topic_id'], row['title'])):
        problems = [row for row in group if row['primary_skill_id'] is not None]
        kinds = topic_validator_tasks(topic_id, problems, enabled)
        approved_demo = topic_id in demo_topic_ids()
        reason = 'Chủ đề chưa có bộ chấm khả dụng trong demo nội bộ.'
        if kinds:
            reason = ('Pack đã duyệt. Bộ chấm kiểm tra dòng kết quả cuối.' if approved_demo
                      else 'Có bộ chấm phương trình bậc nhất trong demo nội bộ.')
        results.append(TopicView(topic_id=topic_id, title=title, problem_count=len(problems),
            tutoring_ready=approved_demo and bool(kinds), internal_demo_available=bool(kinds if approved_demo else problems),
            validator_available=bool(kinds), validator_task_kinds=kinds, reason=reason))
    return results


def session_row(connection, session_id, student, lock=False):
    row = connection.execute('SELECT * FROM sessions WHERE session_id=%s AND student_id=%s' + (' FOR UPDATE' if lock else ''),
                             (session_id, student)).fetchone()
    if not row:
        raise ApiError(404, 'not_found', 'Không tìm thấy phiên thuộc hồ sơ hiện tại.')
    return row


def turn_rows(connection, session_id):
    return connection.execute('''SELECT turn_id,opportunity_id,request_id,action,steps,assessment,response,created_at
        FROM turns WHERE session_id=%s ORDER BY created_at,turn_id''', (session_id,)).fetchall()


def candidate_rows(connection, row):
    # Distinct problems, not new content versions of an already-used problem.
    choices = connection.execute('''SELECT DISTINCT ON (p.problem_id) p.* FROM problems p
        WHERE topic_id=%s AND NOT EXISTS
        (SELECT 1 FROM opportunities o WHERE o.session_id=%s AND o.problem_id=p.problem_id)
        ORDER BY p.problem_id,p.content_version DESC''', (row['topic_id'], row['session_id'])).fetchall()
    return [p for p in choices if problem_validator_task(p)] if row['tutoring_enabled'] else choices


def view(connection, row):
    current = connection.execute('''SELECT o.*,p.public_payload,p.review_status FROM opportunities o
        JOIN problems p USING(problem_id,content_version) WHERE opportunity_id=%s''', (row['current_opportunity_id'],)).fetchone()
    count = connection.execute('SELECT count(*) AS n FROM observations WHERE opportunity_id IN (SELECT opportunity_id FROM opportunities WHERE session_id=%s)', (row['session_id'],)).fetchone()['n']
    return SessionView(
        session_id=row['session_id'], student_id=row['student_id'], status=row['status'],
        state_version=row['state_version'], current_opportunity_id=row['current_opportunity_id'],
        problem=current['public_payload'], draft=current['draft'], hint_level=current['assistance_level'],
        created_at=row['created_at'], review_status=current['review_status'], relation=current['relation'],
        turns=turn_rows(connection, row['session_id']), eligible_observations=count,
        available_next=len(candidate_rows(connection, row)),
        assistance_received=current['assistance_received'],rag_mode=row['rag_mode'],
        tutoring_enabled=row['tutoring_enabled'],
        mastery=connection.execute('SELECT skill_id,mastery,evidence_count,parameter_version FROM knowledge_states WHERE student_id=%s', (row['student_id'],)).fetchall()
            if row['tutoring_enabled'] and row['topic_id'] not in demo_topic_ids() else [],
    ).model_dump(mode='json')


def mutation(student, scope, body, operation):
    # Serialize same-key retries, then lock the session for cross-key writes.
    request_hash = digest(body.model_dump(mode='json'))
    lock_id = int.from_bytes(hashlib.sha256(f'{student}:{scope}:{body.request_id}'.encode()).digest()[:8], 'big', signed=True)
    with connect() as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (lock_id,))
        cached = connection.execute('SELECT payload_hash,response FROM requests WHERE student_id=%s AND scope=%s AND request_id=%s', (student, scope, body.request_id)).fetchone()
        if cached:
            if cached['payload_hash'] != request_hash:
                raise ApiError(409, 'idempotency_conflict', 'Request ID đã được dùng với nội dung khác.')
            return cached['response']
        result = jsonable_encoder(operation(connection))
        connection.execute('INSERT INTO requests(student_id,scope,request_id,payload_hash,response) VALUES (%s,%s,%s,%s,%s)',
                           (student, scope, body.request_id, request_hash, Jsonb(result)))
    log.info('committed request=%s scope=%s', body.request_id, scope)
    return result


def locked(connection, session_id, student, body, allow_completed=False):
    row = session_row(connection, session_id, student, lock=True)
    if allow_completed and row['status'] == 'completed':
        return row
    if row['state_version'] != body.expected_state_version:
        raise ApiError(409, 'state_conflict', 'Phiên đã thay đổi. Tải trạng thái mới rồi gửi lại thao tác.', True)
    if row['status'] == 'completed':
        raise ApiError(409, 'session_completed', 'Phiên đã kết thúc; bài làm đã lưu chỉ có thể xem lại.')
    return row


def advance(connection, row, status=None, opportunity_id=None):
    return connection.execute('''UPDATE sessions SET state_version=state_version+1,updated_at=now(),
        status=%s,current_opportunity_id=%s,completed_at=CASE WHEN %s='completed' THEN now() ELSE completed_at END
        WHERE session_id=%s RETURNING *''',
        (status or row['status'], opportunity_id or row['current_opportunity_id'], status or row['status'], row['session_id'])).fetchone()


def add_opportunity(connection, row, problem, opportunity_id, ordinal, relation, related=None):
    connection.execute('''INSERT INTO opportunities(opportunity_id,session_id,student_id,problem_id,content_version,
        target_skill_id,relation,related_problem_id,ordinal) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (opportunity_id, row['session_id'], row['student_id'], problem['problem_id'], problem['content_version'],
         problem['primary_skill_id'], relation, related, ordinal))


@router.post('/sessions', response_model=SessionView, status_code=201)
def create(body: CreateSession, student=Depends(principal)):
    if body.demo_profile_id != student:
        raise ApiError(403, 'forbidden', 'Hồ sơ không khớp phiên đăng nhập demo.')
    def operation(connection):
        problems = connection.execute('''SELECT DISTINCT ON (problem_id)
            problem_id,content_version,topic_id,primary_skill_id,public_payload,review_status,content_hash FROM problems
            WHERE topic_id=%s ORDER BY problem_id,content_version DESC''', (body.topic_id,)).fetchall()
        if not problems:
            raise ApiError(409, 'content_not_ready', 'Chủ đề chưa có bài mẫu.')
        problem = problems[0]
        tutoring = bool(topic_validator_tasks(body.topic_id, problems, tutor_enabled()))
        if body.topic_id in demo_topic_ids() and not tutoring:
            raise ApiError(409, 'content_not_ready', 'Chủ đề hiện chưa có đủ bài đã duyệt và bộ chấm khả dụng.')
        session_id, opportunity_id = uuid4(), uuid4()
        from app.teaching_runtime import session_configuration
        mode,snapshot=session_configuration(connection,body.topic_id in demo_topic_ids() and tutoring)
        row = connection.execute('''INSERT INTO sessions(session_id,student_id,topic_id,current_opportunity_id,tutoring_enabled,rag_mode,kb_snapshot_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *''', (session_id, student, body.topic_id, opportunity_id,tutoring,mode,snapshot)).fetchone()
        seen = connection.execute('SELECT 1 FROM opportunities WHERE student_id=%s AND problem_id=%s LIMIT 1', (student, problem['problem_id'])).fetchone()
        add_opportunity(connection, row, problem, opportunity_id, 1, 'repeat' if seen else 'initial')
        return view(connection, row)
    return mutation(student, 'create_session', body, operation)


@router.get('/sessions')
def history(student=Depends(principal)):
    with connect() as connection:
        return connection.execute('''SELECT session_id,status,state_version,created_at,updated_at,
            topic_id FROM sessions WHERE student_id=%s ORDER BY updated_at DESC LIMIT 100''', (student,)).fetchall()


@router.get('/sessions/{session_id}', response_model=SessionView)
def read(session_id: UUID, student=Depends(principal)):
    with connect() as connection:
        # Lock keeps state and child rows consistent with concurrent mutations.
        return view(connection, session_row(connection, session_id, student, lock=True))


@router.put('/sessions/{session_id}/draft', response_model=SessionView)
def save_draft(session_id: UUID, body: SaveDraft, student=Depends(principal)):
    def operation(connection):
        row = locked(connection, session_id, student, body)
        if row['status'] != 'active':
            raise ApiError(409, 'session_paused', 'Tiếp tục phiên trước khi sửa bài.')
        connection.execute('UPDATE opportunities SET draft=%s WHERE opportunity_id=%s', (body.draft, row['current_opportunity_id']))
        return view(connection, advance(connection, row))
    return mutation(student, f'{session_id}/draft', body, operation)


@router.post('/sessions/{session_id}/turns', response_model=TurnResult)
def turn(session_id: UUID, body: TeachingTurnRequest,
         idempotency_key: UUID | None = Header(default=None, alias='Idempotency-Key'),
         request_id_header: UUID | None = Header(default=None, alias='X-Request-ID'),
         student=Depends(principal)):
    header_request_id = idempotency_key or request_id_header
    if idempotency_key and request_id_header and idempotency_key != request_id_header:
        raise ApiError(409, 'idempotency_conflict', 'Hai header request ID không khớp nhau.')
    if body.request_id and header_request_id and body.request_id != header_request_id:
        raise ApiError(409, 'idempotency_conflict', 'Request ID trong header không khớp nội dung yêu cầu.')
    effective_request_id = body.request_id or header_request_id
    if effective_request_id is None:
        raise ApiError(422, 'invalid_input', 'Cần request_id trong body hoặc Idempotency-Key/X-Request-ID header.')
    if body.request_id is None:
        body = body.model_copy(update={'request_id': effective_request_id})
    with connect() as connection:
        row = session_row(connection,session_id,student)
        tutoring = row['tutoring_enabled']
        if tutoring:
            problem = connection.execute('''SELECT p.topic_id,p.problem_id,p.content_version,p.primary_skill_id,
                    p.public_payload,p.review_status,p.content_hash
                FROM opportunities o JOIN problems p USING(problem_id,content_version)
                WHERE o.opportunity_id=%s''', (row['current_opportunity_id'],)).fetchone()
            tutoring = bool(problem and problem_validator_task(problem))
        if row['topic_id'] in demo_topic_ids() and not tutoring:
            raise ApiError(409, 'content_not_ready', 'Bài này hiện không có bộ chấm khả dụng.')
    if tutoring:
        from app.tutor_service import process
        return process(session_id,body,student)
    def operation(connection):
        row = locked(connection, session_id, student, body)
        if row['status'] != 'active':
            raise ApiError(409, 'session_paused', 'Tiếp tục phiên trước khi gửi bài.')
        if row['current_opportunity_id'] != body.opportunity_id:
            raise ApiError(409, 'opportunity_conflict', 'Bài hiện tại đã thay đổi.')
        message = ('Đã lưu bài làm. Phiên này chưa có bộ chấm để xác minh đúng/sai.'
                   if body.action == 'submit' else 'Đã ghi nhận yêu cầu. Phiên này chưa có gợi ý.')
        assessment = Assessment(assessment_id=uuid4(), assessment_status='unverified', reason_code='cannot_verify',
                                verification_method='none', validator_version='not-integrated').model_dump(mode='json')
        turn_id = uuid4()
        response = {'message': message, 'response_source': 'system_unavailable'}
        connection.execute('''INSERT INTO turns(turn_id,session_id,opportunity_id,request_id,action,steps,assessment,response)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', (turn_id, session_id, body.opportunity_id, body.request_id, body.action, Jsonb(body.steps), Jsonb(assessment), Jsonb(response)))
        if body.action == 'submit':
            connection.execute('UPDATE opportunities SET draft=%s WHERE opportunity_id=%s', ('\n'.join(body.steps), body.opportunity_id))
        connection.execute('INSERT INTO decisions(decision_id,turn_id,action,reason,pipeline_version) VALUES (%s,%s,%s,%s,%s)',
                           (uuid4(), turn_id, 'defer', 'pipeline_not_integrated', 'phase2-storage-only'))
        updated = advance(connection, row)
        log.info('stored turn=%s session=%s opportunity=%s request=%s', turn_id, session_id, body.opportunity_id, body.request_id)
        return {'session': view(connection, updated), 'assessment': assessment,
                'eligibility': {'eligible': False, 'reason': 'not_verified'}, 'message': message, 'response_source': 'system_unavailable'}
    return mutation(student, f'{session_id}/turns', body, operation)


def save_checkpoint(connection, row):
    opportunity = connection.execute('''SELECT opportunity_id,draft,assistance_level,relation,
        no_progress_count,best_progress FROM opportunities WHERE opportunity_id=%s FOR UPDATE''',
        (row['current_opportunity_id'],)).fetchone()
    if not opportunity:
        raise ApiError(409, 'state_conflict', 'Không thể lưu checkpoint vì bài hiện tại đã thay đổi.')
    snapshot = {
        'status': row['status'],
        'state_version': row['state_version'],
        'current_opportunity_id': str(opportunity['opportunity_id']),
        'draft': opportunity['draft'],
        'assistance_level': opportunity['assistance_level'],
        'relation': opportunity['relation'],
        'no_progress_count': opportunity['no_progress_count'],
        'best_progress': opportunity['best_progress'],
    }
    connection.execute('''INSERT INTO session_checkpoints(session_id,state_version,snapshot)
        VALUES (%s,%s,%s) ON CONFLICT (session_id) DO UPDATE SET
        state_version=EXCLUDED.state_version,snapshot=EXCLUDED.snapshot,saved_at=now()''',
        (row['session_id'], row['state_version'], Jsonb(snapshot)))


def restore_checkpoint(connection, row):
    checkpoint = connection.execute('SELECT state_version,snapshot FROM session_checkpoints WHERE session_id=%s FOR UPDATE',
                                    (row['session_id'],)).fetchone()
    if not checkpoint:
        return
    snapshot = checkpoint['snapshot']
    if (checkpoint['state_version'] != row['state_version']
            or snapshot.get('current_opportunity_id') != str(row['current_opportunity_id'])):
        raise ApiError(409, 'checkpoint_conflict', 'Checkpoint đã cũ. Tải lại trạng thái phiên rồi thử tiếp.', True)
    connection.execute('''UPDATE opportunities SET draft=%s,assistance_level=%s,relation=%s,
        no_progress_count=%s,best_progress=%s WHERE opportunity_id=%s''',
        (snapshot['draft'], snapshot['assistance_level'], snapshot['relation'],
         snapshot['no_progress_count'], snapshot['best_progress'], row['current_opportunity_id']))


def change_status(session_id, body, student, status):
    def operation(connection):
        row = locked(connection, session_id, student, body)
        if status == 'active' and row['status'] == 'paused':
            restore_checkpoint(connection, row)
        updated = row if row['status'] == status else advance(connection, row, status=status)
        if status == 'paused':
            save_checkpoint(connection, updated)
        return view(connection, updated)
    return mutation(student, f'{session_id}/{status}', body, operation)


@router.post('/sessions/{session_id}/pause', response_model=SessionView)
def pause(session_id: UUID, body: Mutation, student=Depends(principal)):
    return change_status(session_id, body, student, 'paused')


@router.post('/sessions/{session_id}/resume', response_model=SessionView)
def resume(session_id: UUID, body: Mutation, student=Depends(principal)):
    return change_status(session_id, body, student, 'active')


@router.post('/sessions/{session_id}/next', response_model=SessionView)
def next_problem(session_id: UUID, body: Mutation, student=Depends(principal)):
    def operation(connection):
        row = locked(connection, session_id, student, body)
        if row['status'] != 'active':
            raise ApiError(409, 'session_paused', 'Tiếp tục phiên trước khi đổi bài.')
        choices = candidate_rows(connection, row)
        if not choices:
            raise ApiError(409, 'content_exhausted', 'Đã hết bài khả dụng trong phiên. Hãy kết thúc và xem báo cáo.')
        current = connection.execute('''SELECT o.*,p.family_id FROM opportunities o JOIN problems p USING(problem_id,content_version)
            WHERE opportunity_id=%s''', (row['current_opportunity_id'],)).fetchone()
        problem = choices[0]
        seen = connection.execute('SELECT 1 FROM opportunities WHERE student_id=%s AND problem_id=%s LIMIT 1', (student, problem['problem_id'])).fetchone()
        assisted = connection.execute('''SELECT 1 FROM opportunities o JOIN problems p USING(problem_id,content_version)
            WHERE o.session_id=%s AND (o.assistance_received OR o.assistance_level>0) AND (p.family_id=%s OR p.source_group=%s) LIMIT 1''',
            (session_id,problem['family_id'],problem['source_group'])).fetchone()
        relation = 'repeat' if seen else ('near_practice' if assisted else ('cross_family' if current['family_id'] != problem['family_id'] else 'initial'))
        example_near=connection.execute('''SELECT 1 FROM teaching_deliveries d JOIN turns t USING(turn_id)
            WHERE t.session_id=%s AND (d.family_id=%s OR d.source_group=%s OR %s=ANY(d.lineage_ids)) LIMIT 1''',
            (session_id,problem['family_id'],problem['source_group'],problem['source_group'])).fetchone()
        if example_near and not seen: relation='near_practice'
        opportunity_id = uuid4()
        add_opportunity(connection, row, problem, opportunity_id, current['ordinal']+1, relation, current['problem_id'])
        return view(connection, advance(connection, row, opportunity_id=opportunity_id))
    return mutation(student, f'{session_id}/next', body, operation)


def report(connection, row):
    frozen=connection.execute('SELECT payload FROM session_reports WHERE session_id=%s',(row['session_id'],)).fetchone()
    if frozen:
        return frozen['payload']
    counts = connection.execute('''SELECT count(*)::int AS viewed,
        count(*) FILTER (WHERE outcome='independent_correct')::int AS independent,
        count(*) FILTER (WHERE outcome='assisted_correct')::int AS assisted,
        count(*) FILTER (WHERE outcome='independent_correct' AND relation IN ('repeat','near_practice'))::int AS repeated
        FROM opportunities WHERE session_id=%s''', (row['session_id'],)).fetchone()
    turns = turn_rows(connection, row['session_id'])
    observations = connection.execute('''SELECT count(*) AS n FROM observations
        WHERE opportunity_id IN (SELECT opportunity_id FROM opportunities WHERE session_id=%s)''', (row['session_id'],)).fetchone()['n']
    canonical = row['topic_id'] in demo_topic_ids()
    repeated = counts['repeated']
    limitations = ['Phiên cũ chỉ lưu trữ; tạo phiên mới để thử bộ chấm và gia sư.']
    if canonical:
        limitations = ['Bộ chấm xác minh dòng kết quả cuối theo dạng bài. Các dòng trước được lưu trong nhật ký.',
                       'Kết quả của phiên này chưa dùng để ước lượng mức độ thành thạo BKT.']
    elif row['tutoring_enabled']:
        limitations = ['Bản thử nội bộ; nội dung/gợi ý chưa được người có chuyên môn duyệt.',
                       'BKT là ước lượng với tham số khởi tạo, chưa fit dataset hay hiệu chỉnh cho người học Việt Nam.',
                       'Chỉ theo dõi kỹ năng giải phương trình trong phạm vi hỗ trợ; chưa đủ bằng chứng cho các kỹ năng con.']
    return Report(session_id=row['session_id'], status=row['status'], independent_correct=counts['independent'] - repeated,
                  repeat_or_near_correct=repeated, assessment_scope='final_answer' if canonical else 'solution_steps',
                  assisted_correct=counts['assisted'], valid_observations=observations,
                  unverified_submissions=sum(t['action']=='submit' and t['assessment']['assessment_status'] in ('unverified','needs_clarification') for t in turns),
                  submitted_turns=sum(t['action']=='submit' for t in turns), requested_hints=sum(t['action']=='request_hint' for t in turns),
                  problems_viewed=counts['viewed'], completed_at=row['completed_at'], timeline=turns,
                  tutoring_enabled=row['tutoring_enabled'],
                  mastery=[] if canonical else connection.execute('''WITH session_skills AS (
                      SELECT DISTINCT target_skill_id AS skill_id FROM opportunities WHERE session_id=%s
                  ), session_evidence AS (
                      SELECT DISTINCT ON (e.skill_id) e.skill_id,e.mastery_after AS mastery,
                          (h.state_after->>'evidence_count')::int AS evidence_count,e.parameter_version
                      FROM observations e JOIN mastery_history h USING(observation_id)
                      JOIN opportunities o USING(opportunity_id) WHERE o.session_id=%s
                      ORDER BY e.skill_id,(h.state_after->>'evidence_count')::int DESC
                  )
                  SELECT s.skill_id,e.mastery,COALESCE(e.evidence_count,0)::int AS evidence_count,e.parameter_version,
                      CASE WHEN COALESCE(e.evidence_count,0)<3 THEN 'insufficient_data' ELSE 'estimated' END AS status
                  FROM session_skills s LEFT JOIN session_evidence e USING(skill_id) ORDER BY s.skill_id''',
                      (row['session_id'],row['session_id'])).fetchall(),
                  skills=skill_reports(connection,row,turns),limitations=limitations).model_dump(mode='json')


def skill_reports(connection,row,turns):
    from app.knowledge import PARAMETERS
    from app.report_diagnoses import diagnoses, parameter_source
    opportunities=connection.execute('''SELECT o.*,p.public_payload,p.family_id,t.title FROM opportunities o
        JOIN problems p USING(problem_id,content_version) JOIN topics t ON t.topic_id=p.topic_id
        WHERE o.session_id=%s ORDER BY o.ordinal''',(row['session_id'],)).fetchall()
    reports=[]
    for skill in sorted({op['target_skill_id'] for op in opportunities}):
        own=[op for op in opportunities if op['target_skill_id']==skill]
        ids={op['opportunity_id'] for op in own}
        own_turns=[turn for turn in turns if turn['opportunity_id'] in ids]
        skill_turns=[turn for turn in own_turns if turn['action']=='submit']
        evidence=connection.execute('''SELECT e.*,h.state_before,h.state_after FROM observations e
            JOIN opportunities o USING(opportunity_id) JOIN mastery_history h USING(observation_id)
            WHERE o.session_id=%s AND e.skill_id=%s ORDER BY (h.state_after->>'evidence_count')::int''',
            (row['session_id'],skill)).fetchall()
        wrong=[t for t in skill_turns if t['assessment']['assessment_status']=='verified_incorrect']
        first,last=(evidence[0],evidence[-1]) if evidence else (None,None)
        before=first['state_before']['evidence_count'] if first else None
        after=last['state_after']['evidence_count'] if last else None
        repeated=sum(op['outcome']=='independent_correct' and op['relation'] in ('repeat','near_practice') for op in own)
        reports.append(dict(concept_id=own[0]['public_payload']['concept_id'],skill_id=skill,title=own[0]['title'],
            problems_viewed=len(own),independent_correct=sum(op['outcome']=='independent_correct' for op in own)-repeated,
            assisted_correct=sum(op['outcome']=='assisted_correct' for op in own),repeat_or_near_correct=repeated,
            unverified_submissions=sum(t['assessment']['assessment_status'] in ('unverified','needs_clarification') for t in skill_turns),
            incorrect_submissions=len(wrong),observation_ids=[e['observation_id'] for e in evidence],
            mastery_before=first['state_before']['mastery'] if first else None,
            mastery_after=last['state_after']['mastery'] if last else None,
            evidence_count_before=before,evidence_count_after=after,
            other_session_observations=max(0,after-before-len(evidence)) if evidence else 0,
            parameter_version=last['parameter_version'] if last else None,
            parameter_source=parameter_source(last['parameter_version'],PARAMETERS) if evidence else None,
            updated_at=last['created_at'] if last else None,
            review_reason='Em có thể thử thêm một bài ở họ khác để kiểm tra cách làm, vì phiên này có bài chưa đúng.' if wrong else None,
            evidence_turn_ids=[t['turn_id'] for t in wrong], diagnoses=diagnoses(own_turns,own)))
    return reports


@router.get('/sessions/{session_id}/report', response_model=Report)
def get_report(session_id: UUID, student=Depends(principal)):
    with connect() as connection:
        return report(connection, session_row(connection, session_id, student, lock=True))


@router.post('/sessions/{session_id}/finish', response_model=Report)
def finish(session_id: UUID, body: Mutation, student=Depends(principal)):
    def operation(connection):
        row = locked(connection, session_id, student, body, allow_completed=True)
        if row['status'] != 'completed':
            row = advance(connection, row, status='completed')
        result=report(connection, row)
        connection.execute('INSERT INTO session_reports(session_id,payload) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                           (session_id,Jsonb(result)))
        return result
    return mutation(student, f'{session_id}/finish', body, operation)
