"""Snapshot-scoped Neo4j graph; local DAG traversal is an explicit fallback."""
import base64
import hashlib
import json
import os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from app.retrieval_contracts import PrerequisitePath


def snapshot_id(registry):
    return hashlib.sha256(registry.model_dump_json().encode()).hexdigest()


def paths(registry, concept_id, *, authoring=False, max_depth=2):
    if max_depth not in (1, 2):
        raise ValueError('Only one or two prerequisite levels are allowed')
    concepts = {c.concept_id: c for c in registry.concepts}
    if concept_id not in concepts:
        raise ValueError('Unknown concept')
    result = []
    def visit(target, node_path, edge_path):
        if len(edge_path) == max_depth:
            return
        for edge in sorted(registry.edges, key=lambda e: e.edge_id):
            if edge.relation != 'PREREQUISITE_OF' or edge.target_concept_id != target:
                continue
            nodes = [edge.source_concept_id, *node_path]
            approved = (edge.review.status == 'human_approved' and
                        all(concepts[n].review.status == 'human_approved' and
                            concepts[n].alignment.status == 'human_approved' for n in nodes))
            if not authoring and not approved:
                continue
            edges = [edge.edge_id, *edge_path]
            # Review must cover the full path, not just its first edge.
            approved = approved and all(e.review.status == 'human_approved' for e in registry.edges if e.edge_id in edges)
            result.append(PrerequisitePath(concept_id=nodes[0], concept_ids=nodes, edge_ids=edges,
                                          depth=len(edges), review_status='human_approved' if approved else 'draft'))
            visit(nodes[0], nodes, edges)
    visit(concept_id, [concept_id], [])
    return sorted(result, key=lambda p: (p.depth, p.concept_id, p.edge_ids))


