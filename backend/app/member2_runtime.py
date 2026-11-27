"""Approved Member 2 demo content and its exact problem capability."""
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from app.assessment_modes import ASSESSMENT_MODE, TASK_KINDS  # noqa: F401 (xuất lại)
from app.content_authoring import ContentReview
from app.curriculum import CurriculumRegistry, PilotBank
from app.manage import digest, seed_problem
from app.member2_foundation import load_workboard
from app.member2_problem_contract import project_curriculum_problem

RELEASE = Path(__file__).resolve().parents[2] / 'content/authoring/batches/member2-original.v2'


@dataclass(frozen=True)
class DemoProblem:
    topic_id: str
    title: str
    source_group: str
    public: dict
    private: dict
    content_hash: str


@lru_cache(maxsize=1)
def demo_catalog():
    manifest = json.loads((RELEASE / 'manifest.json').read_bytes())
    files = {name: (RELEASE / name).read_bytes() for name in ('registry-snapshot.json', 'approved-bank.json')}
    if (manifest['basis'] != 'user_confirmed_approval' or manifest['review_status'] != 'human_approved'
            or manifest['revision'] != 'M2-ORIG02'
            or manifest['files_sha256'] != {name: sha256(raw).hexdigest() for name, raw in files.items()}):
        raise ValueError('Member 2 release approval or checksum mismatch')
    registry = CurriculumRegistry.model_validate_json(files['registry-snapshot.json'])
    bank = PilotBank.model_validate_json(files['approved-bank.json'])
    assignment = next(item for item in load_workboard().assignments if item.owner == 'Member 2')
    assigned = set(assignment.concept_ids)
    if (registry.content_version != bank.content_version or bank.content_version != manifest['content_version']
            or {pack.concept_id for pack in bank.packs} != assigned or set(manifest['packs']) != assigned):
        raise ValueError('Member 2 release is outside the confirmed scope')
    concepts = {concept.concept_id: concept for concept in registry.concepts}
    catalog = {}
    for pack in bank.packs:
        concept = concepts[pack.concept_id]
        item = manifest['packs'][pack.concept_id]
        review = ContentReview.model_validate(item['review'])
        if (concept.review.status != 'human_approved' or concept.alignment.status != 'human_approved'
                or pack.review.status != 'human_approved' or len(pack.problems) != 6
                or review.decision != 'approved' or review.reviewer != pack.review.human_reviewer
                or review.reviewed_at != pack.review.reviewed_at or review.review_id != manifest['record_id']
                or item['approved_pack_sha256'] != digest(pack.model_dump(mode='json'))):
            raise ValueError(f'Unsupported or unapproved demo pack: {pack.concept_id}')
        skills = {skill.skill_id for skill in concept.skills}
        allowed = set(concept.authoring_task_kinds) & TASK_KINDS
        for problem in pack.problems:
            if problem.primary_skill_id not in skills or problem.task.kind not in allowed:
                raise ValueError(f'Problem falls outside the demo validator scope: {problem.case_id}')
            public = project_curriculum_problem(problem, pack.content_version).model_dump(mode='json')
            if problem.task.kind == 'word_equation' and '=' in public['task']['expression']:
                raise ValueError('A word problem cannot publish its target equation')
            private = {**public, 'assessment_mode': ASSESSMENT_MODE,
                       'hint_ladder': [hint.text for hint in pack.hints],
                       'review': pack.review.model_dump(mode='json')}
            catalog[(problem.case_id, pack.content_version)] = DemoProblem(
                f'TOPIC-{pack.concept_id}', concept.title, problem.source_group, public, private, digest(private),
            )
    return catalog


def approved_demo_problem(row):
    """Match the persisted identity and public/private digests to the approved release."""
    item = demo_catalog().get((row['problem_id'], row['content_version']))
    if (item and row['topic_id'] == item.topic_id and row['review_status'] == 'human_approved'
            and row['primary_skill_id'] == item.public['primary_skill_id'] and row['content_hash'] == item.content_hash
            and row['public_payload'] == item.public):
        return item
    return None


@lru_cache(maxsize=1)
def demo_topic_ids():
    return frozenset(item.topic_id for item in demo_catalog().values())


def seed_member2(connection):
    catalog = demo_catalog()
    topics = {item.topic_id: item.title for item in catalog.values()}
    connection.execute('SELECT pg_advisory_xact_lock(791202)')
    for topic_id, title in topics.items():
        connection.execute('INSERT INTO topics VALUES (%s,%s) ON CONFLICT DO NOTHING', (topic_id, title))
    inserted = sum(seed_problem(connection, item.topic_id, item.source_group, item.public, item.private)
                   for item in catalog.values())
    return {'topics': len(topics), 'problems': len(catalog), 'inserted': inserted}
