import streamlit as st
from pathlib import Path
import random
import uuid 
import json
from utils import(
    init_db,
    list_pool_ids,
    get_or_create_assignment,
    all_sets_valid,
    save_results_json,
    IMAGE_ROOT,
    N_TOTAL,
    SET_SIZE,
    SEED,
    THUMB_BOX_H
)
import sqlite3

DB_PATH = "assignments.db"
LABELS = ["A", "B", "C", "D", "E"]
RANK_OPTIONS = ["-","1", "2", "3", "4", "5"]


# 세션 상태 
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# 데이터 조회
# 데이터베이스에 연결
connection = sqlite3.connect("assignments.db")
cursor = connection.cursor()
# 데이터 조회
cursor.execute("SELECT * FROM session_assignments")
rows = cursor.fetchall()
# 데이터 출력
print("할당 세팅:")
for row in rows:
    print(row)
# 연결 종료
# connection.close()


# 팝업 프리뷰 
@st.dialog("Preview")
def preview_dialog(real_path):
    st.image(real_path, use_container_width=True)
    st.caption(Path(real_path).name)

# 청킹 
def chunk(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]
 
st.title("HCI 스마트 액자 실험")
st.markdown("액자 속 그림을 보고 선호하는 순위를 지정해주세요. 순위는 중복 없이 지정해야 합니다.<br>" 
         "1은 가장 높은 순위(1순위)를 나타내며, 5는 가장 낮은 순위(5순위)를 나타냅니다.",
         unsafe_allow_html=True) 


# DB, pool, assignment 준비 
if "conn" not in st.session_state:
    st.session_state.conn = init_db(DB_PATH)

if "pool_ids" not in st.session_state:
    st.session_state.pool_ids = list_pool_ids(IMAGE_ROOT)

if "make_sets" not in st.session_state:
    st.session_state.make_sets = get_or_create_assignment(
        conn=st.session_state.conn,
        session_id=st.session_state.session_id,
        pool_ids=st.session_state.pool_ids,
        n_total=N_TOTAL,
        seed=SEED,
    )

# 세트 구성 및 확인
if "sets" not in st.session_state:
    st.session_state.sets = chunk(st.session_state.make_sets, SET_SIZE)
num_sets = len(st.session_state.sets)

# 진행 상태 표기 
if "set_idx" not in st.session_state:
    st.session_state.set_idx = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False

idx = st.session_state.set_idx
current_ids = st.session_state.sets[idx]  # 5개 (상대경로 ID)

st.write(f"Set {idx+1} / {num_sets}") # set 1/60
st.caption("각 이미지 아래에서 순위를 선택하세요. (1=best, 5=worst)")


# UI 
label_to_id = {}
rank_map = {}

cols = st.columns(5, gap="small")

for i, (col, img_id) in enumerate(zip(cols, current_ids)):
    lbl = LABELS[i]
    label_to_id[lbl] = img_id 

    real_path = str((Path(IMAGE_ROOT) / img_id).resolve())

    with col:
        st.markdown(f"**{lbl}**")

        with st.container(height=THUMB_BOX_H, border=False):
            st.image(real_path, use_container_width=True)

        if st.button("View", key=f"view_{idx}_{lbl}", disabled=st.session_state.submitted):
            preview_dialog(real_path)

        choice = st.selectbox(
            "Rank",
            options=RANK_OPTIONS,
            index=0,
            key=f"rank_{idx}_{lbl}",
            disabled=st.session_state.submitted
        )
        rank_map[lbl] = (int(choice) if choice != "-" else None) 


# 미선택/중복 방지
selected = [rank_map[l] for l in LABELS]
is_complete = all(v is not None for v in selected)
is_unique = (len(set(selected)) == 5) if is_complete else False

if not st.session_state.submitted:
    if not is_complete:
        st.warning("모든 이미지의 순위를 선택해 주세요.")
    elif not is_unique:
        st.error("중복된 순위가 있습니다. 1~5는 각각 한 번씩만 선택해야 합니다.")

# 세트 결과 record 저장
if is_complete and is_unique:
    ranked_labels = [lbl for lbl, _ in sorted(rank_map.items(), key=lambda kv: kv[1])]  # 1->5
    ranked_ids = [label_to_id[lbl] for lbl in ranked_labels]
else:
    ranked_labels = None
    ranked_ids = None

st.session_state.answers[idx] = {
    "session_id": st.session_state.session_id,
    "set_idx": idx,
    "image_labels": LABELS,
    "image_ids_by_label": label_to_id,  # {"A": "...", ...}
    "label_to_rank": rank_map,          # {"A": 1, ...}
    "ranked_labels": ranked_labels,     # ["B","A","E","C","D"] 
    "ranked_ids": ranked_ids,           # ["imgB","imgA",...] 
}

# 버튼 위치 및 Submit
st.divider()
c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    if st.button("Prev", key="previous", disabled=(idx == 0) or st.session_state.submitted):
        st.session_state.set_idx -= 1
        st.rerun()

with c2:
    if st.button(
        "Next", key="Next",
        disabled=(idx >= num_sets - 1) or (not is_complete) or (not is_unique) or st.session_state.submitted
    ):
        st.session_state.set_idx += 1
        st.rerun()
with c3:
    if st.button("Reset to first",key="reset", disabled=st.session_state.submitted):
        st.session_state.set_idx = 0
        st.rerun()


# submit 조건
is_last = (idx == num_sets - 1)
can_submit = (
        is_last
        and is_complete
        and is_unique
        and all_sets_valid(st.session_state.answers, num_sets)
        and (not st.session_state.submitted)
    )

print("idx/num_sets:", idx, num_sets)
print("is_complete:", is_complete, "is_unique:", is_unique)
print("answers keys:", sorted(st.session_state.answers.keys()))
print("all_sets_valid:", all_sets_valid(st.session_state.answers, num_sets))


# 제출 후 JSON 다운로드
if is_last:
    if st.button("Submit", disabled=(not can_submit)):
        st.session_state.submitted = True
        p = save_results_json(st.session_state.answers, st.session_state.session_id)
        st.success(f"Saved on server: {p}")
        st.rerun()

