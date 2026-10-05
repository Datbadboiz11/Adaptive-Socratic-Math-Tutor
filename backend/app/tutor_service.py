"""Durable preparation outside business transaction; atomic evidence + result commit."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.db import connect
from app.manage import digest
from app import knowledge, tutor


def context(c, row):
    op=c.execute('''SELECT o.*,p.private_payload,p.family_id,p.source_group FROM opportunities o
        JOIN problems p USING(problem_id,content_version) WHERE opportunity_id=%s''', (row['current_opportunity_id'],)).fetchone()
    observed=c.execute('SELECT 1 FROM observations WHERE opportunity_id=%s AND skill_id=%s',
                       (op['opportunity_id'],op['target_skill_id'])).fetchone() is not None
    near=c.execute('''SELECT 1 FROM opportunities o JOIN problems p USING(problem_id,content_version)
        WHERE o.session_id=%s AND o.opportunity_id<>%s AND o.assistance_level>0
        AND (p.family_id=%s OR p.source_group=%s) LIMIT 1''',
        (row['session_id'],op['opportunity_id'],op['family_id'],op['source_group'])).fetchone() is not None
    earlier=c.execute('''SELECT 1 FROM opportunities WHERE student_id=%s AND problem_id=%s
        AND (created_at,opportunity_id)<(%s,%s) LIMIT 1''',
        (row['student_id'],op['problem_id'],op['created_at'],op['opportunity_id'])).fetchone()
    prior_evidence=c.execute('''SELECT 1 FROM observations e JOIN opportunities o USING(opportunity_id)
        WHERE e.student_id=%s AND o.problem_id=%s AND o.opportunity_id<>%s LIMIT 1''',
        (row['student_id'],op['problem_id'],op['opportunity_id'])).fetchone()
    if earlier or prior_evidence: op['relation']='repeat'
    return op,observed,near


def persist_evidence(c, row, op, turn_id, a, allowed):
    if not allowed['eligible']: return None
    # Serialize mastery across DIFFERENT sessions for one student/skill as well.
    c.execute('''INSERT INTO knowledge_states(student_id,skill_id,mastery,evidence_count,parameter_version)
        VALUES (%s,%s,%s,0,%s) ON CONFLICT DO NOTHING''',
        (row['student_id'],op['target_skill_id'],knowledge.PARAMETERS['prior'],knowledge.VERSION))
    before=c.execute('SELECT * FROM knowledge_states WHERE student_id=%s AND skill_id=%s FOR UPDATE',
                     (row['student_id'],op['target_skill_id'])).fetchone()
    if before['parameter_version']!=knowledge.VERSION: raise ValueError('Parameter version migration required')
    correct=a['assessment_status']=='verified_correct'
    values=knowledge.update(before['mastery'],correct)
    oid=uuid4(); count=before['evidence_count']+1
    c.execute('''INSERT INTO observations(observation_id,student_id,opportunity_id,skill_id,turn_id,correct,
        prediction_before,mastery_before,mastery_after,parameter_version,protocol_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'g2-v1')''',
        (oid,row['student_id'],op['opportunity_id'],op['target_skill_id'],turn_id,correct,
         values['prediction_before'],values['mastery_before'],values['mastery_after'],knowledge.VERSION))
    c.execute('INSERT INTO mastery_history(observation_id,state_before,state_after) VALUES (%s,%s,%s)',
        (oid,Jsonb({'mastery':before['mastery'],'evidence_count':before['evidence_count'],'parameter_version':knowledge.VERSION}),
         Jsonb({'mastery':values['mastery_after'],'evidence_count':count,'parameter_version':knowledge.VERSION})))
    c.execute('UPDATE knowledge_states SET mastery=%s,evidence_count=%s WHERE student_id=%s AND skill_id=%s',
              (values['mastery_after'],count,row['student_id'],op['target_skill_id']))
    return {'observation_id':str(oid),**values,'evidence_count':count,'parameter_version':knowledge.VERSION}


def process(session_id, body, student):
    from app import sessions as service
    scope=f'{session_id}/turns'; key=(student,session_id,body.request_id); payload_hash=digest(body.model_dump(mode='json'))
    lease=uuid4(); prepared=None
    # A short claim prevents parallel model calls. Business state is unchanged here.
    with connect() as c:
        request_lock=int.from_bytes(hashlib.sha256(f'{student}:{scope}:{body.request_id}'.encode()).digest()[:8],'big',signed=True)
        c.execute("SET LOCAL lock_timeout = '5s'")
        c.execute('SELECT pg_advisory_xact_lock(%s)',(request_lock,))
        cached=c.execute('SELECT payload_hash,response FROM requests WHERE student_id=%s AND scope=%s AND request_id=%s',
                         (student,scope,body.request_id)).fetchone()
        if cached:
            if cached['payload_hash']!=payload_hash: raise service.ApiError(409,'idempotency_conflict','Request ID đã được dùng với nội dung khác.')
            return cached['response']
        row=service.locked(c,session_id,student,body)
        if row['status']!='active': raise service.ApiError(409,'session_paused','Tiếp tục phiên trước khi gửi bài.')
        if row['current_opportunity_id']!=body.opportunity_id: raise service.ApiError(409,'opportunity_conflict','Bài hiện tại đã thay đổi.')
        c.execute('''INSERT INTO turn_jobs VALUES (%s,%s,%s,%s,'preparing',%s,%s,NULL) ON CONFLICT DO NOTHING''',
                  (*key,payload_hash,lease,datetime.now(timezone.utc)+timedelta(seconds=45)))
        job=c.execute('SELECT * FROM turn_jobs WHERE student_id=%s AND session_id=%s AND request_id=%s FOR UPDATE',key).fetchone()
        if job['payload_hash']!=payload_hash: raise service.ApiError(409,'idempotency_conflict','Request ID đã được dùng với nội dung khác.')
        if job['status'] in ('ready','committed'): prepared=job['prepared']
        elif job['lease_id']!=lease:
            if job['lease_until']>datetime.now(timezone.utc):
                raise service.ApiError(503,'turn_in_progress','Lượt này đang được xử lý. Giữ nội dung và thử lại cùng yêu cầu.',True)
            c.execute('UPDATE turn_jobs SET lease_id=%s,lease_until=%s WHERE student_id=%s AND session_id=%s AND request_id=%s',
                      (lease,datetime.now(timezone.utc)+timedelta(seconds=45),*key))
        op,observed,near=context(c,row)
        used=c.execute('SELECT count(*) n FROM turn_jobs WHERE session_id=%s',(session_id,)).fetchone()['n']
        limit=min(20,max(0,int(os.getenv('LLM_MAX_CALLS_PER_SESSION','8'))))
        state={'problem':op['private_payload'],'opportunity':{
            k:op[k] for k in ('target_skill_id','assistance_level','relation','no_progress_count','best_progress')},
            'observed':observed,'near':near,'action':body.action,'steps':body.steps,'llm_allowed':used<=limit}
    thread=f'{session_id}:{body.request_id}'
    if prepared is None:
        try:
            prepared=tutor.run_graph(state,thread)
        except Exception as error:
            service.log.error('pipeline failure session=%s request=%s type=%s',session_id,body.request_id,type(error).__name__)
            with connect() as c:
                c.execute('UPDATE turn_jobs SET lease_until=now() WHERE student_id=%s AND session_id=%s AND request_id=%s AND lease_id=%s',(*key,lease))
            raise service.ApiError(503,'pipeline_unavailable','Lượt xử lý bị gián đoạn. Bài làm được giữ; hãy thử lại cùng yêu cầu.',True) from None
        with connect() as c:
            updated=c.execute('''UPDATE turn_jobs SET status='ready',prepared=%s
                WHERE student_id=%s AND session_id=%s AND request_id=%s AND lease_id=%s RETURNING request_id''',
                (Jsonb(prepared),*key,lease)).fetchone()
            if not updated: raise service.ApiError(503,'turn_in_progress','Lượt đang được khôi phục. Hãy thử lại cùng yêu cầu.',True)

    def operation(c):
        row=service.locked(c,session_id,student,body)
        if row['status']!='active' or row['current_opportunity_id']!=body.opportunity_id:
            raise service.ApiError(409,'state_conflict','Trạng thái đã thay đổi trong khi xử lý. Tải lại phiên.')
        # Global skill lock also makes repeat/evidence checks across sessions consistent.
        lock_id=int.from_bytes(hashlib.sha256(f'knowledge:{student}:{state["opportunity"]["target_skill_id"]}'.encode()).digest()[:8],'big',signed=True)
        c.execute('SELECT pg_advisory_xact_lock(%s)',(lock_id,))
        op,observed,near=context(c,row)
        a=prepared['validation']['assessment']; policy=prepared['policy']; response=prepared['response']
        allowed=knowledge.eligibility(a,op,observed,near)
        turn_id=uuid4()
        pipeline={'pipeline_version':tutor.PIPELINE_VERSION,'parameter_version':knowledge.VERSION,'protocol_version':'g2-v1',
            'validation':prepared['validation'],'eligibility':allowed,'policy':{k:v for k,v in policy.items() if k!='candidates'},
            'checkpoint_thread':thread,'nodes':['validate','eligibility','policy','respond','guard','commit']}
        c.execute('''INSERT INTO turns(turn_id,session_id,opportunity_id,request_id,action,steps,assessment,response,pipeline)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (turn_id,session_id,body.opportunity_id,body.request_id,body.action,Jsonb(body.steps),Jsonb(a),Jsonb(response),Jsonb(pipeline)))
        evidence=persist_evidence(c,row,op,turn_id,a,allowed)
        # Outcome records the FIRST correct completion, not a later supported retry.
        outcome=('assisted_correct' if op['assistance_level'] else 'independent_correct') if a['assessment_status']=='verified_correct' else None
        c.execute('''UPDATE opportunities SET draft=%s,assistance_level=%s,no_progress_count=%s,best_progress=%s,
            outcome=COALESCE(outcome,%s),relation=%s WHERE opportunity_id=%s''',
            ('\n'.join(body.steps) if body.action=='submit' else op['draft'],policy['hint_level'],policy['no_progress_count'],
             policy['best_progress'],outcome,op['relation'],body.opportunity_id))
        c.execute('INSERT INTO decisions(decision_id,turn_id,action,reason,pipeline_version) VALUES (%s,%s,%s,%s,%s)',
                  (uuid4(),turn_id,policy['action'],a['reason_code'],tutor.PIPELINE_VERSION))
        c.execute("UPDATE turn_jobs SET status='committed' WHERE student_id=%s AND session_id=%s AND request_id=%s",key)
        updated=service.advance(c,row)
        service.log.info('tutor turn=%s session=%s opportunity=%s request=%s assessment=%s eligibility=%s source=%s',
                         turn_id,session_id,body.opportunity_id,body.request_id,a['assessment_status'],allowed['reason'],response['response_source'])
        return {'session':service.view(c,updated),'assessment':a,'eligibility':allowed,'observation':evidence,
                'message':response['message'],'response_source':response['response_source'],'tutor':response}
    return service.mutation(student,scope,body,operation)