class GraphUnavailable(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Neo4jGraph:
    def __init__(self, url=None, password=None):
        self.url = (url or os.getenv('NEO4J_HTTP_URL', 'http://localhost:7474')).rstrip('/')
        parsed = urlparse(self.url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise GraphUnavailable('graph_configuration')
        self.password = password if password is not None else os.getenv('NEO4J_PASSWORD', '')
        self.username = os.getenv('NEO4J_USER', 'neo4j')
        if not self.password:
            raise GraphUnavailable('graph_unconfigured')

    def query(self, statement, parameters=None):
        body = json.dumps({'statement': ' '.join(statement.split()), 'parameters': parameters or {}}).encode()
        credential = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
        request = Request(self.url+'/db/neo4j/query/v2', data=body, method='POST',
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                   'Authorization': 'Basic '+credential})
        try:
            with build_opener(NoRedirect()).open(request, timeout=5) as response:
                document = json.loads(response.read(1024*1024))
            if document.get('errors'):
                raise GraphUnavailable('graph_query_failed')
            data = document['data']
            fields, values = data['fields'], data['values']
            if len(fields) != len(set(fields)) or any(len(v) != len(fields) for v in values):
                raise GraphUnavailable('graph_invalid_response')
            return [dict(zip(fields, row)) for row in values]
        except GraphUnavailable:
            raise
        except Exception:
            # No URL/password/server exception text escapes to responses or logs.
            raise GraphUnavailable('graph_unavailable') from None

    def import_registry(self, registry):
        sid = snapshot_id(registry)
        self.query('CREATE CONSTRAINT curriculum_snapshot_unique IF NOT EXISTS FOR (s:CurriculumSnapshot) REQUIRE s.snapshot_id IS UNIQUE')
        self.query('CREATE CONSTRAINT curriculum_concept_unique IF NOT EXISTS FOR (c:CurriculumConcept) REQUIRE (c.snapshot_id,c.concept_id) IS UNIQUE')
        nodes = [{'concept_id': c.concept_id, 'title': c.title, 'objective': c.objective,
                  'grade_levels': c.alignment.grade_levels, 'skill_ids': [s.skill_id for s in c.skills],
                  'review_status': c.review.status, 'alignment_status': c.alignment.status,
                  'content_version': registry.content_version, 'source_id': c.alignment.source_id,
                  'source': c.review.source, 'reviewer': c.review.human_reviewer,
                  'registry_record': c.model_dump_json()} for c in registry.concepts]
        edges = [{'edge_id': e.edge_id, 'source_id': e.source_concept_id, 'target_id': e.target_concept_id,
                  'relation': e.relation, 'review_status': e.review.status, 'rationale': e.rationale,
                  'curriculum_source_id': e.source_id, 'reviewer': e.review.human_reviewer,
                  'registry_record': e.model_dump_json()} for e in registry.edges]
        # One implicit transaction creates the entire snapshot. No deletes or overwrites of other snapshots.
        statement = '''MERGE (s:CurriculumSnapshot {snapshot_id:$snapshot})
          SET s.content_version=$version, s.registry_json=$registry, s.sources_json=$sources
          FOREACH (row IN $nodes | MERGE (c:CurriculumConcept {snapshot_id:$snapshot,concept_id:row.concept_id}) SET c += row)
          WITH s
        '''
        for relation in ('PREREQUISITE_OF', 'RELATED_TO', 'PART_OF'):
            statement += f'''CALL {{ WITH s UNWIND $edges AS row WITH row WHERE row.relation='{relation}'
              MATCH (a:CurriculumConcept {{snapshot_id:$snapshot,concept_id:row.source_id}}),
                    (b:CurriculumConcept {{snapshot_id:$snapshot,concept_id:row.target_id}})
              MERGE (a)-[r:{relation} {{edge_id:row.edge_id}}]->(b) SET r += row RETURN count(*) AS count_{relation} }}
            '''
        statement += 'RETURN s.snapshot_id AS snapshot_id'
        answer = self.query(statement, {'snapshot': sid, 'version': registry.content_version,
                           'registry': registry.model_dump_json(), 'sources': json.dumps([s.model_dump() for s in registry.sources]),
                           'nodes': nodes, 'edges': edges})
        if answer != [{'snapshot_id': sid}]:
            raise GraphUnavailable('graph_import_incomplete')
        return {'snapshot_id': sid, 'concepts': len(nodes), 'edges': len(edges), 'provider': 'neo4j'}

    def prerequisites(self, registry, concept_id, *, authoring=False):
        rows = self.query('''MATCH (s:CurriculumSnapshot {snapshot_id:$snapshot}) RETURN s.registry_json AS registry_json''',
                          {'snapshot': snapshot_id(registry)})
        if len(rows) != 1 or rows[0].get('registry_json') != registry.model_dump_json():
            raise GraphUnavailable('graph_snapshot_missing_or_stale')
        rows = self.query('''MATCH p=(a:CurriculumConcept)-[:PREREQUISITE_OF*1..2]->
                    (b:CurriculumConcept {snapshot_id:$snapshot,concept_id:$concept})
                    WHERE all(n IN nodes(p) WHERE n.snapshot_id=$snapshot)
                    RETURN [n IN nodes(p) | n.concept_id] AS concept_ids,
                           [r IN relationships(p) | r.edge_id] AS edge_ids''',
                          {'snapshot': snapshot_id(registry), 'concept': concept_id})
        # Verify full graph parity against the versioned registry before review filtering.
        expected = paths(registry, concept_id, authoring=True)
        actual = {(tuple(r['concept_ids']), tuple(r['edge_ids'])) for r in rows}
        if actual != {(tuple(p.concept_ids), tuple(p.edge_ids)) for p in expected}:
            raise GraphUnavailable('graph_parity_mismatch')
        return paths(registry, concept_id, authoring=authoring)


def prerequisites(registry, concept_id, *, authoring=False, provider=None):
    provider = provider or os.getenv('KG_PROVIDER', 'neo4j')
    if provider == 'registry':
        return paths(registry, concept_id, authoring=authoring), 'registry', None
    if provider != 'neo4j':
        raise ValueError('Unsupported graph provider')
    try:
        return Neo4jGraph().prerequisites(registry, concept_id, authoring=authoring), 'neo4j', None
    except (GraphUnavailable, KeyError, TypeError):
        return paths(registry, concept_id, authoring=authoring), 'registry_fallback', 'neo4j_unavailable_or_stale'


if __name__ == '__main__':
    import argparse
    from app.curriculum import load_curriculum
    parser = argparse.ArgumentParser(description='Import a versioned curriculum snapshot; no deletes.')
    parser.add_argument('--import-registry', action='store_true', required=True)
    parser.parse_args()
    registry, _ = load_curriculum()
    print(json.dumps(Neo4jGraph().import_registry(registry), ensure_ascii=False, indent=2))
