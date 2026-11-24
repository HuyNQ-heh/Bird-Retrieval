"""MySQL persistence. Every published mask path refers to an immutable PNG."""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import numpy as np
import pymysql


ROOT = Path(__file__).resolve().parent
SELECT_FEATURES = """
    SELECT i.image_id, i.image_path, i.mask_path, f.color_feature, f.texture_feature, f.shape_feature
    FROM images i JOIN image_features f USING (image_id)
"""


def connect(initialize=False):
    load_dotenv(ROOT / ".env", encoding="utf-8-sig", interpolate=False)
    name = os.environ.get("MYSQL_DATABASE", "")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name) or not os.environ.get("MYSQL_USER"):
        raise ValueError("Configure MYSQL_DATABASE and MYSQL_USER in .env")
    options = dict(host=os.getenv("MYSQL_HOST", "127.0.0.1"),
                   port=int(os.getenv("MYSQL_PORT", "3306")), user=os.environ["MYSQL_USER"],
                   password=os.getenv("MYSQL_PASSWORD", ""), charset="utf8mb4",
                   autocommit=True, connect_timeout=5)
    try:
        conn = pymysql.connect(database=name, **options)
    except pymysql.err.OperationalError as exc:
        if not initialize or exc.args[0] != 1049:
            raise
        conn = pymysql.connect(**options)
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4")
        conn.select_db(name)
    if initialize:
        with conn.cursor() as cur:
            for sql in (ROOT / "sql/schema.sql").read_text(encoding="utf-8").split(";"):
                if sql.strip():
                    cur.execute(sql)
    return conn


def register(conn, path, species):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO images (image_path, species) VALUES (%s, %s)
                       ON DUPLICATE KEY UPDATE image_id=LAST_INSERT_ID(image_id), species=%s""",
                    (path, species, species))
        return cur.lastrowid


def publish(conn, image_id, mask_path, features):
    arrays = [json.dumps(v.tolist(), allow_nan=False, separators=(",", ":")) for v in features]
    conn.begin()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE images SET mask_path=%s WHERE image_id=%s", (mask_path, image_id))
            cur.execute("""INSERT INTO image_features
                           (image_id, color_feature, texture_feature, shape_feature)
                           VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE
                           color_feature=%s, texture_feature=%s, shape_feature=%s""",
                        (image_id, *arrays, *arrays))
            cur.execute(SELECT_FEATURES + " WHERE i.image_id=%s", (image_id,))
            row = cur.fetchone()
            if row[2] != mask_path:
                raise ValueError("MySQL read-back differs from the published mask path")
            for value, expected in zip(row[3:], features):
                np.testing.assert_allclose(json.loads(value), expected, rtol=1e-12, atol=1e-12)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
