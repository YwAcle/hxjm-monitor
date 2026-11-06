"""只读检索新轨迹身份表：历史特征、临时身份和真实轨迹记录。

检索对象是样本管线写入的 ``feature`` 向量，而不是登记照片重新编码的结果。
本模块不写数据库，也不创建身份或轨迹。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

_SCHEMA = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class FeatureSpaceInfo:
    id: str
    object_type: str
    dimensions: int
    metric: str
    enabled: bool


@dataclass(frozen=True)
class IdentityCandidate:
    identity_id: str
    identity_kind: str
    display_no: int | None
    display_name: str | None
    employee_id: str | None
    similarity: float
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    compatible_count: int


@dataclass(frozen=True)
class IdentityOccurrence:
    identity_id: str
    tracklet_id: str
    source_id: str | None
    camera_name: str | None
    first_observed_at: datetime
    last_observed_at: datetime
    asset_id: str | None
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    storage_key: str | None = None
    content_type: str | None = None


def _schema(schema: str) -> str:
    if not _SCHEMA.fullmatch(schema):
        raise ValueError("不支持的数据库 schema 名称")
    return schema


def _keys(schema: str) -> str:
    """把临时身份解析到已登记身份；没有有效关联时保留临时身份自身。"""
    return f'''
        keys AS (
            SELECT i.id AS raw_id,
                   COALESCE(l.registered_identity_id, i.id) AS identity_id
            FROM "{schema}".identity i
            LEFT JOIN "{schema}".identity_link l
              ON l.temporary_identity_id = i.id
             AND l.valid_to IS NULL
             AND l.expires_at > now()
             AND EXISTS (
                 SELECT 1
                 FROM "{schema}".identity r
                 WHERE r.id = l.registered_identity_id
                   AND r.enabled
                   AND (r.expires_at IS NULL OR r.expires_at > now())
             )
            WHERE i.enabled
              AND (i.expires_at IS NULL OR i.expires_at > now())
        )
    '''


def default_feature_space(engine, schema: str) -> str | None:
    """返回第一个启用的特征空间 ID；仅用于只读自检。"""
    schema = _schema(schema)
    with engine.connect() as conn:
        value = conn.execute(text(f'''
            SELECT id
            FROM "{schema}".feature_space
            WHERE enabled
            ORDER BY created_at, id
            LIMIT 1
        ''')).scalar()
    return str(value) if value is not None else None


def get_feature_space(engine, schema: str, feature_space_id: str) -> FeatureSpaceInfo | None:
    schema = _schema(schema)
    with engine.connect() as conn:
        row = conn.execute(text(f'''
            SELECT id, object_type, dimensions, metric, enabled
            FROM "{schema}".feature_space
            WHERE id = :space
        '''), {"space": feature_space_id}).mappings().first()
    if row is None:
        return None
    return FeatureSpaceInfo(
        id=str(row["id"]),
        object_type=str(row["object_type"]),
        dimensions=int(row["dimensions"]),
        metric=str(row["metric"]),
        enabled=bool(row["enabled"]),
    )


def count_searchable_features(engine, schema: str, feature_space_id: str) -> int:
    """统计当前可在检索中使用的历史轨迹特征数量。"""
    schema = _schema(schema)
    with engine.connect() as conn:
        value = conn.execute(text(f'''
            SELECT count(*) AS count
            FROM "{schema}".feature f
            JOIN "{schema}".tracklet t ON t.id = f.tracklet_id
            WHERE f.feature_space_id = :space
              AND f.state = 'ready'
              AND f.embedding IS NOT NULL
              AND (f.expires_at IS NULL OR f.expires_at > now())
              AND t.expires_at > now()
        '''), {"space": feature_space_id}).scalar_one()
    return int(value)


def search_identities(engine, schema: str, feature_space_id: str, query_vector: str,
                      limit: int) -> list[IdentityCandidate]:
    """按余弦相似度返回身份候选，每个身份只保留最相似的一条轨迹特征。

    ``query_vector`` 是 pgvector 文本字面量，例如 ``[0.1,0.2,...]``。
    """
    schema = _schema(schema)
    sql = text(f'''
        WITH {_keys(schema)}, scored AS (
            SELECT k.identity_id,
                   t.id AS tracklet_id,
                   1 - (f.embedding <=> CAST(:query AS vector)) AS similarity
            FROM "{schema}".feature f
            JOIN "{schema}".tracklet t ON t.id = f.tracklet_id
            LEFT JOIN LATERAL (
                SELECT a.identity_id
                FROM "{schema}".track_identity_assignment a
                WHERE a.tracklet_id = f.tracklet_id
                  AND a.valid_to IS NULL
                  AND a.expires_at > now()
                ORDER BY a.valid_from DESC, a.id
                LIMIT 1
            ) a ON true
            JOIN keys k ON k.raw_id = COALESCE(a.identity_id, f.identity_id)
            WHERE f.feature_space_id = :space
              AND f.state = 'ready'
              AND f.embedding IS NOT NULL
              AND (f.expires_at IS NULL OR f.expires_at > now())
              AND t.expires_at > now()
        ), best AS (
            SELECT DISTINCT ON (identity_id)
                   identity_id, tracklet_id, similarity
            FROM scored
            ORDER BY identity_id, similarity DESC, tracklet_id
        )
        SELECT b.identity_id::text AS identity_id,
               b.similarity,
               i.identity_kind, i.display_no, i.display_name, i.employee_id,
               i.first_seen_at, i.last_seen_at,
               count(*) OVER () AS compatible_count
        FROM best b
        JOIN "{schema}".identity i ON i.id = b.identity_id
        WHERE b.similarity IS NOT NULL
        ORDER BY b.similarity DESC, b.identity_id
        LIMIT :limit
    ''')
    with engine.connect() as conn:
        rows = conn.execute(sql, {
            "query": query_vector,
            "space": feature_space_id,
            "limit": int(limit),
        }).mappings().all()
    return [
        IdentityCandidate(
            identity_id=str(row["identity_id"]),
            identity_kind=str(row["identity_kind"]),
            display_no=(int(row["display_no"]) if row["display_no"] is not None else None),
            display_name=row["display_name"],
            employee_id=row["employee_id"],
            similarity=max(-1.0, min(1.0, float(row["similarity"]))),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            compatible_count=int(row["compatible_count"]),
        )
        for row in rows
    ]


def list_occurrences(engine, schema: str, identity_ids: list[str],
                     per_identity: int = 5) -> list[IdentityOccurrence]:
    """返回候选身份的真实轨迹出现记录，按最后出现时间倒序截断。"""
    schema = _schema(schema)
    if not identity_ids:
        return []
    sql = text(f'''
        WITH {_keys(schema)}, occ_rows AS (
            SELECT DISTINCT ON (k.identity_id, t.id)
                   k.identity_id,
                   t.id AS tracklet_id,
                   t.source_id,
                   c.name AS camera_name,
                   t.first_observed_at,
                   t.last_observed_at,
                   s.asset_id,
                   s.storage_key,
                   s.content_type
            FROM keys k
            JOIN "{schema}".track_identity_assignment a
              ON a.identity_id = k.raw_id
             AND a.valid_to IS NULL
             AND a.expires_at > now()
            JOIN "{schema}".tracklet t
              ON t.id = a.tracklet_id
             AND t.expires_at > now()
            LEFT JOIN "{schema}".camera c ON c.id = t.source_id
            LEFT JOIN LATERAL (
                SELECT sample.asset_id,
                       asset.storage_key,
                       asset.content_type
                FROM "{schema}".sample sample
                LEFT JOIN "{schema}".media_asset asset ON asset.id = sample.asset_id
                WHERE sample.tracklet_id = t.id
                  AND sample.purpose = 'history'
                  AND sample.available
                  AND (sample.expires_at IS NULL OR sample.expires_at > now())
                ORDER BY sample.created_at, sample.id
                LIMIT 1
            ) s ON true
            WHERE k.identity_id = ANY(:identity_ids)
            ORDER BY k.identity_id, t.id, a.valid_from DESC, a.id
        ), ranked AS (
            SELECT occ_rows.*,
                   row_number() OVER (
                       PARTITION BY identity_id
                       ORDER BY last_observed_at DESC, tracklet_id
                   ) AS rn,
                   count(*) OVER (PARTITION BY identity_id) AS occurrence_count,
                   min(first_observed_at) OVER (PARTITION BY identity_id) AS first_seen_at,
                   max(last_observed_at) OVER (PARTITION BY identity_id) AS last_seen_at
            FROM occ_rows
        )
        SELECT identity_id::text AS identity_id,
               tracklet_id::text AS tracklet_id,
               source_id::text AS source_id,
               camera_name,
               first_observed_at, last_observed_at,
               asset_id::text AS asset_id,
               storage_key, content_type,
               occurrence_count, first_seen_at, last_seen_at
        FROM ranked
        WHERE rn <= :per_identity
        ORDER BY identity_id, rn
    ''')
    with engine.connect() as conn:
        rows = conn.execute(sql, {
            "identity_ids": [str(value) for value in identity_ids],
            "per_identity": int(per_identity),
        }).mappings().all()
    return [
        IdentityOccurrence(
            identity_id=str(row["identity_id"]),
            tracklet_id=str(row["tracklet_id"]),
            source_id=(str(row["source_id"]) if row["source_id"] is not None else None),
            camera_name=row["camera_name"],
            first_observed_at=row["first_observed_at"],
            last_observed_at=row["last_observed_at"],
            asset_id=(str(row["asset_id"]) if row["asset_id"] is not None else None),
            storage_key=row["storage_key"],
            content_type=row["content_type"],
            occurrence_count=int(row["occurrence_count"]),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
        )
        for row in rows
    ]


def sample_feature(engine, schema: str, feature_space_id: str) -> dict | None:
    """只读取一条可检索特征，用于离线自检；不改变任何记录。"""
    schema = _schema(schema)
    with engine.connect() as conn:
        row = conn.execute(text(f'''
            SELECT f.id::text AS feature_id,
                   f.tracklet_id::text AS tracklet_id,
                   f.identity_id::text AS feature_identity_id,
                   a.identity_id::text AS assignment_identity_id,
                   f.embedding::text AS embedding
            FROM "{schema}".feature f
            JOIN "{schema}".tracklet t ON t.id = f.tracklet_id
            LEFT JOIN "{schema}".track_identity_assignment a
              ON a.tracklet_id = f.tracklet_id
             AND a.valid_to IS NULL
             AND a.expires_at > now()
            WHERE f.feature_space_id = :space
              AND f.state = 'ready'
              AND f.embedding IS NOT NULL
              AND (f.expires_at IS NULL OR f.expires_at > now())
              AND t.expires_at > now()
              AND COALESCE(a.identity_id, f.identity_id) IS NOT NULL
            ORDER BY f.created_at, f.id
            LIMIT 1
        '''), {"space": feature_space_id}).mappings().first()
    return dict(row) if row is not None else None