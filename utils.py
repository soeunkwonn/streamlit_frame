from pathlib import Path
import random
import sqlite3
import json
import time


# Config
IMAGE_ROOT = "./sampled_arts" # 데이터셋 경로 
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
N_TOTAL = 25 # 1세트 내 이미지 수 
SET_SIZE = 5 # 한 번 보여줄 때의 이미지 수 
SEED = 123
THUMB_BOX_H = 220

# 이미지 경로 지정 
def get_image_paths(root: str) -> list[Path]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)

    paths = [
        p for p in root.iterdir()
        if p.is_file()
        and p.suffix.lower() in ALLOWED_EXTS
        and not p.name.startswith(".")
    ]
    return paths

# # 60세트 추출 
# def make_sets(root: str, n_total: int = 300, set_size: int = 5, seed: int | None = None) -> list[list[Path]]:
#     paths = get_image_paths(root)

#     if len(paths) < n_total:
#         raise ValueError(f"Not enough images. Found={len(paths)}, requested={n_total}")

#     if n_total % set_size != 0:
#         raise ValueError(f"n_total must be multiple of set_size. n_total={n_total}, set_size={set_size}")

#     rng = random.Random(seed)

#     picked = rng.sample(paths, n_total)  # 중복 없이 300장
#     rng.shuffle(picked)                 # 세트 구성을 랜덤화

#     sets = [picked[i:i+set_size] for i in range(0, n_total, set_size)]  # 60세트
#     return sets

# # 이미지 저장 루트 
# def rel_id(p: Path, root: Path) -> str: 
#     try:
#         return str(p.resolve().relative_to(root.resolve()))
#     except Exception:
#         return p.name

# DB 및 assignment 세팅 
def init_db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    print("데이터베이스 연결 성공")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claims(
            image_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            claimed_at INTEGER NOT NULL
                )
            """)
    conn.execute("""
                CREATE TABLE IF NOT EXISTS session_assignments(
            session_id TEXT NOT NULL,
            ord        INTEGER NOT NULL,
            image_id   TEXT NOT NULL,
            PRIMARY KEY (session_id, ord)
                )
            """)
    print("테이블 생성 성공")
    conn.commit()
    return conn 


# 데이터셋 폴더 안 이미지들의 상대경로 ID 수집
def list_pool_ids(root): 
    root_p = Path(root)
    if not root_p.exists():
        raise FileNotFoundError(root)
    if not root_p.is_dir():
        raise NotADirectoryError(root)
    
    ids = []
    for p in root_p.iterdir():
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS and not p.name.startswith("."):
            ids.append(p.relative_to(root_p).as_posix())
    
    ids.sort()
    return ids 

# assignment 할당
def get_existing_assignment(conn, session_id):
    rows = conn.execute(
        "SELECT image_id FROM session_assignments WHERE session_id=? ORDER BY ord",
        (session_id,) # session_asssignments 테이블에서 session_id에게 배정된 이미지와, 배정 당시 순서 정렬해서 가져옴
    ).fetchall() # 결과를 모두 리스트로 받음
    if not rows:
        return None 
    return [r[0] for r in rows] # image_id 리스트만 반환

# assignment 할당 혹은 생성 
def get_or_create_assignment(
    conn: sqlite3.Connection,
    session_id: str,
    pool_ids: list[str],
    n_total: int,
    seed: int,
) -> list[str]:
    
    existing = get_existing_assignment(conn, session_id)
    # 이미지 리스트가 있으면 그대로 반환
    if existing and len(existing) == n_total:
        return existing
    elif existing:
        # 기존 배정/claims를 지우고 다시 생성
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute("DELETE FROM session_assignments WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM claims WHERE session_id=?", (session_id,))
            conn.commit()
        except Exception:
            conn.rollback()


    # 없으면 새로 claim해서 할당
    conn.execute("BEGIN IMMEDIATE;")
    try:
        claimed_rows = conn.execute("SELECT image_id FROM claims").fetchall()
        claimed = set(r[0] for r in claimed_rows)
        remaining = [img_id for img_id in pool_ids if img_id not in claimed]

        if len(remaining) < n_total:
            raise RuntimeError(
                f"남은 이미지가 부족합니다. remaining={len(remaining)}, need={n_total}"
            )

        # 세션별로 다르게 샘플되도록 seed를 섞음 
        rng = random.Random(seed + (hash(session_id) % 10_000_000))
        picked = rng.sample(remaining, n_total)
        rng.shuffle(picked)

        now = int(time.time())
        conn.executemany(
            "INSERT INTO claims(image_id, session_id, claimed_at) VALUES(?,?,?)",
            [(img_id, session_id, now) for img_id in picked]
        )
        conn.executemany(
            "INSERT INTO session_assignments(session_id, ord, image_id) VALUES(?,?,?)",
            [(session_id, i, img_id) for i, img_id in enumerate(picked)]
        )
        conn.commit()
        return picked

    except Exception:
        conn.rollback()
        raise



# 데이터 누락 확인 
def all_sets_valid(answers, num_sets):
    if len(answers) < num_sets:
        return False
    for j in range(num_sets):  # 0..num_sets-1
        rec = answers.get(j)
        if not rec:
            return False
        if rec.get("ranked_labels") is None or rec.get("ranked_ids") is None:
            return False
    return True

# 데이터 저장 및 추출 
OUTPUT_DIR = Path("./outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def save_results_json(answers, session_id):
    out = {
        "session_id": session_id,
        "num_sets": len(answers),
        "answers": [answers[k] for k in sorted(answers.keys())]
    }
    save_path = OUTPUT_DIR / f"ranking_{session_id}.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return save_path