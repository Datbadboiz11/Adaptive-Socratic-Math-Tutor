"""Server-owned KB context and conservative, grounded response assembly (no API calls)."""
import os
from uuid import uuid4

from app.curriculum import CurriculumRegistry
from app.db import connect
from app.kb_contracts import KBChunk,KBRequest,KBScope
from app.kb_sync import active_snapshot,namespace_lock
from app.member2_contracts import RetrievalQuery
from app.retrieval import KBRetriever

VERSION = 'grounded-delivery-1.0.0'


def session_configuration(connection,canonical):
    mode = os.getenv('TUTOR_RAG_MODE','full').lower()
    if mode not in ('full','no_rag'):
        raise ValueError('TUTOR_RAG_MODE must be full or no_rag')
    # A proposed legacy mapping is not permission to import canonical KB content.
    if not canonical or mode=='no_rag':
        return 'no_rag',None
    return mode,active_snapshot(connection,'runtime')


def trusted_context(row,op):
    return {'mode':row['rag_mode'],'snapshot_id':row['kb_snapshot_id'],
            'session_id':str(row['session_id']),'opportunity_id':str(op['opportunity_id']),
            'problem_id':op['problem_id'],'concept_id':op['public_payload']['concept_id'],
            'skill_id':op['target_skill_id'],'family_id':op['family_id'],'source_group':op['source_group'],
            'difficulty':op['public_payload']['difficulty'],'content_version':op['content_version']}


def retrieve_context(state):
    """Known hint/explanation IDs use direct lookup; examples use metadata filters."""
    trusted = state.get('teaching',{})
    mode = trusted.get('mode','no_rag')
    receipt = {'version':VERSION,'mode':mode,'retrieved_refs':[], 'generator_refs':[],
               'delivered_refs':[],'fallback_reason':None}
    empty = {'retrieval':receipt,'teaching_context':[]}
    # No-RAG exits before reading a snapshot, registry, content cache or model.
    if mode!='full':
        return empty
    purpose = {'hint':'hint','explanation':'explanation','different_example':'example'}.get(state['policy']['action'])
    if not purpose:
        return empty
    snapshot = trusted.get('snapshot_id')
    if not snapshot:
        receipt['fallback_reason']='snapshot_unavailable'
        return empty
    try:
        with connect() as connection:
            row = connection.execute('''SELECT r.payload FROM kb_snapshots s JOIN kb_registry_versions r
                ON r.namespace=s.namespace AND r.registry_version=s.registry_version
                WHERE s.namespace='runtime' AND s.snapshot_id=%s''',(snapshot,)).fetchone()
        if not row:
            receipt['fallback_reason']='snapshot_unavailable'
            return empty
        registry = CurriculumRegistry.model_validate(row['payload'])
        concept = next(c for c in registry.concepts if c.concept_id==trusted['concept_id'])
        level = state['policy']['hint_level'] if purpose=='hint' else (3 if purpose=='example' else 0)
        scope = KBScope.from_registry(registry,namespace='runtime',session_id=trusted['session_id'],
            opportunity_id=trusted['opportunity_id'],allowed_targets=[{
                'concept_id':trusted['concept_id'],'skill_id':trusted['skill_id']}],
            allowed_hint_level=level,kb_snapshot_version=snapshot,active_problem_id=trusted['problem_id'],
            excluded_source_groups=[trusted['source_group']],excluded_family_ids=[trusted['family_id']],
            excluded_lineage_ids=[trusted['source_group'],trusted['family_id']],
            grade_levels=concept.alignment.grade_levels,difficulty=trusted['difficulty'])
        content_id = trusted['concept_id'] + ('-explanation' if purpose=='explanation' else f'-hint-{level}')
        request = KBRequest(request_id=uuid4(),scope=scope,method='metadata' if purpose=='example' else 'direct',
            query=RetrievalQuery(query=f'{purpose} {concept.title}',concept_id=trusted['concept_id'],
                target_skill_id=trusted['skill_id'],purpose=purpose,top_k=3 if purpose=='example' else 1),
            direct_ref=None if purpose=='example' else {
                'content_id':content_id,'content_version':trusted['content_version']})
        result = KBRetriever().retrieve(request)
        receipt.update(snapshot_id=snapshot,retrieval_id=str(result.retrieval_id),method=result.method,
                       fallback_reason=result.fallback_reason,concept_title=concept.title)
        # Never serve teaching content from a different approved source-pack revision.
        chunks = [chunk for chunk in result.chunks if chunk.provenance.pack_version==trusted['content_version']]
        receipt['retrieved_refs']=[{'content_id':ch.content_id,'content_version':ch.content_version} for ch in result.chunks]
        if not chunks:
            receipt['fallback_reason']=receipt['fallback_reason'] or 'pack_version_mismatch'
            return empty
        selected = chunks[0]
        receipt['generator_refs']=[{'content_id':selected.content_id,'content_version':selected.content_version}]
        # Only the chosen approved teaching projection reaches the assembler.
        return {'retrieval':receipt,'teaching_context':[selected.for_generator()],
                'selected_chunk':selected.model_dump(mode='json')}
    except Exception as error:
        receipt['fallback_reason']='retrieval_unavailable'
        receipt['error_class']=type(error).__name__
        return empty


def grounded_candidate(state):
    context = state.get('teaching_context',[])
    if context:
        return {'message':context[0]['text'],'response_source':'reviewed_kb'}
    return None


def validate_grounded_candidate(state,candidate):
    context = state.get('teaching_context',[])
    if not context or not state.get('selected_chunk'):
        return False
    chunk = KBChunk.model_validate(state['selected_chunk'])
    return (candidate=={'message':chunk.text,'response_source':'reviewed_kb'}
            and len(context)==1 and context[0]==chunk.for_generator()
            and state.get('retrieval',{}).get('mode')=='full')


def delivery_receipt(state):
    chunk = KBChunk.model_validate(state['selected_chunk'])
    return {'content_id':chunk.content_id,'content_version':chunk.content_version,
            'title':state.get('retrieval',{}).get('concept_title','Nội dung đã duyệt'), 'kind':chunk.kind}


def delivery_still_authorized(connection,prepared):
    if not prepared['response'].get('content_refs'):
        return True
    # Serialize the final delivery check with a concurrent approval withdrawal.
    namespace_lock(connection,'runtime')
    chunk=KBChunk.model_validate(prepared['selected_chunk'])
    row=connection.execute('''SELECT ch.content_hash FROM kb_snapshot_members m
        JOIN kb_chunks ch USING(namespace,content_id,content_version)
        WHERE m.namespace='runtime' AND m.snapshot_id=%s AND m.content_id=%s AND m.content_version=%s
        AND NOT EXISTS (SELECT 1 FROM kb_withdrawals w WHERE w.namespace=ch.namespace
            AND w.concept_id=ch.concept_id AND w.pack_version=ch.pack_version)''',
        (prepared['retrieval']['snapshot_id'],chunk.content_id,chunk.content_version)).fetchone()
    return bool(row and row['content_hash']==chunk.content_hash)
