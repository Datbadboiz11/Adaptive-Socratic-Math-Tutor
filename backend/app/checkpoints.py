"""Native LangGraph saver with short PostgreSQL transactions, no pickle fallback."""
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from app.db import connect


class PostgresCheckpoints(BaseCheckpointSaver):
    def get_tuple(self, config):
        cfg = config['configurable']; thread = cfg['thread_id']; ns = cfg.get('checkpoint_ns','')
        with connect() as c:
            query = 'SELECT * FROM tutor_checkpoints WHERE thread_id=%s AND checkpoint_ns=%s'
            args = [thread,ns]
            if cfg.get('checkpoint_id'):
                query += ' AND checkpoint_id=%s'; args.append(cfg['checkpoint_id'])
            row = c.execute(query+' ORDER BY checkpoint_id DESC LIMIT 1',args).fetchone()
            if not row: return None
            writes = c.execute('''SELECT task_id,channel,value_type,value FROM tutor_checkpoint_writes
                WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s ORDER BY task_id,idx''',
                (thread,ns,row['checkpoint_id'])).fetchall()
        def configuration(cid):
            return {'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':cid}}
        return CheckpointTuple(config=configuration(row['checkpoint_id']),
            checkpoint=self.serde.loads_typed((row['checkpoint_type'],bytes(row['checkpoint']))),
            metadata=self.serde.loads_typed((row['metadata_type'],bytes(row['metadata']))),
            parent_config=configuration(row['parent_id']) if row['parent_id'] else None,
            pending_writes=[(w['task_id'],w['channel'],self.serde.loads_typed((w['value_type'],bytes(w['value'])))) for w in writes])

    def put(self, config, checkpoint, metadata, new_versions):
        cfg=config['configurable']; thread=cfg['thread_id']; ns=cfg.get('checkpoint_ns','')
        typ,value=self.serde.dumps_typed(checkpoint)
        mtyp,mvalue=self.serde.dumps_typed(metadata)
        with connect() as c:
            c.execute('''INSERT INTO tutor_checkpoints VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (thread_id,checkpoint_ns,checkpoint_id) DO NOTHING''',
                (thread,ns,checkpoint['id'],cfg.get('checkpoint_id'),typ,value,mtyp,mvalue))
        return {'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':checkpoint['id']}}

    def put_writes(self, config, writes, task_id, task_path=''):
        cfg=config['configurable']
        with connect() as c:
            for index,(channel,value) in enumerate(writes):
                idx=WRITES_IDX_MAP.get(channel,index); typ,data=self.serde.dumps_typed(value)
                conflict = 'DO UPDATE SET channel=EXCLUDED.channel,value_type=EXCLUDED.value_type,value=EXCLUDED.value' if idx < 0 else 'DO NOTHING'
                c.execute('''INSERT INTO tutor_checkpoint_writes VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (thread_id,checkpoint_ns,checkpoint_id,task_id,idx) '''+conflict,
                    (cfg['thread_id'],cfg.get('checkpoint_ns',''),cfg['checkpoint_id'],task_id,idx,channel,typ,data))

    def list(self, config, *, filter=None, before=None, limit=None):
        if config is None: raise ValueError('A thread must be specified')
        cfg=config['configurable']; args=[cfg['thread_id'],cfg.get('checkpoint_ns','')]
        query='SELECT checkpoint_id FROM tutor_checkpoints WHERE thread_id=%s AND checkpoint_ns=%s'
        if before:
            query+=' AND checkpoint_id<%s'; args.append(before['configurable']['checkpoint_id'])
        query+=' ORDER BY checkpoint_id DESC'
        with connect() as c: rows=c.execute(query,args).fetchall()
        count=0
        for row in rows:
            value=self.get_tuple({'configurable':{**cfg,'checkpoint_id':row['checkpoint_id']}})
            if filter and any(value.metadata.get(k)!=v for k,v in filter.items()): continue
            if limit is not None and count>=limit: break
            yield value; count+=1
