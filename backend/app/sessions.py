"""Durable internal-demo sessions; tutoring pipeline intentionally unavailable."""
import hashlib
import json
import logging
import secrets
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from app.db import connect, demo_enabled
from app.manage import digest
from app.contracts import CreateSession, TurnRequest, Assessment
from app.session_contracts import DemoLogin, Mutation, SaveDraft, SessionView, TurnResult, Report, ApiErrorBody

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


@router.get('/topics')
def topics(student=Depends(principal)):
    with connect() as connection:
        rows = connection.execute('''SELECT t.topic_id,t.title,count(p.problem_id)::int AS problem_count
            FROM topics t LEFT JOIN problems p USING(topic_id) GROUP BY t.topic_id ORDER BY t.topic_id''').fetchall()
    return [dict(row, tutoring_ready=False, internal_demo_available=row['problem_count'] > 0,
                 validator_available=tutor_enabled(), reason='Chế độ nội bộ; nội dung vẫn chờ duyệt chuyên môn.') for row in rows]


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
    return connection.execute('''SELECT DISTINCT ON (p.problem_id) p.* FROM problems p
        WHERE topic_id=%s AND NOT EXISTS
        (SELECT 1 FROM opportunities o WHERE o.session_id=%s AND o.problem_id=p.problem_id)
        ORDER BY p.problem_id,p.content_version DESC''', (row['topic_id'], row['session_id'])).fetchall()


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
        tutoring_enabled=row['tutoring_enabled'],
        mastery=connection.execute('SELECT skill_id,mastery,evidence_count,parameter_version FROM knowledge_states WHERE student_id=%s', (row['student_id'],)).fetchall() if row['tutoring_enabled'] else [],
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
        raise ApiError(409, 'state_conflict', 'Phiên đã thay đổi. Tải trạng thái mới trước khi tiếp tục.')
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
        problem = connection.execute('SELECT * FROM problems WHERE topic_id=%s ORDER BY problem_id,content_version DESC LIMIT 1', (body.topic_id,)).fetchone()
        if not problem:
            raise ApiError(409, 'content_not_ready', 'Chủ đề chưa có bài mẫu.')
        session_id, opportunity_id = uuid4(), uuid4()
        row = connection.execute('''INSERT INTO sessions(session_id,student_id,topic_id,current_opportunity_id,tutoring_enabled)
            VALUES (%s,%s,%s,%s,%s) RETURNING *''', (session_id, student, body.topic_id, opportunity_id,tutor_enabled())).fetchone()
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
def turn(session_id: UUID, body: TurnRequest, student=Depends(principal)):
    with connect() as connection:
        tutoring = session_row(connection,session_id,student)['tutoring_enabled']
    if tutoring:
        from app.tutor_service import process
        return process(session_id,body,student)
    def operation(connection):
        row = locked(connection, session_id, student, body)
        if row['status'] != 'active':
            raise ApiError(409, 'session_paused', 'Tiếp tục phiên trước khi gửi bài.')
        if row['current_opportunity_id'] != body.opportunity_id:
            raise ApiError(409, 'opportunity_conflict', 'Bài hiện tại đã thay đổi.')
        message = ('Đã lưu bài làm. Chưa xác minh đúng/sai: bộ chấm Toán được triển khai ở Phần 3.'
                   if body.action == 'submit' else 'Đã ghi nhận yêu cầu. Gia sư chưa được nối; chưa có gợi ý nào được cung cấp.')
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


def change_status(session_id, body, student, status):
    def operation(connection):
        row = locked(connection, session_id, student, body)
        return view(connection, row if row['status'] == status else advance(connection, row, status=status))
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
            raise ApiError(409, 'content_exhausted', 'Đã xem hết 6 bài trong phiên. Hãy kết thúc và xem báo cáo.')
        current = connection.execute('''SELECT o.*,p.family_id FROM opportunities o JOIN problems p USING(problem_id,content_version)
            WHERE opportunity_id=%s''', (row['current_opportunity_id'],)).fetchone()
        problem = choices[0]
        seen = connection.execute('SELECT 1 FROM opportunities WHERE student_id=%s AND problem_id=%s LIMIT 1', (student, problem['problem_id'])).fetchone()
        assisted = connection.execute('''SELECT 1 FROM opportunities o JOIN problems p USING(problem_id,content_version)
            WHERE o.session_id=%s AND o.assistance_level>0 AND (p.family_id=%s OR p.source_group=%s) LIMIT 1''',
            (session_id,problem['family_id'],problem['source_group'])).fetchone()
        relation = 'repeat' if seen else ('near_practice' if assisted else ('cross_family' if current['family_id'] != problem['family_id'] else 'initial'))
        opportunity_id = uuid4()
        add_opportunity(connection, row, problem, opportunity_id, current['ordinal']+1, relation, current['problem_id'])
        return view(connection, advance(connection, row, opportunity_id=opportunity_id))
    return mutation(student, f'{session_id}/next', body, operation)


def report(connection, row):
    counts = connection.execute('''SELECT count(*)::int AS viewed,
        count(*) FILTER (WHERE outcome='independent_correct')::int AS independent,
        count(*) FILTER (WHERE outcome='assisted_correct')::int AS assisted
        FROM opportunities WHERE session_id=%s''', (row['session_id'],)).fetchone()
    turns = turn_rows(connection, row['session_id'])
    observations = connection.execute('''SELECT count(*) AS n FROM observations
        WHERE opportunity_id IN (SELECT opportunity_id FROM opportunities WHERE session_id=%s)''', (row['session_id'],)).fetchone()['n']
    return Report(session_id=row['session_id'], status=row['status'], independent_correct=counts['independent'],
                  assisted_correct=counts['assisted'], valid_observations=observations,
                  unverified_submissions=sum(t['action']=='submit' and t['assessment']['assessment_status'] in ('unverified','needs_clarification') for t in turns),
                  submitted_turns=sum(t['action']=='submit' for t in turns), requested_hints=sum(t['action']=='request_hint' for t in turns),
                  problems_viewed=counts['viewed'], completed_at=row['completed_at'], timeline=turns,
                  tutoring_enabled=row['tutoring_enabled'],
                  mastery=connection.execute('''SELECT DISTINCT ON (o.skill_id) o.skill_id,o.mastery_after AS mastery,
                      (h.state_after->>'evidence_count')::int AS evidence_count,o.parameter_version
                      FROM observations o JOIN mastery_history h USING(observation_id)
                      JOIN opportunities p USING(opportunity_id) WHERE p.session_id=%s
                      ORDER BY o.skill_id,(h.state_after->>'evidence_count')::int DESC''',(row['session_id'],)).fetchall(),
                  limitations=['Bản thử nội bộ; nội dung/gợi ý chưa được người có chuyên môn duyệt.',
                               'BKT là ước lượng với tham số khởi tạo, chưa fit dataset hay hiệu chỉnh cho người học Việt Nam.',
                               'Chỉ theo dõi kỹ năng giải phương trình trong phạm vi hỗ trợ; chưa đủ bằng chứng cho các kỹ năng con.'] if row['tutoring_enabled'] else
                               ['Phiên cũ chỉ lưu trữ; tạo phiên mới để thử bộ chấm và gia sư.']).model_dump(mode='json')


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
        return report(connection, row)
    return mutation(student, f'{session_id}/finish', body, operation)
